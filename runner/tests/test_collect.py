"""Building results.json entries from suite data: failures, verdicts and review."""

from __future__ import annotations

import pytest

from inji_conformance.collect import (
    condition_name,
    failures_from_log,
    module_result,
    plan_modules,
    review_from_vp_result,
    transaction_id,
)
from inji_conformance.handoff import HandoffRecord
from inji_conformance.model import HandoffKind, ModuleStatus, Review, ReviewOutcome, SuiteResult, Verdict

LOG = [
    {"startBlock": True, "blockId": "b1", "msg": "Authorization endpoint"},
    {"src": "EnsureMatchingClientId", "result": "SUCCESS", "blockId": "b1", "msg": "ok"},
    {
        "src": "VP1FinalValidateVpFormatsSupportedInClientMetadata",
        "result": "FAILURE",
        "blockId": "b1",
        "msg": "vp_formats_supported missing",
        "requirements": ["OID4VP-1FINAL-11.1"],
    },
    {"src": "oid4vp-1final-verifier-happy-flow", "result": "WARNING", "msg": "test-level warning"},
]


def test_failures_keep_condition_block_and_requirements():
    failures = failures_from_log(LOG)
    assert [(f.condition, f.severity.value, f.block) for f in failures] == [
        ("VP1FinalValidateVpFormatsSupportedInClientMetadata", "FAILURE", "Authorization endpoint"),
        ("oid4vp_1final_verifier_happy_flow", "WARNING", ""),
    ]
    assert failures[0].requirements == ("OID4VP-1FINAL-11.1",)


@pytest.mark.parametrize(("src", "name"), [("Abc_1", "Abc_1"), ("a-b", "a_b"), ("1x", "_1x"), ("", "unknown")])
def test_condition_name(src, name):
    assert condition_name(src) == name


def record(status=302, tx="tx1") -> HandoffRecord:
    return HandoffRecord(
        "t1",
        "m",
        HandoffKind.AUTHORIZATION_REQUEST,
        "2026-10-04T19:31:05Z",
        status,
        12.5,
        detail="d",
        data={"transaction_id": tx},
    )


def test_passed_module_conforms_and_carries_handoffs():
    module = module_result("m", "t1", {"status": "FINISHED", "result": "PASSED"}, [], [record()], suite_log_url="u")
    assert (module.status, module.result, module.verdict) == (
        ModuleStatus.FINISHED,
        SuiteResult.PASSED,
        Verdict.CONFORMS,
    )
    assert module.handoffs[0].http_status == 302
    assert module.links.suite_log == "u"


def test_review_without_evidence_is_not_confirmed():
    review = review_from_vp_result("valid", {"vpResultStatus": "SUCCESS"})
    module = module_result(
        "m", "t1", {"status": "FINISHED", "result": "REVIEW"}, [], [], suite_log_url=None, review=review
    )
    assert review.observed is ReviewOutcome.VALID
    assert module.verdict is Verdict.REGRESSION
    assert "no evidence image" in module.verdict_reason


def test_confirmed_review_conforms():
    review = Review(ReviewOutcome.VALID, ReviewOutcome.VALID, "evidence/t1.png")
    module = module_result(
        "m", "t1", {"status": "FINISHED", "result": "REVIEW"}, [], [], suite_log_url=None, review=review
    )
    assert module.verdict is Verdict.CONFORMS


@pytest.mark.parametrize(
    ("info", "reason"),
    [
        (None, "never started"),
        ({"status": "INTERRUPTED", "result": "FAILED"}, "status INTERRUPTED"),
        (
            {"status": "FINISHED", "result": "FAILED"},
            "result FAILED: VP1FinalValidateVpFormatsSupportedInClientMetadata",
        ),
        ({"status": "FINISHED", "result": "SKIPPED"}, "skipped"),
    ],
)
def test_problems_are_regressions_with_a_reason(info, reason):
    module = module_result("m", "t1" if info else None, info, LOG if info else [], [], suite_log_url=None)
    assert module.verdict is Verdict.REGRESSION
    assert reason in module.verdict_reason


def test_review_outcomes():
    assert review_from_vp_result("invalid", {"vpResultStatus": "INVALID"}).observed is ReviewOutcome.INVALID
    assert review_from_vp_result("valid", None).observed is ReviewOutcome.MISSING


def test_plan_modules_takes_the_latest_instance_of_the_selected_modules():
    plan = {"modules": [{"testModule": "a", "instances": ["1", "2"]}, {"testModule": "b", "instances": []}]}
    assert plan_modules(plan, None) == [("a", "2"), ("b", None)]
    assert plan_modules(plan, ["b"]) == [("b", None)]


def test_transaction_id_of_the_last_delivery():
    assert transaction_id([record(tx="a"), record(tx="b")]) == "b"
    assert transaction_id([]) is None
