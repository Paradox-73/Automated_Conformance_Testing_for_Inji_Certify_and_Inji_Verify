"""``inji-conformance run``: one component's suite test plan from start to ``results.json``.

Steps for ``--component verify`` and ``--component certify``:

1. wait until the suite and the Inji component answer (exit 3 when they do not);
2. Inji Certify only, unless ``--no-seed``: add the credential configuration the plan requests (``cmd_seed``,
   idempotent), so a fresh stack needs no manual step;
3. render the plan template into ``<out>/<component>/config/<template>.json``;
4. stage the suite's scripts, vendored unchanged in ``third_party/oidf-conformance-suite/scripts``, into
   ``<out>/<component>/suite-scripts/`` with a ``certs-keys/`` folder holding this run's keys:
   ``run-test-plan.py`` reads every file in the ``certs-keys`` folder next to itself and fills the config's
   ``{<file>}`` placeholders with them;
5. start ``run-test-plan.py`` (dev mode, ``--export-dir``) and the handoff responder side by side; the script's
   output goes to the console and to ``logs/run-test-plan.log``. The responder answers Inji Verify's tests with
   authorization requests and Inji Certify's tests with credential offers and transaction codes;
6. download the plan's HTML export and extract it into ``exports/html/``;
7. read each module's outcome from the suite, classify it against the benchmark (``inji_conformance.benchmark``)
   unless ``--no-gate``, cross-check the gate with ``run-test-plan.py``'s exit code, and write ``results.json``;
8. remove the staged ``certs-keys`` folder, so no private key stays in the report folder.

Run folder layout (``--out``)::

    <out>/<component>/results.json
    <out>/<component>/config/<template>.json      rendered suite configuration (placeholders, no keys)
    <out>/<component>/exports/*.zip               the suite's plan exports (JSON and HTML)
    <out>/<component>/exports/html/               the HTML export, extracted (one page per module)
    <out>/<component>/benchmark/                  the benchmark files run-test-plan.py was given
    <out>/<component>/logs/run-test-plan.log      the script's output
    <out>/<component>/logs/handoffs.jsonl         one line per handoff
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from inji_conformance import benchmark, keys, manifest, model, plans
from inji_conformance.collect import (
    evidence_path,
    module_result,
    plan_modules,
    review_from_vp_result,
    transaction_id,
    verdict_at_upload,
)
from inji_conformance.handoff import (
    AuthorizationRequestHandoff,
    BrowserVisitHandoff,
    CredentialOfferHandoff,
    Handoff,
    Responder,
    StartTestHandoff,
    VerificationEvidenceHandoff,
    utc_now,
)
from inji_conformance.inji_certify import CertifyClient, CertifyError
from inji_conformance.inji_certify import seed as seed_certify
from inji_conformance.inji_verify import VerifyClient
from inji_conformance.model import Component, ExitCode, RunMode, Track
from inji_conformance.suite import SuiteClient, SuiteError

# Settings from the environment; the compose runner service sets the first four.
ENV_SUITE_URL = "HARNESS_SUITE_URL"
ENV_SUITE_MTLS_URL = "HARNESS_SUITE_MTLS_URL"
ENV_VERIFY_URL = "HARNESS_VERIFY_URL"
ENV_CERTIFY_URL = "HARNESS_CERTIFY_URL"
ENV_PKI_DIR = "HARNESS_PKI_DIR"
ENV_REPORTS_DIR = "HARNESS_REPORTS_DIR"
ENV_HOME = "INJI_CONFORMANCE_HOME"  # folder holding third_party/ and conformance/ (the image sets it)

DEFAULT_SUITE_URL = "https://localhost.emobix.co.uk:18443"
DEFAULT_VERIFY_URL = "https://verify.inji.test:18451/v1/verify"
DEFAULT_CERTIFY_URL = "https://certify.inji.test:18450"  # issuer identifier: an origin, the APIs are below /v1/certify
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


def wait_until_ready(check, what: str, timeout_s: float | None = None, interval_s: float = 3.0) -> None:
    """Call ``check`` (returns True when ready) until it succeeds; RunError(ENVIRONMENT_NOT_READY) after timeout.

    ``timeout_s`` defaults to ``READY_TIMEOUT_S``, read when the call is made.
    """
    if timeout_s is None:
        timeout_s = READY_TIMEOUT_S
    deadline = time.monotonic() + timeout_s
    last = "no answer"
    while True:
        try:
            if check():
                return
            last = "not ready"
        except (httpx.HTTPError, SuiteError, CertifyError) as error:
            last = f"{type(error).__name__}: {error}"
        if time.monotonic() >= deadline:
            raise RunError(f"{what} is not ready after {timeout_s:.0f} s ({last})", ExitCode.ENVIRONMENT_NOT_READY)
        time.sleep(interval_s)


def stage_scripts(home: Path, stage: Path, pki_dir: Path, certs_keys: dict[str, object]) -> Path:
    """Copy the vendored suite scripts into ``stage`` and fill ``stage/certs-keys``; returns the script path."""
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "certs-keys").mkdir(parents=True)
    for name in SUITE_SCRIPTS:
        shutil.copy2(home / SCRIPTS_RELATIVE / name, stage / name)
    stage_certs_keys(stage / "certs-keys", pki_dir, certs_keys)
    return stage / "run-test-plan.py"


def stage_certs_keys(folder: Path, pki_dir: Path, certs_keys: dict[str, object]) -> None:
    """Write each ``certs_keys`` entry of a plan template into ``folder`` (forms: ``inji_conformance.plans``)."""

    def source_text(name: str) -> str:
        path = pki_dir / name
        if not path.is_file():
            raise RunError(f"run key {path} is missing (pki-init writes it)", ExitCode.ENVIRONMENT_NOT_READY)
        return path.read_text(encoding="utf-8")

    for target, source in certs_keys.items():
        if isinstance(source, str):
            text = source_text(source)
        elif isinstance(source, dict) and source.get("as") == "json_string":
            # run-test-plan.py turns newlines of a certs-keys file into spaces; as a JSON string literal the PEM
            # text keeps its line breaks, and the config uses the placeholder without quotes.
            text = json.dumps(source_text(str(source["from"])))
        elif isinstance(source, dict) and source.get("generate") == "p256_jwks":
            text = json.dumps(keys.new_private_jwks(target.split(".", 1)[0]))
        else:
            raise RunError(f"certs_keys.{target}: unknown form {source!r}", ExitCode.USAGE)
        (folder / target).write_text(text, encoding="utf-8", newline="\n")


def run_script(
    command: Sequence[str], cwd: Path, env: dict[str, str], log_path: Path, deadline: float, *, label: str = "suite"
) -> tuple[int | None, str | None]:
    """Run ``run-test-plan.py``, copying its output to the console and the log; returns (exit code, plan id).

    When ``deadline`` (time.monotonic) passes, the script is stopped and the exit code is None; the plan id is
    still returned, so the modules that ran can be reported.
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
                print(f"{label} | {line}", end="", flush=True)
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
            code = None
        finally:
            reader.join(timeout=10)
    return code, plan_id[0] if plan_id else None


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


# ---------------------------------------------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    """One component, or both with ``--combined``: at the same time, or one after the other with ``--serial``.

    The components share the run id and the run folder (``<out>/certify``, ``<out>/verify``); their aliases differ
    (``inji-certify-<run id>``, ``inji-verify-<run id>``), so the two responders never touch each other's tests.
    The exit code is the highest of the components' codes. ``manifest.json`` records the wall time of each plan.
    """
    started_at = utc_now()
    run_id = getattr(args, "run_id", None) or new_run_id()
    out = Path(args.out) if args.out else default_out_dir(run_id)
    components = [Component.CERTIFY, Component.VERIFY] if args.combined else [Component(args.component)]
    parallel = bool(args.combined and not args.serial)
    outcomes: dict[Component, tuple[int, model.Results | None]] = {}

    def one(component: Component) -> None:
        prefix = f"inji-conformance run ({component.value})" if args.combined else "inji-conformance run"
        try:
            outcomes[component] = run_component(args, component, run_id=run_id, out=out, label=component.value)
        except (RunError, plans.PlanError) as error:
            code = error.exit_code if isinstance(error, RunError) else ExitCode.USAGE
            print(f"{prefix}: {error}", file=sys.stderr)
            outcomes[component] = (int(code), None)
        except Exception as error:  # one plan's crash must not hide the other plan's results
            print(f"{prefix}: {type(error).__name__}: {error}", file=sys.stderr)
            outcomes[component] = (int(ExitCode.ENVIRONMENT_NOT_READY), None)
            if not parallel:
                raise

    if parallel:
        threads = [threading.Thread(target=one, args=(c,), name=f"plan-{c.value}") for c in components]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    else:
        for component in components:
            one(component)

    worst = max(code for code, _results in outcomes.values())
    finished = [(results, code) for code, results in (outcomes[c] for c in components) if results is not None]
    if finished:
        written = manifest.build(
            run_id,
            RunMode.COMBINED if args.combined else RunMode.COMPONENT,
            Track(args.track),
            started_at,
            utc_now(),
            finished,
            parallel=parallel if args.combined else None,
            out=out,
            command=sys.argv,
        )
        if written is not None and (not args.combined or len(finished) == len(components)):
            print(f"manifest: {manifest.write(written, out)}")
    if args.combined:
        print(f"combined run {run_id}: " + ", ".join(f"{c.value} exit {outcomes[c][0]}" for c in components))
    return worst


def cmd_gate(args: argparse.Namespace) -> int:
    """``inji-conformance gate --run DIR``: classify a recorded run against the benchmark and exit with the gate.

    ``DIR`` is a component run folder (``<out>/<component>``) or its ``results.json``. The file itself is not
    changed; the verdicts are printed, and written as JUnit XML with ``--junit``.
    """
    path = Path(args.run)
    results_file = path / "results.json" if path.is_dir() else path
    try:
        results = model.load_results(results_file)
    except FileNotFoundError:
        print(f"inji-conformance gate: no results file at {results_file}", file=sys.stderr)
        return ExitCode.USAGE
    except (model.ContractError, OSError, ValueError) as error:
        print(f"inji-conformance gate: {error}", file=sys.stderr)
        return ExitCode.USAGE
    try:
        home = harness_home() if not args.benchmark_dir else None
        folder = Path(args.benchmark_dir) if args.benchmark_dir else benchmark.default_dir(home)
        bench = benchmark.load(folder, results.component)
    except (RunError, benchmark.BenchmarkError) as error:
        print(f"inji-conformance gate: {error}", file=sys.stderr)
        return ExitCode.USAGE
    classified = benchmark.classify(results, bench, allow_stale=bool(args.allow_stale), home=home)
    for entry in benchmark.unused_entries(classified, bench):
        print(f"warning: benchmark entry matches no module of this run: {benchmark.entry_label(entry)}")
    for line in classified.gate.messages:
        print(line)
    if args.junit:
        Path(args.junit).parent.mkdir(parents=True, exist_ok=True)
        Path(args.junit).write_text(benchmark.junit_xml(classified), encoding="utf-8", newline="\n")
        print(f"junit: {args.junit}")
    return int(classified.gate.exit_code)


def cmd_seed(args: argparse.Namespace) -> int:
    """``inji-conformance seed certify``: add the credential configuration the issuer plan requests (idempotent)."""
    try:
        home = harness_home()
        template = plans.find_template(home / "conformance" / "plans", Component.CERTIFY, Track(args.track))
        target_url = (args.target or os.environ.get(ENV_CERTIFY_URL, DEFAULT_CERTIFY_URL)).rstrip("/")
        certify = CertifyClient(target_url, verify=tls_verify(pki_folder()))
        try:
            wait_until_ready(lambda: bool(certify.issuer_metadata()), f"Inji Certify at {target_url}")
            print(seed_component(certify, template, {"target_url": target_url}))
        finally:
            certify.close()
    except (RunError, plans.PlanError) as error:
        code = error.exit_code if isinstance(error, RunError) else ExitCode.USAGE
        print(f"inji-conformance seed: {error}", file=sys.stderr)
        return code
    return ExitCode.OK


def seed_component(
    certify: CertifyClient, template: plans.PlanTemplate, run_values: Mapping[str, str] | None = None
) -> str:
    """Seed Inji Certify from the template's rendered ``seed.credential_configuration``; the one-line outcome."""
    definition = plans.render_seed(template, run_values).get("credential_configuration")
    if not isinstance(definition, dict):
        raise plans.PlanError(f"{template.path.name}: seed.credential_configuration is missing")
    try:
        return seed_certify(certify, definition).message()
    except (CertifyError, httpx.HTTPError) as error:
        raise RunError(f"seeding Inji Certify failed: {error}", ExitCode.ENVIRONMENT_NOT_READY) from error


def pki_folder() -> Path:
    return Path(os.environ.get(ENV_PKI_DIR) or os.path.join(os.environ.get("HARNESS_RUN_DIR", "run"), "pki"))


def tls_verify(pki_dir: Path) -> bool | str:
    """The run's test CA when pki-init wrote one, else no certificate check (the Inji hosts use that CA)."""
    ca_file = pki_dir / "ca.crt"
    return str(ca_file) if ca_file.is_file() else False


def variant_overrides(values: Sequence[str] | None) -> dict[str, str]:
    """``--variant NAME=VALUE`` options as a mapping."""
    overrides = {}
    for item in values or ():
        name, sep, value = item.partition("=")
        if not sep or not name or not value:
            raise plans.PlanError(f"--variant expects NAME=VALUE, not {item!r}")
        overrides[name] = value
    return overrides


def run_component(
    args: argparse.Namespace,
    component: Component,
    *,
    run_id: str | None = None,
    out: Path | None = None,
    label: str = "suite",
) -> tuple[int, model.Results]:
    """Run one component's plan and write its results.json; returns (exit code, results)."""
    started_at = utc_now()
    deadline = time.monotonic() + 60 * (args.timeout_minutes or DEFAULT_TIMEOUT_MINUTES)
    home = harness_home()
    track = Track(args.track)
    template = plans.find_template(
        home / "conformance" / "plans", component, track, name=getattr(args, "template", None)
    )
    template = plans.with_variant(template, variant_overrides(getattr(args, "variant", None)))
    run_id = run_id or new_run_id()
    out = out or (Path(args.out) if args.out else default_out_dir(run_id))
    folder = out / component.value
    for sub in ("config", "exports", "logs"):
        (folder / sub).mkdir(parents=True, exist_ok=True)

    suite_url = os.environ.get(ENV_SUITE_URL, DEFAULT_SUITE_URL).rstrip("/")
    if component is Component.VERIFY:
        default_target = os.environ.get(ENV_VERIFY_URL, DEFAULT_VERIFY_URL)
    else:
        default_target = os.environ.get(ENV_CERTIFY_URL, DEFAULT_CERTIFY_URL)
    target_url = (args.target or default_target).rstrip("/")
    pki_dir = pki_folder()
    variant = ", ".join(f"{k}={v}" for k, v in template.variant.items())
    print(f"run {run_id}: {component.value} plan {template.plan} [{variant}] against {target_url}; results in {folder}")

    suite = SuiteClient(suite_url)
    verify = VerifyClient(target_url, verify=tls_verify(pki_dir)) if component is Component.VERIFY else None
    certify = CertifyClient(target_url, verify=tls_verify(pki_dir)) if component is Component.CERTIFY else None
    try:
        server: dict = {}

        def suite_ready() -> bool:
            server.update(suite.server_info())
            return True

        wait_until_ready(suite_ready, f"the conformance suite at {suite_url}")
        if verify is not None:
            wait_until_ready(lambda: verify.health() == 200, f"Inji Verify at {target_url}")
        if certify is not None:
            wait_until_ready(lambda: bool(certify.issuer_metadata()), f"Inji Certify at {target_url}")
            if getattr(args, "no_seed", False):
                print("seed certify: skipped (--no-seed)")
            else:
                print(seed_component(certify, template, {"target_url": target_url}))

        run_values = {"run_id": run_id, "target_url": target_url, "suite_url": suite_url}
        alias = plans.substitute(template.config.get("alias", ""), {**template.parameters, **run_values})
        if run_id not in alias:
            # The responder recognises this run's tests by alias; a fixed alias could answer another run's tests.
            raise plans.PlanError(f"{template.path.name}: config.alias must contain ${{run_id}}")
        config_path = folder / "config" / f"{template.name}.json"
        config_path.write_text(plans.render_config(template, run_values), encoding="utf-8", newline="\n")
        handoff_settings = plans.render_handoff(template, run_values)
        bench = None
        expected_args: list[str] = []
        if not args.no_gate:
            bench = load_benchmark(args, home, component).for_config(relative(config_path, folder))
            if args.modules:
                # run-test-plan.py fails on an entry that matches no module of the run, so a run of selected
                # modules uses only the entries for those modules, for the script and for the gate alike.
                bench = bench.restricted_to(
                    [(name, template.variant) for name in args.modules], relative(config_path, folder)
                )
            failures_file, skips_file = bench.write(folder / "benchmark", component)
            expected_args = [
                "--expected-failures-file",
                relative(failures_file, folder),
                "--expected-skips-file",
                relative(skips_file, folder),
            ]

        stage = folder / "suite-scripts"
        script = stage_scripts(home, stage, pki_dir, dict(template.certs_keys))
        command = [
            sys.executable,
            "-u",
            str(script.resolve()),
            "--export-dir",
            "exports",
            *expected_args,
            *plans.plan_spec(template, relative(config_path, folder), args.modules),
        ]
        env = {
            **os.environ,
            "CONFORMANCE_SERVER": suite_url + "/",
            "CONFORMANCE_SERVER_MTLS": os.environ.get(ENV_SUITE_MTLS_URL, suite_url.replace(":18443", ":18444")) + "/",
            "CONFORMANCE_DEV_MODE": "1",
            # The script stops the whole plan after three modules in a row that did not reach FINISHED. Against
            # Inji, a module is INTERRUPTED by every failing condition inside a request it answers, so that would
            # end a plan after three Inji findings. The run's own time limit still bounds an unhealthy suite.
            "CONFORMANCE_MAX_CONSECUTIVE_FAILURES": os.environ.get("CONFORMANCE_MAX_CONSECUTIVE_FAILURES", "1000"),
            "PYTHONUNBUFFERED": "1",
        }

        handoffs = component_handoffs(template, handoff_settings, suite, verify, certify)
        requests = next((h for h in handoffs if isinstance(h, AuthorizationRequestHandoff)), None)
        if requests is not None and verify is not None:
            handoffs.append(
                VerificationEvidenceHandoff(
                    suite,
                    verify,
                    requests.transactions,
                    folder / "evidence",
                    template.expected_review,
                    relative_to=out,
                )
            )
        responder = Responder(
            suite,
            alias,
            [*handoffs, BrowserVisitHandoff(suite), StartTestHandoff(suite)],
            log_path=folder / "logs" / "handoffs.jsonl",
        )
        (folder / "logs" / "handoffs.jsonl").write_text("", encoding="utf-8")
        responder.start()
        try:
            script_code, plan_id = run_script(
                command, folder, env, folder / "logs" / "run-test-plan.log", deadline, label=label
            )
        finally:
            responder.stop()
            shutil.rmtree(stage / "certs-keys", ignore_errors=True)
        if script_code is None:
            print("the run reached its time limit (--timeout-minutes); run-test-plan.py was stopped", file=sys.stderr)
        else:
            print(f"run-test-plan.py exited with {script_code}; plan {plan_id or 'not created'}")
        html_pages = export_html(suite, plan_id, folder / "exports") if plan_id else {}

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
            timed_out=script_code is None,
        )
        results = build_results(context, suite, verify, plan_id, responder, html_pages)
        if bench is not None and not context.timed_out:
            results = apply_benchmark(results, bench, home, script_code, allow_stale=bool(args.allow_stale))
        shim = certify.as_metadata_shim() if certify is not None else None
        if shim:
            results = dataclasses.replace(
                results, notes=(*results.notes, f"Inji Certify's authorization server metadata was changed: {shim}")
            )
    finally:
        suite.close()
        for client in (verify, certify):
            if client is not None:
                client.close()

    model.dump(results, folder / "results.json")
    print_summary(results, folder / "results.json")
    return (int(results.gate.exit_code) if results.gate else int(ExitCode.OK)), results


def component_handoffs(
    template: plans.PlanTemplate,
    settings: dict,
    suite: SuiteClient,
    verify: VerifyClient | None,
    certify: CertifyClient | None,
) -> list[Handoff]:
    """The component's own handoffs, configured from the template's ``handoff`` block."""
    try:
        if verify is not None:
            request = settings["authorization_request"]
            return [
                AuthorizationRequestHandoff(
                    suite,
                    verify,
                    client_id=request["client_id"],
                    dcql_query=request["dcql_query"],
                    response_mode=request.get("response_mode"),
                )
            ]
        if certify is not None:
            offer = settings["credential_offer"]
            return [
                CredentialOfferHandoff(
                    suite,
                    certify,
                    str(offer["credential_configuration_id"]),
                    offer["claims"],
                    tx_code_length=int(offer.get("tx_code_length", 6)),
                    expires_in=int(offer.get("expires_in", 600)),
                )
            ]
    except (KeyError, TypeError, ValueError) as error:
        raise plans.PlanError(f"{template.path.name}: handoff block is incomplete: {error!r}") from error
    return []


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
    timed_out: bool = False  # run-test-plan.py was stopped at the time limit


def build_results(
    ctx: RunContext,
    suite: SuiteClient,
    verify: VerifyClient | None,
    plan_id: str | None,
    responder: Responder,
    html_pages: Mapping[str, str] | None = None,
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
        if info and info.get("result") == "REVIEW" and verify is not None:
            tx = transaction_id(handoffs)
            # The verdict the evidence image shows; read again only when no upload recorded one.
            seen = verdict_at_upload(handoffs) or (verify.vp_result(tx) if tx else None)
            review = review_from_vp_result(template.expected_review(name), seen, evidence_path(handoffs))
        result = module_result(
            name,
            test_id,
            info,
            log,
            handoffs,
            suite_log_url=suite.log_url(test_id) if test_id else None,
            review=review,
            duration_s=_duration(log),
        )
        page = (html_pages or {}).get(test_id or "")
        if page and result.links is not None:
            result = dataclasses.replace(result, links=dataclasses.replace(result.links, export=page))
        modules.append(result)

    exports = sorted(
        (p for p in (ctx.folder / "exports").glob("*.zip") if not p.name.endswith("-html.zip")),
        key=lambda p: p.stat().st_mtime,
    )
    summary = model.Summary.of(modules)
    failing = summary.regression + summary.stale_benchmark
    notes = []
    if responder.errors:
        notes.append(f"handoff responder: {len(responder.errors)} failed polls, last: {responder.errors[-1]}")
    if ctx.timed_out:
        # Exit 4 with or without --no-gate: an incomplete run is never a pass.
        gating = not ctx.no_gate and ctx.track is Track.GATE
        gate = model.Gate(
            passed=False,
            exit_code=ExitCode.TIMEOUT,
            messages=("the run reached its time limit; modules that did not finish are regressions",),
        )
    elif ctx.no_gate:
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


def load_benchmark(args: argparse.Namespace, home: Path, component: Component) -> benchmark.Benchmark:
    folder = Path(args.benchmark_dir) if getattr(args, "benchmark_dir", None) else benchmark.default_dir(home)
    try:
        return benchmark.load(folder, component)
    except benchmark.BenchmarkError as error:
        raise RunError(f"benchmark: {error}", ExitCode.USAGE) from error


def export_html(suite: SuiteClient, plan_id: str, exports: Path) -> dict[str, str]:
    """Download the plan's HTML export into ``exports/`` and extract it into ``exports/html/``.

    Returns the page of each test id, relative to the run folder's parent (as results.json paths are). A failed
    download is reported and leaves the map empty: the live suite log links still work while the stack is up.
    """
    try:
        name, data = suite.export_html(plan_id)
    except (SuiteError, httpx.HTTPError) as error:
        print(f"HTML export of plan {plan_id} failed: {error}", file=sys.stderr)
        return {}
    stem = name[: -len(".zip")] if name.endswith(".zip") else name
    archive = exports / f"{stem}-html.zip"
    archive.write_bytes(data)
    target = exports / "html"
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    pages: dict[str, str] = {}
    try:
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.namelist():
                # Only plain file names: an export never has folders, and this keeps "../" out of the run folder.
                if "/" in member or "\\" in member or member.startswith("."):
                    continue
                (target / member).write_bytes(bundle.read(member))
                if member.startswith("test-log-") and member.endswith(".html"):
                    test_id = member[: -len(".html")].rsplit("-", 1)[-1]
                    pages[test_id] = exports.parent.name + "/exports/html/" + member
    except zipfile.BadZipFile as error:
        print(f"HTML export of plan {plan_id} is not a zip: {error}", file=sys.stderr)
        return {}
    return pages


def apply_benchmark(
    results: model.Results,
    bench: benchmark.Benchmark,
    home: Path,
    script_code: int | None,
    *,
    allow_stale: bool,
) -> model.Results:
    """Classify against the benchmark, then cross-check the gate with ``run-test-plan.py``'s exit code.

    Two outcomes stop the run with exit 2, because the benchmark or the harness is wrong rather than Inji: an entry
    that matches no module of a whole-plan run, and a gate that disagrees with ``run-test-plan.py`` on the same
    benchmark files.
    """
    classified = benchmark.classify(results, bench, allow_stale=allow_stale, home=home)
    problems = []
    unused = benchmark.unused_entries(classified, bench)
    if unused:
        problems.append(
            "benchmark entries that match no module of this plan: "
            + "; ".join(benchmark.entry_label(entry) for entry in unused)
        )
    disagreement = benchmark.cross_check(classified, script_code)
    if disagreement:
        problems.append(disagreement)
    if not problems:
        return classified
    for problem in problems:
        print(f"inji-conformance run: {problem}", file=sys.stderr)
    gate = dataclasses.replace(
        classified.gate, passed=False, exit_code=ExitCode.USAGE, messages=(*classified.gate.messages, *problems)
    )
    return dataclasses.replace(classified, gate=gate)


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
    for line in gate.messages if gate else ():
        print(line)
    state = "not applied" if not results.gating else ("passed" if gate and gate.passed else "failed")
    print(f"results: {path} ({results.summary.total if results.summary else 0} modules, gate {state})")
