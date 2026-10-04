"""Comparing two runs: what counts as a change, new regressions, context, exit codes and the text output."""

from __future__ import annotations

from inji_conformance.model import ExitCode
from inji_conformance.report.diff import Change, diff_runs, format_text
from inji_conformance.report.runs import load_run

HAPPY = "oid4vci-1_0-issuer-happy-flow"
NONCE = "oid4vp-1final-verifier-invalid-kb-jwt-nonce"
UNKNOWN_CONFIG = "oid4vci-1_0-issuer-fail-unknown-credential-configuration"
FETCHED_TWICE = "oid4vp-1final-verifier-request-uri-fetched-twice"


def _by_name(result):
    return {item.name: item for item in result.differences}


def test_a_run_compared_with_itself_is_the_same(run_a):
    result = diff_runs(load_run(run_a), load_run(run_a))
    assert result.same and not result.differences and not result.context
    assert result.counts()["unchanged"] == 26
    assert result.exit_code() == ExitCode.OK
    assert result.exit_code(strict=True) == ExitCode.OK


def test_new_regressions_from_a_to_b(run_a, run_b):
    result = diff_runs(load_run(run_a), load_run(run_b))
    changes = _by_name(result)
    assert set(changes) == {HAPPY, NONCE, UNKNOWN_CONFIG, FETCHED_TWICE}
    assert changes[FETCHED_TWICE].change is Change.REMOVED
    assert {item.name for item in result.new_regressions} == {HAPPY, NONCE}
    assert changes[HAPPY].conditions_added == (("EnsureHttpStatusCodeIs200", "FAILURE"),)
    assert changes[UNKNOWN_CONFIG].conditions_removed == (("VCIValidateCredentialErrorResponse", "FAILURE"),)
    # new regressions sort first
    assert {item.name for item in result.differences[:2]} == {HAPPY, NONCE}
    assert result.exit_code() == ExitCode.DIFF_CHANGED
    assert result.exit_code(strict=True) == ExitCode.GATE_FAILED


def test_fixes_from_b_to_a_do_not_fail_strict(run_a, run_b):
    result = diff_runs(load_run(run_b), load_run(run_a))
    changes = _by_name(result)
    assert changes[FETCHED_TWICE].change is Change.ADDED
    assert {item.name for item in result.fixed} == {HAPPY, NONCE}
    assert not result.new_regressions
    assert result.exit_code() == ExitCode.DIFF_CHANGED
    assert result.exit_code(strict=True) == ExitCode.OK


def test_context_lists_what_ran_differently(run_a, run_b):
    context = {item.subject: (item.before, item.after) for item in diff_runs(load_run(run_a), load_run(run_b)).context}
    assert context["harness commit"] == ("1a2b3c4", "9f8e7d6")
    assert context["verify-service commit"] == ("ad3595f", "0bd41e2")
    assert context["verify target commit"] == ("ad3595f", "0bd41e2")
    assert "certify target commit" not in context


def test_timings_and_links_never_count(copied_runs, edit_json):
    results = copied_runs / "run-b" / "verify" / "results.json"
    reference = load_run(results)

    def retime(data):
        for module in data["modules"]:
            module["duration_s"] = 99.0
            module["test_id"] = "other" + module["test_id"]
            module["links"] = {"suite_log": "https://suite.example/log-detail.html?log=x"}

    edit_json(results, retime)
    assert diff_runs(reference, load_run(results)).same


def test_a_new_failing_condition_alone_is_a_change(copied_runs, edit_json):
    results = copied_runs / "run-a" / "verify" / "results.json"
    reference = load_run(results)

    def add_warning(data):
        module = next(m for m in data["modules"] if m["verdict"] == "known_gap")
        extra = dict(module["failures"][0], condition="CheckForUnexpectedParameters", severity="WARNING")
        module["failures"].append(extra)

    edit_json(results, add_warning)
    result = diff_runs(reference, load_run(results))
    assert [item.change for item in result.differences] == [Change.CHANGED]
    assert result.differences[0].conditions_added == (("CheckForUnexpectedParameters", "WARNING"),)
    assert not result.new_regressions


def test_a_component_only_in_one_run(run_a):
    result = diff_runs(load_run(run_a / "verify"), load_run(run_a))
    assert result.counts()["added"] == 15
    assert any(item.subject == "certify results" for item in result.context)


def test_text_names_every_changed_module_and_the_total(run_a, run_b):
    text = format_text(diff_runs(load_run(run_a), load_run(run_b)))
    for name in (HAPPY, NONCE, UNKNOWN_CONFIG, FETCHED_TWICE):
        assert name in text
    assert "NEW REGRESSION" in text
    assert text.splitlines()[-1] == (
        "result: changed; 3 changed, 0 added, 1 removed, 22 unchanged; 2 new regressions, 0 fixed"
    )


def test_json_form(run_a, run_b):
    data = diff_runs(load_run(run_a), load_run(run_b)).to_dict()
    assert data["same"] is False and data["counts"]["new_regressions"] == 2
    happy = next(item for item in data["modules"] if item["module"] == HAPPY)
    assert happy["before"]["verdict"] == "conforms" and happy["after"]["verdict"] == "regression"
    assert happy["new_regression"] is True
