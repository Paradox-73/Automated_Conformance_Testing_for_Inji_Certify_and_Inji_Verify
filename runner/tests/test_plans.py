"""Plan templates: loading, rendering into the suite's config format and the run-test-plan.py plan spec."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from inji_conformance import plans
from inji_conformance.model import Component, Track

REPO_ROOT = Path(__file__).resolve().parents[2]
PLANS_DIR = REPO_ROOT / "conformance" / "plans"
RUN_VALUES = {"run_id": "20261004T193000Z-abc123", "target_url": "https://verify.inji.test:18451/v1/verify"}


@pytest.fixture
def verify_template() -> plans.PlanTemplate:
    return plans.find_template(PLANS_DIR, Component.VERIFY, Track.GATE)


def test_verify_template_selects_the_1_0_final_variant(verify_template):
    assert verify_template.plan == "oid4vp-1final-verifier-test-plan"
    assert verify_template.variant == {
        "vp_profile": "plain_vp",
        "credential_format": "sd_jwt_vc",
        "client_id_prefix": "x509_san_dns",
        "request_method": "request_uri_signed",
        "response_mode": "direct_post",
    }


def test_rendered_config_is_the_suite_format_without_keys(verify_template):
    text = plans.render_config(verify_template, RUN_VALUES)
    # The signing key stays a placeholder that run-test-plan.py fills from certs-keys/, written without quotes.
    assert '"signing_jwk": {suite-signing.jwk.json}' in text
    config = json.loads(text.replace("{suite-signing.jwk.json}", '{"kty": "EC"}'))
    assert config["alias"] == "inji-verify-20261004T193000Z-abc123"
    assert config["client"] == {"client_id": "test.example.com"}
    assert "$comment" not in text
    assert config["browser"][0]["match"] == "https://*/test/a/*/verification-evidence"


def test_handoff_block_gets_the_run_values(verify_template):
    handoff = plans.render_handoff(verify_template, RUN_VALUES)["authorization_request"]
    assert handoff["client_id"] == "x509_san_dns:test.example.com"
    assert handoff["dcql_query"]["credentials"][0]["meta"] == {"vct_values": ["urn:eudi:pid:1"]}


def test_expected_review(verify_template):
    assert verify_template.expected_review("oid4vp-1final-verifier-happy-flow") == "valid"
    assert verify_template.expected_review("oid4vp-1final-verifier-invalid-sd-hash") == "invalid"


def test_plan_spec_matches_the_suite_grammar(verify_template):
    spec, config = plans.plan_spec(verify_template, "config/v.json", ["oid4vp-1final-verifier-happy-flow"])
    assert spec == (
        "oid4vp-1final-verifier-test-plan[vp_profile=plain_vp][credential_format=sd_jwt_vc]"
        "[client_id_prefix=x509_san_dns][request_method=request_uri_signed][response_mode=direct_post]"
        ":oid4vp-1final-verifier-happy-flow"
    )
    assert config == "config/v.json"
    assert ":" not in plans.plan_spec(verify_template, "c.json")[0]


def test_plan_spec_parses_with_the_vendored_parser(verify_template):
    pytest.importorskip("pyparsing")
    import importlib.util

    path = REPO_ROOT / "third_party" / "oidf-conformance-suite" / "scripts" / "test_plan_parser.py"
    spec_loader = importlib.util.spec_from_file_location("test_plan_parser", path)
    parser = importlib.util.module_from_spec(spec_loader)
    spec_loader.loader.exec_module(parser)
    line = " ".join(plans.plan_spec(verify_template, "config/verify.x.json", ["m-one", "m_two"]))
    ((tokens, _start, _end),) = list(parser.test_plan.scan_string(line))
    test = tokens[0]["test"]
    assert test["test_name"] == "oid4vp-1final-verifier-test-plan"
    assert test["variants"]["client_id_prefix"] == "x509_san_dns"
    assert test["modules"] == ["m-one", "m_two"]
    assert test["config_file"] == "config/verify.x.json"


@pytest.mark.parametrize("path", ["C:/run/config.json", "my config.json"])
def test_plan_spec_rejects_paths_the_parser_cannot_read(verify_template, path):
    with pytest.raises(plans.PlanError):
        plans.plan_spec(verify_template, path)


def test_unknown_variable_is_an_error(verify_template):
    with pytest.raises(plans.PlanError, match=re.escape("unknown variable ${nope}")):
        plans.substitute({"a": "x ${nope}"}, {"run_id": "1"})


def test_load_rejects_a_bad_variant_value(tmp_path):
    path = tmp_path / "verify.bad.json"
    path.write_text(
        json.dumps({"component": "verify", "plan": "p", "variant": {"a": "b]"}, "config": {}}), encoding="utf-8"
    )
    with pytest.raises(plans.PlanError, match="not a valid variant value"):
        plans.load_template(path)


def test_find_template_needs_exactly_one(tmp_path):
    with pytest.raises(plans.PlanError, match="found none"):
        plans.find_template(tmp_path, Component.VERIFY)
