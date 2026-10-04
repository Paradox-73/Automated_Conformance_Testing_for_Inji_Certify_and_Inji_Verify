"""The example files in conformance/schema/examples: valid ones validate, *.invalid.json ones are rejected, and the
results examples list exactly the modules the suite creates for the chosen plan variants."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inji_conformance import model
from inji_conformance.model import DocumentKind, Verdict

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "conformance" / "schema" / "examples"
VALID = sorted(p.name for p in EXAMPLES_DIR.glob("*.json") if not p.name.endswith(".invalid.json"))
INVALID = sorted(p.name for p in EXAMPLES_DIR.glob("*.invalid.json"))

# Modules of oid4vci-1_0-issuer-test-plan for the variant set fapi_profile=vci, credential_format=sd_jwt_vc,
# client_auth_type=private_key_jwt, sender_constrain=dpop, vci_grant_type=pre_authorization_code,
# vci_authorization_code_flow_variant=issuer_initiated, authorization_request_type=simple,
# fapi_request_method=unsigned, vci_credential_encryption=plain. Listed by the suite (release-v5.3.1) when the plan
# was created on 2026-10-04.
CERTIFY_MODULES = [
    "oid4vci-1_0-issuer-metadata-test",
    "oid4vci-1_0-issuer-metadata-test-signed",
    "oid4vci-1_0-issuer-happy-flow",
    "oid4vci-1_0-issuer-happy-flow-additional-requests",
    "oid4vci-1_0-issuer-happy-flow-multiple-clients",
    "oid4vci-1_0-issuer-happy-flow-skip-notification",
    "oid4vci-1_0-issuer-batch-issuance",
    "oid4vci-1_0-issuer-fail-invalid-nonce",
    "oid4vci-1_0-issuer-fail-invalid-jwt-proof-signature",
    "oid4vci-1_0-issuer-fail-invalid-key-attestation-signature",
    "oid4vci-1_0-issuer-fail-missing-proof",
    "oid4vci-1_0-issuer-fail-unsupported-encryption-algorithm",
    "oid4vci-1_0-issuer-fail-unknown-credential-configuration",
    "oid4vci-1_0-issuer-fail-unknown-credential-identifier",
    "oid4vci-1_0-issuer-fail-on-access-token-in-query",
]

# Modules of oid4vp-1final-verifier-test-plan for vp_profile=plain_vp, credential_format=sd_jwt_vc,
# client_id_prefix=x509_san_dns, request_method=request_uri_signed, response_mode=direct_post. Not measured yet: the
# plan created on 2026-10-04 used redirect_uri / url_query and listed the ten modules below without
# request-uri-fetched-twice, which the suite marks not applicable only to url_query
# (VP1FinalVerifierRequestUriFetchedTwice.java, @VariantNotApplicable). invalid-session-transcript is marked not
# applicable to sd_jwt_vc, so it is absent from both lists.
VERIFY_MODULES = [
    "oid4vp-1final-verifier-happy-flow",
    "oid4vp-1final-verifier-minimal-cnf-jwk",
    "oid4vp-1final-verifier-request-uri-method-post",
    "oid4vp-1final-verifier-request-uri-fetched-twice",
    "oid4vp-1final-verifier-invalid-kb-jwt-signature",
    "oid4vp-1final-verifier-invalid-credential-signature",
    "oid4vp-1final-verifier-invalid-sd-hash",
    "oid4vp-1final-verifier-invalid-kb-jwt-nonce",
    "oid4vp-1final-verifier-invalid-kb-jwt-aud",
    "oid4vp-1final-verifier-kb-jwt-iat-in-past",
    "oid4vp-1final-verifier-kb-jwt-iat-in-future",
]


def _load(name: str):
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def test_there_are_valid_and_invalid_examples():
    assert "results-verify.example.json" in VALID
    assert INVALID, "keep at least one *.invalid.json so the check proves the validator rejects bad input"


@pytest.mark.parametrize("name", VALID)
def test_valid_example_validates(name):
    data = _load(name)
    kind = model.detect_kind(name, data)
    assert kind is not None
    assert model.validate(data, kind) == []


@pytest.mark.parametrize("name", INVALID)
def test_invalid_example_is_rejected(name):
    data = _load(name)
    kind = model.detect_kind(name, data)
    assert kind is not None
    assert model.validate(data, kind), f"{name} should be rejected"


@pytest.mark.parametrize(
    ("component", "expected"),
    [("certify", CERTIFY_MODULES), ("verify", VERIFY_MODULES)],
)
@pytest.mark.parametrize("variant", ["", "-regression"])
def test_results_examples_list_the_plan_modules_in_suite_order(component, expected, variant):
    results = model.load_results(EXAMPLES_DIR / f"results-{component}{variant}.example.json")
    assert [m.name for m in results.modules] == expected


@pytest.mark.parametrize("component", ["certify", "verify"])
def test_clean_examples_pass_the_gate_and_regression_examples_fail_it(component):
    clean = model.load_results(EXAMPLES_DIR / f"results-{component}.example.json")
    regression = model.load_results(EXAMPLES_DIR / f"results-{component}-regression.example.json")
    assert clean.gate.passed and clean.gate.exit_code == model.ExitCode.OK
    assert not regression.gate.passed and regression.gate.exit_code == model.ExitCode.GATE_FAILED
    assert any(m.fails_gate for m in regression.modules)


@pytest.mark.parametrize("component", ["certify", "verify"])
def test_benchmark_references_in_results_come_from_the_benchmark_examples(component):
    """Every benchmark entry a results example cites exists, unchanged, in that component's benchmark example."""
    entries = []
    for kind in (DocumentKind.EXPECTED_FAILURES, DocumentKind.EXPECTED_SKIPS):
        entries += model.load_benchmark(EXAMPLES_DIR / f"{component}.{kind.value}.example.json")
    listed = {(e.comment, e.owner, e.spec, e.issue) for e in entries}
    for variant in ("", "-regression"):
        results = model.load_results(EXAMPLES_DIR / f"results-{component}{variant}.example.json")
        for module in results.modules:
            for ref in module.benchmark:
                assert (ref.comment, ref.owner, ref.spec, ref.issue) in listed, module.name


def test_examples_cover_every_verdict():
    seen = set()
    for name in VALID:
        if name.startswith("results-"):
            seen |= {m.verdict for m in model.load_results(EXAMPLES_DIR / name).modules}
    assert seen == set(Verdict)
