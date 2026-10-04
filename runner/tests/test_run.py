"""The run command's steps: locating files, staging the suite scripts, driving the script, assembling results."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from inji_conformance import model, plans, run
from inji_conformance.handoff import HandoffRecord, Responder
from inji_conformance.model import Component, ExitCode, HandoffKind, Track

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_harness_home_is_found_from_the_checkout(monkeypatch):
    monkeypatch.delenv(run.ENV_HOME, raising=False)
    assert run.harness_home() == REPO_ROOT


def test_run_id_sorts_by_time_and_matches_the_schema():
    from datetime import UTC, datetime

    run_id = run.new_run_id(datetime(2026, 10, 4, 19, 30, tzinfo=UTC))
    assert run_id.startswith("20261004T193000Z-")
    assert len(run_id) == len("20261004T193000Z-") + 6


def test_stage_copies_scripts_and_run_keys(tmp_path):
    pki = tmp_path / "pki"
    pki.mkdir()
    (pki / "suite-signing.jwk.json").write_text('{"kty": "EC"}', encoding="utf-8")
    script = run.stage_scripts(REPO_ROOT, tmp_path / "stage", pki, {"suite-signing.jwk.json": "suite-signing.jwk.json"})
    assert script.name == "run-test-plan.py"
    assert {p.name for p in script.parent.iterdir()} == {*run.SUITE_SCRIPTS, "certs-keys"}
    assert (script.parent / "certs-keys" / "suite-signing.jwk.json").read_text() == '{"kty": "EC"}'
    # the staged copy is byte-identical to the vendored script
    assert script.read_bytes() == (REPO_ROOT / run.SCRIPTS_RELATIVE / "run-test-plan.py").read_bytes()


def test_stage_without_the_key_is_an_environment_error(tmp_path):
    with pytest.raises(run.RunError) as caught:
        run.stage_scripts(REPO_ROOT, tmp_path / "stage", tmp_path, {"k.json": "missing.json"})
    assert caught.value.exit_code is ExitCode.ENVIRONMENT_NOT_READY


def test_run_script_copies_output_and_finds_the_plan_id(tmp_path, capsys):
    code = "print('2026-10-04 10:41:37 Created test plan, new id: PLAN123'); print('done')"
    exit_code, plan_id = run.run_script(
        [sys.executable, "-c", code], tmp_path, {}, tmp_path / "out.log", time.monotonic() + 60
    )
    assert (exit_code, plan_id) == (0, "PLAN123")
    assert "done" in (tmp_path / "out.log").read_text()
    assert "suite | done" in capsys.readouterr().out


def test_run_script_stops_at_the_deadline(tmp_path):
    with pytest.raises(run.RunError) as caught:
        run.run_script(
            [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, {}, tmp_path / "l", time.monotonic() + 1
        )
    assert caught.value.exit_code is ExitCode.TIMEOUT


def test_wait_until_ready_gives_up_with_exit_3():
    with pytest.raises(run.RunError) as caught:
        run.wait_until_ready(lambda: False, "thing", timeout_s=0, interval_s=0)
    assert caught.value.exit_code is ExitCode.ENVIRONMENT_NOT_READY
    assert "thing is not ready" in str(caught.value)


class FakeSuite:
    """The suite API calls build_results makes, answered from fixed data."""

    def plan(self, plan_id):
        return {"modules": [{"testModule": "oid4vp-1final-verifier-happy-flow", "instances": ["t1"]}]}

    def test_info(self, test_id):
        return {
            "status": "FINISHED",
            "result": "PASSED",
            "description": "d",
            "variant": {"credential_format": "sd_jwt_vc"},
        }

    def test_log(self, test_id):
        return [{"src": "A", "result": "SUCCESS", "time": 1791148800000}, {"src": "B", "time": 1791148807500}]

    def log_url(self, test_id):
        return f"https://localhost.emobix.co.uk:18443/log-detail.html?log={test_id}"


class FakeVerify:
    def vp_result(self, transaction_id):
        return {"vpResultStatus": "SUCCESS"}


@pytest.mark.parametrize("no_gate", [True, False])
def test_build_results_writes_a_valid_results_file(tmp_path, schema_dir, no_gate):
    template = plans.find_template(REPO_ROOT / "conformance" / "plans", Component.VERIFY)
    folder = tmp_path / "verify"
    (folder / "config").mkdir(parents=True)
    (folder / "exports").mkdir()
    (folder / "exports" / "test-log-PLAN.zip").write_bytes(b"zip")
    config = folder / "config" / "verify.oid4vp-1final-verifier.json"
    config.write_text("{}", encoding="utf-8")
    responder = Responder(None, "alias", [])  # type: ignore[arg-type]
    responder.records.append(
        HandoffRecord(
            "t1",
            "oid4vp-1final-verifier-happy-flow",
            HandoffKind.AUTHORIZATION_REQUEST,
            "2026-10-04T19:31:01Z",
            302,
            120.0,
            data={"transaction_id": "tx"},
        )
    )
    ctx = run.RunContext(
        run_id="20261004T193000Z-abc123",
        component=Component.VERIFY,
        track=Track.GATE,
        template=template,
        started_at="2026-01-01T00:00:00Z",
        suite_url="https://localhost.emobix.co.uk:18443",
        suite_version="5.3.1",
        target_url="https://verify.inji.test:18451/v1/verify",
        out=tmp_path,
        folder=folder,
        config_path=config,
        modules=("oid4vp-1final-verifier-happy-flow",),
        no_gate=no_gate,
    )

    results = run.build_results(ctx, FakeSuite(), FakeVerify(), "PLAN", responder)  # type: ignore[arg-type]

    path = tmp_path / "results.json"
    model.dump(results, path)
    assert model.validate(model.read_json(path), model.DocumentKind.RESULTS, schema_dir) == []
    module = results.modules[0]
    assert (module.status.value, module.verdict.value, module.duration_s) == ("FINISHED", "conforms", 7.5)
    assert module.handoffs[0].kind is HandoffKind.AUTHORIZATION_REQUEST
    assert results.plan.config_file == "verify/config/verify.oid4vp-1final-verifier.json"
    assert results.plan.export == "verify/exports/test-log-PLAN.zip"
    assert results.gating is (not no_gate)
    assert results.gate.exit_code is ExitCode.OK
