"""Turn a finished plan into ``results.json`` v1: module outcomes from the suite, handoffs from the responder.

The suite is the source of truth for status, result and log entries (``/api/plan``, ``/api/info``, ``/api/log``).
Verdicts here use the verdict table in ``conformance/schema/README.md`` without a benchmark: every problem is a
regression. Applying the benchmark is the job of the gate.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from inji_conformance.handoff import HandoffRecord
from inji_conformance.model import (
    Failure,
    Handoff,
    Links,
    ModuleResult,
    ModuleStatus,
    Review,
    ReviewOutcome,
    Severity,
    SuiteResult,
    Verdict,
)

_CONDITION = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def condition_name(src: str) -> str:
    """A log entry's ``src`` as a condition name: the condition class, or the test name for test-level entries."""
    if _CONDITION.match(src):
        return src
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", src) or "unknown"
    return cleaned if _CONDITION.match(cleaned) else f"_{cleaned}"


def failures_from_log(entries: Sequence[Mapping[str, Any]]) -> list[Failure]:
    """Every FAILURE and WARNING entry, with the title of the block it ran in."""
    blocks = {
        entry.get("blockId"): str(entry.get("msg", ""))
        for entry in entries
        if entry.get("startBlock") and entry.get("blockId")
    }
    failures = []
    for entry in entries:
        result = entry.get("result")
        if result not in ("FAILURE", "WARNING"):
            continue
        failures.append(
            Failure(
                condition=condition_name(str(entry.get("src", ""))),
                severity=Severity(result),
                message=str(entry.get("msg", "")),
                block=blocks.get(entry.get("blockId"), ""),
                requirements=tuple(str(r) for r in entry.get("requirements") or ()),
                expected=False,
            )
        )
    return failures


def _status(value: Any) -> ModuleStatus:
    try:
        return ModuleStatus(str(value))
    except ValueError:
        return ModuleStatus.UNKNOWN


def _result(value: Any) -> SuiteResult | None:
    if value in (None, ""):
        return None
    try:
        return SuiteResult(str(value))
    except ValueError:
        return SuiteResult.UNKNOWN


def verdict_without_benchmark(
    status: ModuleStatus, result: SuiteResult | None, failures: Sequence[Failure], review: Review | None
) -> tuple[Verdict, str | None]:
    """Verdict and reason when no benchmark entry applies."""
    interrupted_by_failure = (
        status is ModuleStatus.INTERRUPTED
        and result is SuiteResult.FAILED
        and any(f.severity is Severity.FAILURE for f in failures)
    )
    if status is not ModuleStatus.FINISHED and not interrupted_by_failure:
        if status is ModuleStatus.NOT_STARTED:
            return Verdict.REGRESSION, "the module never started"
        return Verdict.REGRESSION, f"the module ended in status {status.value}: handoff not delivered or timeout"
    if result is SuiteResult.PASSED:
        return Verdict.CONFORMS, None
    if result is SuiteResult.REVIEW and review is not None and review.confirmed:
        return Verdict.CONFORMS, None
    if result is SuiteResult.REVIEW:
        observed = review.observed.value if review else ReviewOutcome.MISSING.value
        return Verdict.REGRESSION, (
            f"result REVIEW: Inji Verify's verdict was {observed}, and no evidence image of it was uploaded, "
            "so the review is not confirmed"
        )
    if result in (SuiteResult.FAILED, SuiteResult.WARNING):
        names = ", ".join(sorted({f.condition for f in failures})) or "no logged condition"
        return Verdict.REGRESSION, f"result {result.value}: {names}"
    if result is SuiteResult.SKIPPED:
        return Verdict.REGRESSION, "the suite skipped the module and no benchmark entry expects that"
    return Verdict.REGRESSION, f"result {result.value if result else 'none'}"


def module_result(
    name: str,
    test_id: str | None,
    info: Mapping[str, Any] | None,
    log: Sequence[Mapping[str, Any]],
    handoffs: Sequence[HandoffRecord],
    *,
    suite_log_url: str | None,
    review: Review | None = None,
    duration_s: float | None = None,
) -> ModuleResult:
    """One ``modules[]`` entry of results.json."""
    if test_id is None or info is None:
        status, result = ModuleStatus.NOT_STARTED, None
    else:
        status, result = _status(info.get("status")), _result(info.get("result"))
    failures = failures_from_log(log)
    verdict, reason = verdict_without_benchmark(status, result, failures, review)
    variant = info.get("variant") if info else None
    return ModuleResult(
        name=name,
        test_id=test_id,
        status=status,
        result=result,
        verdict=verdict,
        verdict_reason=reason,
        description=str(info["description"]) if info and info.get("description") else None,
        variant={str(k): str(v) for k, v in variant.items()} if isinstance(variant, Mapping) and variant else None,
        failures=tuple(failures),
        review=review if result is SuiteResult.REVIEW else None,
        handoffs=tuple(
            Handoff(
                kind=record.kind,
                http_status=record.http_status,
                duration_ms=record.duration_ms,
                at=record.at,
                detail=record.detail or None,
                error=record.error,
            )
            for record in handoffs
        ),
        links=Links(suite_log=suite_log_url) if suite_log_url else None,
        duration_s=duration_s,
    )


def review_from_vp_result(expected: str, vp_result: Mapping[str, Any] | None) -> Review:
    """What Inji Verify reported for the presentation (``GET /vp-result``), against what the module expects.

    No evidence image yet: the suite's own evidence page fills the screenshot placeholder for now.
    """
    if not vp_result or "vpResultStatus" not in vp_result:
        observed = ReviewOutcome.MISSING
    elif vp_result["vpResultStatus"] == "SUCCESS":
        observed = ReviewOutcome.VALID
    else:
        observed = ReviewOutcome.INVALID
    return Review(expected=ReviewOutcome(expected), observed=observed, evidence=None)


def plan_modules(plan: Mapping[str, Any], selected: Sequence[str] | None) -> list[tuple[str, str | None]]:
    """``(module name, latest test id or None)`` for each module of the plan, limited to ``selected``."""
    out = []
    for module in plan.get("modules") or []:
        name = str(module.get("testModule"))
        if selected and name not in selected:
            continue
        instances = module.get("instances") or []
        out.append((name, str(instances[-1]) if instances else None))
    return out


def transaction_id(handoffs: Sequence[HandoffRecord]) -> str | None:
    """Inji Verify's transaction id of the last delivered authorization request."""
    for record in reversed(handoffs):
        if record.data.get("transaction_id"):
            return record.data["transaction_id"]
    return None
