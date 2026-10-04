"""``inji-conformance run``: one component's suite test plan from start to ``results.json``.

Steps for ``--component verify`` (the issuer path follows the same steps with its own handoffs):

1. wait until the suite and Inji Verify answer (exit 3 when they do not);
2. render the plan template into ``<out>/<component>/config/<template>.json``;
3. stage the suite's scripts, vendored unchanged in ``third_party/oidf-conformance-suite/scripts``, into
   ``<out>/<component>/suite-scripts/`` with a ``certs-keys/`` folder holding this run's keys:
   ``run-test-plan.py`` reads every file in the ``certs-keys`` folder next to itself and fills the config's
   ``{<file>}`` placeholders with them;
4. start ``run-test-plan.py`` (dev mode, ``--export-dir``) and the handoff responder side by side; the script's
   output goes to the console and to ``logs/run-test-plan.log``;
5. read each module's outcome from the suite and write ``results.json``;
6. remove the staged ``certs-keys`` folder, so no private key stays in the report folder.

Run folder layout (``--out``)::

    <out>/<component>/results.json
    <out>/<component>/config/<template>.json      rendered suite configuration (placeholders, no keys)
    <out>/<component>/exports/*.zip               the suite's plan export
    <out>/<component>/logs/run-test-plan.log      the script's output
    <out>/<component>/logs/handoffs.jsonl         one line per handoff
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from inji_conformance import model, plans
from inji_conformance.collect import module_result, plan_modules, review_from_vp_result, transaction_id
from inji_conformance.handoff import (
    AuthorizationRequestHandoff,
    BrowserVisitHandoff,
    Responder,
    StartTestHandoff,
    utc_now,
)
from inji_conformance.inji_verify import VerifyClient
from inji_conformance.model import Component, ExitCode, Track
from inji_conformance.suite import SuiteClient, SuiteError

# Settings from the environment; the compose runner service sets the first four.
ENV_SUITE_URL = "HARNESS_SUITE_URL"
ENV_SUITE_MTLS_URL = "HARNESS_SUITE_MTLS_URL"
ENV_VERIFY_URL = "HARNESS_VERIFY_URL"
ENV_PKI_DIR = "HARNESS_PKI_DIR"
ENV_REPORTS_DIR = "HARNESS_REPORTS_DIR"
ENV_HOME = "INJI_CONFORMANCE_HOME"  # folder holding third_party/ and conformance/ (the image sets it)

DEFAULT_SUITE_URL = "https://localhost.emobix.co.uk:18443"
DEFAULT_VERIFY_URL = "https://verify.inji.test:18451/v1/verify"
DEFAULT_TIMEOUT_MINUTES = 30.0
READY_TIMEOUT_S = 120.0
SUITE_SCRIPTS = ("run-test-plan.py", "conformance.py", "test_plan_parser.py")
SCRIPTS_RELATIVE = Path("third_party", "oidf-conformance-suite", "scripts")


class RunError(Exception):
    """The run cannot go on; ``exit_code`` says why (usage, environment, timeout)."""

    def __init__(self, message: str, exit_code: ExitCode):
        super().__init__(message)
        self.exit_code = exit_code


# ---------------------------------------------------------------------------------------------------------------
# Locations and run values
# ---------------------------------------------------------------------------------------------------------------


def harness_home() -> Path:
    """The folder with ``third_party/`` and ``conformance/``: $INJI_CONFORMANCE_HOME, else a parent of this file
    or of the current directory."""
    configured = os.environ.get(ENV_HOME)
    candidates = [Path(configured)] if configured else []
    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        candidates += [start, *start.parents]
    for folder in candidates:
        if (folder / SCRIPTS_RELATIVE / "run-test-plan.py").is_file() and (folder / "conformance" / "plans").is_dir():
            return folder
    raise RunError(
        f"cannot find {SCRIPTS_RELATIVE}/run-test-plan.py and conformance/plans; set {ENV_HOME}", ExitCode.USAGE
    )


def new_run_id(now: datetime | None = None) -> str:
    """UTC start time plus a random suffix, for example 20261004T193000Z-1a2b3c (sorts by time)."""
    now = now or datetime.now(UTC)
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(3)}"


def default_out_dir(run_id: str) -> Path:
    base = os.environ.get(ENV_REPORTS_DIR) or os.path.join(os.environ.get("HARNESS_RUN_DIR", "run"), "reports")
    return Path(base) / run_id


# ---------------------------------------------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------------------------------------------


def wait_until_ready(check, what: str, timeout_s: float = READY_TIMEOUT_S, interval_s: float = 3.0) -> None:
    """Call ``check`` (returns True when ready) until it succeeds; RunError(ENVIRONMENT_NOT_READY) after timeout."""
    deadline = time.monotonic() + timeout_s
    last = "no answer"
    while True:
        try:
            if check():
                return
            last = "not ready"
        except (httpx.HTTPError, SuiteError) as error:
            last = f"{type(error).__name__}: {error}"
        if time.monotonic() >= deadline:
            raise RunError(f"{what} is not ready after {timeout_s:.0f} s ({last})", ExitCode.ENVIRONMENT_NOT_READY)
        time.sleep(interval_s)


def stage_scripts(home: Path, stage: Path, pki_dir: Path, certs_keys: dict[str, str]) -> Path:
    """Copy the vendored suite scripts into ``stage`` and fill ``stage/certs-keys``; returns the script path."""
    if stage.exists():
        shutil.rmtree(stage)
    keys = stage / "certs-keys"
    keys.mkdir(parents=True)
    for name in SUITE_SCRIPTS:
        shutil.copy2(home / SCRIPTS_RELATIVE / name, stage / name)
    for target, source in certs_keys.items():
        path = pki_dir / source
        if not path.is_file():
            raise RunError(f"run key {path} is missing (pki-init writes it)", ExitCode.ENVIRONMENT_NOT_READY)
        shutil.copyfile(path, keys / target)
    return stage / "run-test-plan.py"


def run_script(
    command: Sequence[str], cwd: Path, env: dict[str, str], log_path: Path, deadline: float
) -> tuple[int, str | None]:
    """Run ``run-test-plan.py``, copying its output to the console and the log; returns (exit code, plan id).

    Raises RunError(TIMEOUT) and stops the script when ``deadline`` (time.monotonic) passes.
    """
    plan_id: list[str] = []
    marker = "Created test plan, new id: "
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )

        def pump() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(f"suite | {line}", end="", flush=True)
                # The script prefixes its lines with a timestamp, so the marker is searched, not matched at the start.
                if marker in line and not plan_id:
                    plan_id.append(line.split(marker, 1)[1].strip())

        reader = threading.Thread(target=pump, name="run-test-plan-output", daemon=True)
        reader.start()
        try:
            code = process.wait(timeout=max(1.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            raise RunError("the run reached its time limit; run-test-plan.py was stopped", ExitCode.TIMEOUT) from None
        finally:
            reader.join(timeout=10)
    return code, plan_id[0] if plan_id else None


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


# ---------------------------------------------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    if args.combined or args.component != Component.VERIFY.value:
        print("inji-conformance run: this version runs --component verify only", file=sys.stderr)
        return ExitCode.USAGE
    try:
        return run_component(args, Component(args.component))
    except (RunError, plans.PlanError) as error:
        code = error.exit_code if isinstance(error, RunError) else ExitCode.USAGE
        print(f"inji-conformance run: {error}", file=sys.stderr)
        return code


def run_component(args: argparse.Namespace, component: Component) -> int:
    started_at = utc_now()
    deadline = time.monotonic() + 60 * (args.timeout_minutes or DEFAULT_TIMEOUT_MINUTES)
    home = harness_home()
    track = Track(args.track)
    template = plans.find_template(home / "conformance" / "plans", component, track)
    run_id = new_run_id()
    out = Path(args.out) if args.out else default_out_dir(run_id)
    folder = out / component.value
    for sub in ("config", "exports", "logs"):
        (folder / sub).mkdir(parents=True, exist_ok=True)

    suite_url = os.environ.get(ENV_SUITE_URL, DEFAULT_SUITE_URL).rstrip("/")
    target_url = (args.target or os.environ.get(ENV_VERIFY_URL, DEFAULT_VERIFY_URL)).rstrip("/")
    pki_dir = Path(os.environ.get(ENV_PKI_DIR) or os.path.join(os.environ.get("HARNESS_RUN_DIR", "run"), "pki"))
    ca_file = pki_dir / "ca.crt"
    print(f"run {run_id}: {component.value} plan {template.plan} against {target_url}; results in {folder}")

    suite = SuiteClient(suite_url)
    verify = VerifyClient(target_url, verify=str(ca_file) if ca_file.is_file() else False)
    try:
        server: dict = {}

        def suite_ready() -> bool:
            server.update(suite.server_info())
            return True

        wait_until_ready(suite_ready, f"the conformance suite at {suite_url}")
        wait_until_ready(lambda: verify.health() == 200, f"Inji Verify at {target_url}")

        run_values = {"run_id": run_id, "target_url": target_url, "suite_url": suite_url}
        alias = plans.substitute(template.config.get("alias", ""), {**template.parameters, **run_values})
        if run_id not in alias:
            # The responder recognises this run's tests by alias; a fixed alias could answer another run's tests.
            raise plans.PlanError(f"{template.path.name}: config.alias must contain ${{run_id}}")
        config_path = folder / "config" / f"{template.name}.json"
        config_path.write_text(plans.render_config(template, run_values), encoding="utf-8", newline="\n")
        handoff_settings = plans.render_handoff(template, run_values).get("authorization_request", {})

        stage = folder / "suite-scripts"
        script = stage_scripts(home, stage, pki_dir, dict(template.certs_keys))
        command = [
            sys.executable,
            "-u",
            str(script.resolve()),
            "--export-dir",
            "exports",
            *plans.plan_spec(template, relative(config_path, folder), args.modules),
        ]
        env = {
            **os.environ,
            "CONFORMANCE_SERVER": suite_url + "/",
            "CONFORMANCE_SERVER_MTLS": os.environ.get(ENV_SUITE_MTLS_URL, suite_url.replace(":18443", ":18444")) + "/",
            "CONFORMANCE_DEV_MODE": "1",
            "PYTHONUNBUFFERED": "1",
        }

        responder = Responder(
            suite,
            alias,
            [
                AuthorizationRequestHandoff(
                    suite,
                    verify,
                    client_id=handoff_settings["client_id"],
                    dcql_query=handoff_settings["dcql_query"],
                    response_mode=handoff_settings.get("response_mode"),
                ),
                BrowserVisitHandoff(suite),
                StartTestHandoff(suite),
            ],
            log_path=folder / "logs" / "handoffs.jsonl",
        )
        (folder / "logs" / "handoffs.jsonl").write_text("", encoding="utf-8")
        responder.start()
        try:
            script_code, plan_id = run_script(command, folder, env, folder / "logs" / "run-test-plan.log", deadline)
        finally:
            responder.stop()
            shutil.rmtree(stage / "certs-keys", ignore_errors=True)
        print(f"run-test-plan.py exited with {script_code}; plan {plan_id or 'not created'}")

        context = RunContext(
            run_id=run_id,
            component=component,
            track=track,
            template=template,
            started_at=started_at,
            suite_url=suite_url,
            suite_version=str(server.get("version") or "unknown"),
            target_url=target_url,
            out=out,
            folder=folder,
            config_path=config_path,
            modules=tuple(args.modules or template.modules),
            no_gate=bool(args.no_gate),
        )
        results = build_results(context, suite, verify, plan_id, responder)
    finally:
        suite.close()
        verify.close()

    model.dump(results, folder / "results.json")
    print_summary(results, folder / "results.json")
    return int(results.gate.exit_code) if results.gate else ExitCode.OK


@dataclasses.dataclass(frozen=True)
class RunContext:
    """What one component run needs when it assembles results.json."""

    run_id: str
    component: Component
    track: Track
    template: plans.PlanTemplate
    started_at: str
    suite_url: str
    suite_version: str
    target_url: str
    out: Path  # run folder; paths in results.json are relative to it
    folder: Path  # <out>/<component>
    config_path: Path
    modules: tuple[str, ...]  # selected modules; empty for every module of the plan
    no_gate: bool


def build_results(
    ctx: RunContext, suite: SuiteClient, verify: VerifyClient, plan_id: str | None, responder: Responder
) -> model.Results:
    """Read every module of the plan from the suite and assemble results.json."""
    template = ctx.template
    modules: list[model.ModuleResult] = []
    plan = suite.plan(plan_id) if plan_id else None
    selected = list(ctx.modules)
    entries = plan_modules(plan, selected) if plan else [(name, None) for name in selected]
    for name, test_id in entries:
        info = suite.test_info(test_id) if test_id else None
        log = suite.test_log(test_id) if test_id else []
        handoffs = responder.records_for(test_id) if test_id else []
        review = None
        if info and info.get("result") == "REVIEW":
            tx = transaction_id(handoffs)
            review = review_from_vp_result(template.expected_review(name), verify.vp_result(tx) if tx else None)
        modules.append(
            module_result(
                name,
                test_id,
                info,
                log,
                handoffs,
                suite_log_url=suite.log_url(test_id) if test_id else None,
                review=review,
                duration_s=_duration(log),
            )
        )

    exports = sorted((ctx.folder / "exports").glob("*.zip"), key=lambda p: p.stat().st_mtime)
    summary = model.Summary.of(modules)
    failing = summary.regression + summary.stale_benchmark
    notes = []
    if responder.errors:
        notes.append(f"handoff responder: {len(responder.errors)} failed polls, last: {responder.errors[-1]}")
    if ctx.no_gate:
        gating = False
        gate = model.Gate(
            passed=True, exit_code=ExitCode.OK, messages=("--no-gate: verdicts recorded, the gate was not applied",)
        )
    else:
        gating = ctx.track is Track.GATE
        passed = failing == 0 or not gating
        gate = model.Gate(
            passed=passed,
            exit_code=ExitCode.OK if passed else ExitCode.GATE_FAILED,
            messages=(f"{failing} of {summary.total} modules fail the gate (no benchmark applied)",),
        )
    return model.Results(
        schema_version=model.RESULTS_SCHEMA_VERSION,
        run_id=ctx.run_id,
        component=ctx.component,
        track=ctx.track,
        gating=gating,
        suite=model.SuiteInfo(base_url=ctx.suite_url, version=ctx.suite_version),
        target=model.TargetInfo(base_url=ctx.target_url),
        plan=model.PlanInfo(
            name=template.plan,
            variant=dict(template.variant),
            id=plan_id,
            config_file=relative(ctx.config_path, ctx.out),
            export=relative(exports[-1], ctx.out) if exports else None,
        ),
        modules=tuple(modules),
        summary=summary,
        gate=gate,
        started_at=ctx.started_at,
        finished_at=utc_now(),
        notes=tuple(notes),
    )


def _duration(log: list[dict]) -> float | None:
    """Seconds between the first and the last log entry of a module (entries carry ``time`` in epoch ms)."""
    times = [entry["time"] for entry in log if isinstance(entry.get("time"), int | float)]
    if not times:
        return None
    return round((max(times) - min(times)) / 1000, 1)


def print_summary(results: model.Results, path: Path) -> None:
    for module in results.modules:
        handoffs = ", ".join(
            f"{h.kind.value} HTTP {h.http_status if h.http_status is not None else '-'} {h.duration_ms:.0f} ms"
            for h in module.handoffs
        )
        result = module.result.value if module.result else "-"
        print(
            f"  {module.name}: {module.status.value} {result} -> {module.verdict.value}"
            + (f" [{handoffs}]" if handoffs else "")
        )
        if module.verdict_reason:
            print(f"    {module.verdict_reason}")
    gate = results.gate
    state = "not applied" if not results.gating else ("passed" if gate and gate.passed else "failed")
    print(f"results: {path} ({results.summary.total if results.summary else 0} modules, gate {state})")
