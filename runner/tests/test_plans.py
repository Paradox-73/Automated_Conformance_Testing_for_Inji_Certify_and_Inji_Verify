"""Plan templates: loading, rendering into the suite's config format and the run-test-plan.py plan spec."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest

from inji_conformance import inji_certify, plans
from inji_conformance.model import Component, Track

REPO_ROOT = Path(__file__).resolve().parents[2]
PLANS_DIR = REPO_ROOT / "conformance" / "plans"
RUN_VALUES = {"run_id": "20261004T193000Z-abc123", "target_url": "https://verify.inji.test:18451/v1/verify"}


X509_TEMPLATE = "verify.oid4vp-1final-verifier-x509-san-dns"


@pytest.fixture
def verify_template() -> plans.PlanTemplate:
    """The x509_san_dns configuration: the one with every kind of template field (client, signed request)."""
    return plans.find_template(PLANS_DIR, Component.VERIFY, Track.GATE, name=X509_TEMPLATE)


def test_default_verify_template_uses_the_redirect_uri_client_id():
    default = plans.find_template(PLANS_DIR, Component.VERIFY, Track.GATE)
    assert default.name == "verify.oid4vp-1final-verifier" and not default.alternative
    assert default.variant == {
        "vp_profile": "plain_vp",
        "credential_format": "sd_jwt_vc",
        "client_id_prefix": "redirect_uri",
        "request_method": "url_query",
        "response_mode": "direct_post",
    }
    handoff = plans.render_handoff(default, RUN_VALUES)["authorization_request"]
    assert handoff["client_id"] == "redirect_uri:https://verify.inji.test:18451/v1/verify/v2/vp-submission/direct-post"
    assert "$comment" not in handoff


def test_alternative_templates_run_only_when_named(tmp_path):
    for name in ("verify.a", "verify.b"):
        data = json.loads((PLANS_DIR / f"{X509_TEMPLATE}.json").read_text(encoding="utf-8"))
        data["alternative"] = name == "verify.b"
        (tmp_path / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    assert plans.find_template(tmp_path, Component.VERIFY).name == "verify.a"
    assert plans.find_template(tmp_path, Component.VERIFY, name="verify.b").name == "verify.b"
    with pytest.raises(plans.PlanError, match=r"no plan template verify\.c\.json .*known: verify\.a, verify\.b"):
        plans.find_template(tmp_path, Component.VERIFY, name="verify.c")
    with pytest.raises(plans.PlanError, match="is a verify gate template"):
        plans.find_template(tmp_path, Component.CERTIFY, name="verify.a")


def test_verify_template_selects_the_1_0_final_variant(verify_template):
    assert verify_template.plan == "oid4vp-1final-verifier-test-plan"
    assert verify_template.alternative
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
    assert config["client"] == {"client_id": "verify.inji.test"}
    assert "$comment" not in text
    # No scripted browser: the responder uploads Inji Verify's verdict into the screenshot placeholder.
    assert "browser" not in config


def test_handoff_block_gets_the_run_values(verify_template):
    handoff = plans.render_handoff(verify_template, RUN_VALUES)["authorization_request"]
    assert handoff["client_id"] == "x509_san_dns:verify.inji.test"
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


def test_plan_spec_parses_with_the_vendored_parser(verify_template, monkeypatch):
    pytest.importorskip("pyparsing")
    import importlib.util
    import sys

    # No __pycache__ next to the vendored script: third_party/reimport.sh check allows no extra file there.
    monkeypatch.setattr(sys, "dont_write_bytecode", True)

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


# --------------------------------------------------------------------------------------------------------------
# The issuer plan template: variant, certs-keys forms, seed block
# --------------------------------------------------------------------------------------------------------------

CERTIFY_RUN_VALUES = {
    "run_id": "20261004T193000Z-abc123",
    "target_url": "https://certify.inji.test:18450",
    "suite_url": "https://localhost.emobix.co.uk:18443",
}


@pytest.fixture
def certify_template() -> plans.PlanTemplate:
    return plans.find_template(PLANS_DIR, Component.CERTIFY, Track.GATE)


def minimal_template(tmp_path: Path, **blocks) -> Path:
    path = tmp_path / "certify.t.json"
    path.write_text(
        json.dumps({"component": "certify", "plan": "p", "variant": {}, "config": {}, **blocks}), encoding="utf-8"
    )
    return path


def test_certify_template_selects_the_pre_authorized_sd_jwt_variant(certify_template):
    assert certify_template.plan == "oid4vci-1_0-issuer-test-plan"
    assert certify_template.variant == {
        "fapi_profile": "vci",
        "credential_format": "sd_jwt_vc",
        "vci_grant_type": "pre_authorization_code",
        "vci_authorization_code_flow_variant": "issuer_initiated",
        "client_auth_type": "private_key_jwt",
        "sender_constrain": "dpop",
        "authorization_request_type": "simple",
        "fapi_request_method": "unsigned",
        "vci_credential_encryption": "plain",
    }
    assert certify_template.modules == ()  # every module of the plan


def test_rendered_certify_config_keeps_every_key_out(certify_template):
    text = plans.render_config(certify_template, CERTIFY_RUN_VALUES)
    filled = text
    for name in certify_template.certs_keys:
        placeholder = "{" + name + "}"
        assert placeholder in text and f'"{placeholder}"' not in text  # unquoted, as the suite expects
        filled = filled.replace(placeholder, "null")
    config = json.loads(filled)
    assert config["alias"] == "inji-certify-20261004T193000Z-abc123"
    assert config["vci"] == {
        "credential_issuer_url": "https://certify.inji.test:18450",
        "credential_configuration_id": "InjiConformanceSdJwtVc",
    }
    assert config["client"]["client_id"] != config["client2"]["client_id"]
    assert "$comment" not in text and "PRIVATE KEY" not in text


def test_certify_handoff_block_names_the_seeded_configuration(certify_template):
    offer = plans.render_handoff(certify_template, CERTIFY_RUN_VALUES)["credential_offer"]
    seed = plans.render_seed(certify_template)["credential_configuration"]
    assert offer["credential_configuration_id"] == seed["credentialConfigKeyId"] == "InjiConformanceSdJwtVc"
    # Inji Certify refuses an offer whose claims differ from the configuration's claims.
    assert set(offer["claims"]) == set(seed["vcTemplate"]) == set(seed["sdJwtClaims"])
    assert 4 <= offer["tx_code_length"] <= 8 and 60 <= offer["expires_in"] <= 86400


def test_seed_block_is_rendered_but_the_credential_template_is_kept(certify_template):
    seed = plans.render_seed(certify_template, {"target_url": CERTIFY_RUN_VALUES["target_url"]})
    definition = seed["credential_configuration"]
    assert definition["credentialConfigKeyId"] == "InjiConformanceSdJwtVc"
    assert "$comment" not in definition
    # ${fullName} is a placeholder of Inji Certify's template engine, not one of ours.
    assert definition["vcTemplate"] == {
        "fullName": "${fullName}",
        "dateOfBirth": "${dateOfBirth}",
        "gender": "${gender}",
    }
    request = inji_certify.configuration_request(definition)
    assert json.loads(base64.b64decode(request["vcTemplate"])) == definition["vcTemplate"]
    assert "${" not in json.dumps({key: value for key, value in request.items() if key != "vcTemplate"})


def test_seed_block_with_an_unknown_variable_is_an_error(tmp_path):
    template = plans.load_template(
        minimal_template(tmp_path, seed={"credential_configuration": {"credentialConfigKeyId": "${nope}"}})
    )
    with pytest.raises(plans.PlanError, match=re.escape("unknown variable ${nope}")):
        plans.render_seed(template)


def test_template_without_a_seed_block_renders_none(verify_template):
    assert plans.render_seed(verify_template) == {}


def test_with_variant_replaces_and_adds_values(certify_template):
    changed = plans.with_variant(certify_template, {"sender_constrain": "mtls", "extra_option": "on"})
    assert changed.variant["sender_constrain"] == "mtls" and changed.variant["extra_option"] == "on"
    assert certify_template.variant["sender_constrain"] == "dpop"  # the loaded template is not changed
    assert "[sender_constrain=mtls]" in plans.plan_spec(changed, "config/c.json")[0]
    assert plans.with_variant(certify_template, {}).variant == certify_template.variant


@pytest.mark.parametrize("overrides", [{"sender constrain": "mtls"}, {"sender_constrain": "mt]ls"}, {"a": ""}])
def test_with_variant_rejects_what_the_plan_spec_cannot_carry(certify_template, overrides):
    with pytest.raises(plans.PlanError, match="not a valid variant name and value"):
        plans.with_variant(certify_template, overrides)


@pytest.mark.parametrize(
    "source",
    ["suite-signing.jwk.json", {"from": "suite-mtls-client.crt", "as": "json_string"}, {"generate": "p256_jwks"}],
)
def test_certs_keys_forms_are_accepted(tmp_path, source):
    template = plans.load_template(minimal_template(tmp_path, certs_keys={"key.json": source}))
    assert template.certs_keys == {"key.json": source}


@pytest.mark.parametrize(
    ("target", "source"),
    [
        ("key.json", {"from": "a.crt", "as": "base64"}),
        ("key.json", {"from": "a.crt"}),
        ("key.json", {"from": 7, "as": "json_string"}),
        ("key.json", {"generate": "rsa_jwks"}),
        ("key.json", {"generate": "p256_jwks", "as": "json_string"}),
        ("key.json", 7),
        ("../key.json", "a.json"),
        ("sub/key.json", {"generate": "p256_jwks"}),
    ],
)
def test_certs_keys_entries_of_another_form_are_rejected(tmp_path, target, source):
    with pytest.raises(plans.PlanError, match="certs_keys"):
        plans.load_template(minimal_template(tmp_path, certs_keys={target: source}))
