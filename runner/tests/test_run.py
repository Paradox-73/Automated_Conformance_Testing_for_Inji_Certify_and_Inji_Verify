"""The run command's steps: locating files, staging the suite scripts, driving the script, assembling results."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx
import pytest
import respx

from inji_conformance import model, plans, run
from inji_conformance.handoff import CredentialOfferHandoff, HandoffRecord, Responder
from inji_conformance.inji_certify import CertifyClient, CertifyError
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


def test_run_script_stops_at_the_deadline_and_keeps_the_plan_id(tmp_path):
    code = "import time; print('x Created test plan, new id: P1', flush=True); time.sleep(30)"
    exit_code, plan_id = run.run_script(
        [sys.executable, "-c", code], tmp_path, {}, tmp_path / "log", time.monotonic() + 2
    )
    assert (exit_code, plan_id) == (None, "P1")


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


class FakeEmptySuite(FakeSuite):
    def plan(self, plan_id):
        return {"modules": []}


def verify_context(tmp_path: Path, *, no_gate: bool = False, timed_out: bool = False, modules=None) -> run.RunContext:
    template = plans.find_template(REPO_ROOT / "conformance" / "plans", Component.VERIFY)
    folder = tmp_path / "verify"
    (folder / "config").mkdir(parents=True, exist_ok=True)
    (folder / "exports").mkdir(exist_ok=True)
    config = folder / "config" / "verify.oid4vp-1final-verifier.json"
    config.write_text("{}", encoding="utf-8")
    return run.RunContext(
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
        modules=("oid4vp-1final-verifier-happy-flow",) if modules is None else modules,
        no_gate=no_gate,
        timed_out=timed_out,
    )


@pytest.mark.parametrize(("no_gate", "plan_id"), [(False, "PLAN"), (True, "PLAN"), (False, None)])
def test_build_results_without_modules_fails_with_exit_3(tmp_path, schema_dir, no_gate, plan_id):
    ctx = verify_context(tmp_path, no_gate=no_gate, modules=())
    responder = Responder(None, "alias", [])  # type: ignore[arg-type]
    results = run.build_results(ctx, FakeEmptySuite(), FakeVerify(), plan_id, responder)  # type: ignore[arg-type]
    assert results.modules == ()
    assert (results.gate.passed, results.gate.exit_code) == (False, ExitCode.ENVIRONMENT_NOT_READY)
    path = tmp_path / "results.json"
    model.dump(results, path)
    assert model.validate(model.read_json(path), model.DocumentKind.RESULTS, schema_dir) == []


@pytest.mark.parametrize(("no_gate", "timed_out"), [(True, False), (False, False), (True, True), (False, True)])
def test_build_results_writes_a_valid_results_file(tmp_path, schema_dir, no_gate, timed_out):
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
        timed_out=timed_out,
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
    assert results.gate.exit_code is (ExitCode.TIMEOUT if timed_out else ExitCode.OK)


# --------------------------------------------------------------------------------------------------------------
# Issuer path: certs-keys forms, variants, seeding, the offer handoff, results
# --------------------------------------------------------------------------------------------------------------

CERTIFY = "https://certify.inji.test:18450"
CERTIFY_RUN_VALUES = {
    "run_id": "20261004T193000Z-abc123",
    "target_url": CERTIFY,
    "suite_url": "https://localhost.emobix.co.uk:18443",
}
# Stand-ins for the files pki-init writes; only their line structure matters here.
PEM_CERT = "-----BEGIN CERTIFICATE-----\nMIIBszCCAVmgAwIBAgIU\nq0aB\n-----END CERTIFICATE-----\n"
PEM_KEY = "first line of the key file\nsecond line\nlast line\n"


def certify_template() -> plans.PlanTemplate:
    return plans.find_template(REPO_ROOT / "conformance" / "plans", Component.CERTIFY)


def fill_like_run_test_plan(config_text: str, certs_keys: Path) -> dict:
    """What run-test-plan.py does before it creates the plan: every ``{<file>}`` becomes the content of
    ``certs-keys/<file>`` with newlines turned into spaces, then the text is parsed as JSON."""
    for path in certs_keys.iterdir():
        config_text = config_text.replace("{" + path.name + "}", path.read_text(encoding="utf-8").replace("\n", " "))
    return json.loads(config_text)


def test_certify_config_filled_from_the_staged_keys_is_valid_and_complete(tmp_path):
    pki = tmp_path / "pki"
    pki.mkdir()
    (pki / "suite-mtls-client.crt").write_text(PEM_CERT, encoding="utf-8")
    (pki / "suite-mtls-client.key").write_text(PEM_KEY, encoding="utf-8")
    template = certify_template()

    script = run.stage_scripts(REPO_ROOT, tmp_path / "stage", pki, dict(template.certs_keys))
    config = fill_like_run_test_plan(plans.render_config(template, CERTIFY_RUN_VALUES), script.parent / "certs-keys")

    # PEM text keeps its line breaks although the script flattens the file it reads.
    assert config["mtls"] == config["mtls2"] == {"cert": PEM_CERT, "key": PEM_KEY}
    (key,) = config["client"]["jwks"]["keys"]
    (key2,) = config["client2"]["jwks"]["keys"]
    assert (key["kty"], key["crv"], key["alg"]) == ("EC", "P-256", "ES256") and "d" in key
    assert key["kid"].startswith("client-jwks-") and key2["kid"].startswith("client2-jwks-")
    assert key["d"] != key2["d"]  # each wallet client has its own key


def test_generated_keys_are_new_for_every_run(tmp_path):
    forms = {"client-jwks.json": {"generate": "p256_jwks"}}
    first = run.stage_scripts(REPO_ROOT, tmp_path / "a", tmp_path, forms).parent / "certs-keys" / "client-jwks.json"
    second = run.stage_scripts(REPO_ROOT, tmp_path / "b", tmp_path, forms).parent / "certs-keys" / "client-jwks.json"
    assert first.read_text() != second.read_text()


def test_json_string_form_without_its_source_is_an_environment_error(tmp_path):
    with pytest.raises(run.RunError, match=r"missing \(pki-init writes it\)") as caught:
        run.stage_certs_keys(tmp_path, tmp_path, {"c.json": {"from": "suite-mtls-client.crt", "as": "json_string"}})
    assert caught.value.exit_code is ExitCode.ENVIRONMENT_NOT_READY


def test_unknown_certs_keys_form_is_a_usage_error(tmp_path):
    with pytest.raises(run.RunError, match=r"certs_keys\.k\.json: unknown form") as caught:
        run.stage_certs_keys(tmp_path, tmp_path, {"k.json": {"generate": "rsa_jwks"}})
    assert caught.value.exit_code is ExitCode.USAGE


def test_variant_options_become_a_mapping():
    assert run.variant_overrides(None) == {}
    assert run.variant_overrides(["sender_constrain=mtls", "a=b=c"]) == {"sender_constrain": "mtls", "a": "b=c"}
    assert run.variant_overrides(["a=1", "a=2"]) == {"a": "2"}  # the last one wins


@pytest.mark.parametrize("option", ["sender_constrain", "=mtls", "sender_constrain=", ""])
def test_variant_option_must_be_name_and_value(option):
    with pytest.raises(plans.PlanError, match="--variant expects NAME=VALUE"):
        run.variant_overrides([option])


def test_wait_until_ready_keeps_asking_while_certify_starts():
    answers = iter([CertifyError("issuer metadata: HTTP 502", 502), httpx.ConnectError("refused"), True])

    def check() -> bool:
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    run.wait_until_ready(check, "Inji Certify", timeout_s=30, interval_s=0)
    assert next(answers, None) is None  # all three answers were used


def test_wait_until_ready_reads_the_default_limit_when_called(monkeypatch):
    monkeypatch.setattr(run, "READY_TIMEOUT_S", 0)
    with pytest.raises(run.RunError, match="is not ready after 0 s"):
        run.wait_until_ready(lambda: False, "thing", interval_s=0)


@respx.mock
def test_seed_component_sends_the_rendered_configuration():
    api = f"{CERTIFY}/v1/certify/credential-configurations"
    answers = iter([httpx.Response(404, json={"errors": [{"errorCode": "invalid_request"}]})])
    respx.get(f"{api}/InjiConformanceSdJwtVc").mock(
        side_effect=lambda _request: next(
            answers, httpx.Response(200, json={"credentialConfigKeyId": "InjiConformanceSdJwtVc"})
        )
    )
    add = respx.post(api).mock(return_value=httpx.Response(201, json={"id": "InjiConformanceSdJwtVc"}))

    message = run.seed_component(CertifyClient(CERTIFY), certify_template(), {"target_url": CERTIFY})

    assert message == "seed certify: credential configuration InjiConformanceSdJwtVc created"
    sent = json.loads(add.calls.last.request.content)
    assert sent["credentialConfigKeyId"] == "InjiConformanceSdJwtVc"
    assert (sent["credentialFormat"], sent["signatureAlgo"]) == ("dc+sd-jwt", "ES256")
    assert isinstance(sent["vcTemplate"], str) and "$comment" not in sent


@respx.mock
def test_seed_component_failure_is_an_environment_error():
    respx.get(f"{CERTIFY}/v1/certify/credential-configurations/InjiConformanceSdJwtVc").mock(
        side_effect=httpx.ConnectError("refused")
    )
    with pytest.raises(run.RunError, match="seeding Inji Certify failed") as caught:
        run.seed_component(CertifyClient(CERTIFY), certify_template())
    assert caught.value.exit_code is ExitCode.ENVIRONMENT_NOT_READY


def test_seed_component_needs_a_seed_block():
    verify_template = plans.find_template(REPO_ROOT / "conformance" / "plans", Component.VERIFY)
    with pytest.raises(plans.PlanError, match=r"seed\.credential_configuration is missing"):
        run.seed_component(CertifyClient(CERTIFY), verify_template)


def test_certify_handoff_comes_from_the_template():
    template = certify_template()
    settings = plans.render_handoff(template, CERTIFY_RUN_VALUES)
    (handoff,) = run.component_handoffs(template, settings, None, None, CertifyClient(CERTIFY))  # type: ignore[arg-type]
    assert isinstance(handoff, CredentialOfferHandoff)
    assert handoff.config_id == "InjiConformanceSdJwtVc"
    assert handoff.claims == {"fullName": "Asha Test-Farmer", "dateOfBirth": "1990-01-15", "gender": "Female"}
    assert (handoff.tx_code_length, handoff.expires_in) == (6, 600)
    assert run.component_handoffs(template, settings, None, None, None) == []  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "settings",
    [{}, {"credential_offer": {"claims": {}}}, {"credential_offer": {"credential_configuration_id": "x"}}],
)
def test_incomplete_certify_handoff_block_is_a_plan_error(settings):
    with pytest.raises(plans.PlanError, match="handoff block is incomplete"):
        run.component_handoffs(certify_template(), settings, None, None, CertifyClient(CERTIFY))  # type: ignore[arg-type]


class FakeIssuerSuite(FakeSuite):
    """A plan of three issuer modules: one passed, one failed at the credential request, one never started."""

    def plan(self, plan_id):
        return {
            "modules": [
                {"testModule": "oid4vci-1_0-issuer-metadata-test", "instances": ["m1"]},
                {"testModule": "oid4vci-1_0-issuer-happy-flow", "instances": ["old", "h1"]},
                {"testModule": "oid4vci-1_0-issuer-happy-flow-multiple-clients", "instances": []},
            ]
        }

    def test_info(self, test_id):
        result = "PASSED" if test_id == "m1" else "FAILED"
        return {"status": "FINISHED", "result": result, "variant": {"sender_constrain": "dpop"}}

    def test_log(self, test_id):
        if test_id == "m1":
            return []
        return [
            {"blockId": "b1", "startBlock": True, "msg": "Call credential endpoint", "time": 1791148800000},
            {
                "src": "EnsureHttpStatusCodeIs200or202",
                "blockId": "b1",
                "result": "FAILURE",
                "msg": "invalid_dpop_proof",
                "requirements": ["OID4VCI-1FINAL-8.3"],
                "time": 1791148803000,
            },
        ]


def test_build_results_for_an_issuer_run(tmp_path, schema_dir, capsys):
    template = certify_template()
    folder = tmp_path / "certify"
    (folder / "config").mkdir(parents=True)
    (folder / "exports").mkdir()
    config = folder / "config" / f"{template.name}.json"
    config.write_text("{}", encoding="utf-8")
    responder = Responder(None, "alias", [])  # type: ignore[arg-type]
    for kind, status in ((HandoffKind.CREDENTIAL_OFFER, 204), (HandoffKind.TX_CODE, 204)):
        responder.records.append(
            HandoffRecord("h1", "oid4vci-1_0-issuer-happy-flow", kind, "2026-10-04T19:31:01Z", status, 85.0)
        )
    ctx = run.RunContext(
        run_id="20261004T193000Z-abc123",
        component=Component.CERTIFY,
        track=Track.GATE,
        template=template,
        started_at="2026-01-01T00:00:00Z",
        suite_url="https://localhost.emobix.co.uk:18443",
        suite_version="5.3.1",
        target_url=CERTIFY,
        out=tmp_path,
        folder=folder,
        config_path=config,
        modules=(),  # the whole plan
        no_gate=True,
    )

    results = run.build_results(ctx, FakeIssuerSuite(), None, "PLAN", responder)  # type: ignore[arg-type]

    path = tmp_path / "results.json"
    model.dump(results, path)
    assert model.validate(model.read_json(path), model.DocumentKind.RESULTS, schema_dir) == []
    assert results.component is Component.CERTIFY and results.plan.variant["sender_constrain"] == "dpop"
    metadata, happy, multiple = results.modules
    assert (metadata.verdict.value, metadata.handoffs) == ("conforms", ())  # the metadata module needs no offer
    assert happy.test_id == "h1"  # the latest instance
    assert [h.kind for h in happy.handoffs] == [HandoffKind.CREDENTIAL_OFFER, HandoffKind.TX_CODE]
    assert happy.failures[0].condition == "EnsureHttpStatusCodeIs200or202"
    assert happy.failures[0].block == "Call credential endpoint"
    assert (multiple.status.value, multiple.verdict.value) == ("NOT_STARTED", "regression")
    assert results.gate.exit_code is ExitCode.OK and results.gating is False
    run.print_summary(results, path)
    summary = capsys.readouterr().out
    assert "[credential_offer HTTP 204 85 ms, tx_code HTTP 204 85 ms]" in summary
    assert "(3 modules, gate not applied)" in summary
