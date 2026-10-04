"""inji_conformance.model: loading, round trips and the rules beyond the JSON Schemas."""

from __future__ import annotations

import json

import pytest

from inji_conformance import model
from inji_conformance.model import (
    ContractError,
    DocumentKind,
    ExitCode,
    ModuleResult,
    Results,
    ReviewOutcome,
    SchemaNotFoundError,
    Summary,
    Verdict,
)


def _module(results, suffix):
    (module,) = [m for m in results["modules"] if m["name"].endswith(suffix)]
    return module


def _paths(issues):
    return [issue.path for issue in issues]


def _resync(results):
    """Recompute summary and gate from the modules, as the runner would, so a test changes one thing only."""
    summary = Summary.of(Results.from_dict(results).modules)
    results["summary"] = summary.to_dict()
    failing = summary.regression + (0 if results["gate"].get("allow_stale") else summary.stale_benchmark)
    results["gate"]["passed"] = failing == 0
    results["gate"]["exit_code"] = 0 if failing == 0 else 1
    return results


# --------------------------------------------------------------------------------------------------------------
# Loading and round trips
# --------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "results-verify.example.json",
        "results-verify-regression.example.json",
        "results-certify.example.json",
        "results-certify-regression.example.json",
        "run-manifest.example.json",
    ],
)
def test_load_then_to_dict_gives_back_the_file(examples_dir, name):
    original = json.loads((examples_dir / name).read_text(encoding="utf-8"))
    assert model.load(examples_dir / name).to_dict() == original


@pytest.mark.parametrize("name", ["certify.expected-failures.example.json", "certify.expected-skips.example.json"])
def test_benchmark_entries_round_trip_with_the_suite_key_names(examples_dir, name):
    original = json.loads((examples_dir / name).read_text(encoding="utf-8"))
    entries = model.load_benchmark(examples_dir / name)
    assert [entry.to_dict() for entry in entries] == original
    assert "test-name" in entries[0].to_dict()


def test_loaded_results_are_typed(examples_dir):
    results = model.load_results(examples_dir / "results-verify.example.json")
    happy = results.module("oid4vp-1final-verifier-happy-flow")
    assert results.component is model.Component.VERIFY
    assert happy.result is model.SuiteResult.REVIEW
    assert happy.review is not None and happy.review.expected is ReviewOutcome.VALID and happy.review.confirmed
    assert happy.handoffs[0].kind is model.HandoffKind.AUTHORIZATION_REQUEST
    assert results.gate.exit_code is ExitCode.OK
    with pytest.raises(KeyError):
        results.module("no-such-module")


def test_summary_of_counts_each_verdict():
    modules = [
        ModuleResult(name="a", status=model.ModuleStatus.FINISHED, verdict=Verdict.CONFORMS),
        ModuleResult(name="b", status=model.ModuleStatus.FINISHED, verdict=Verdict.CONFORMS),
        ModuleResult(name="c", status=model.ModuleStatus.INTERRUPTED, verdict=Verdict.REGRESSION),
    ]
    summary = Summary.of(modules)
    assert (summary.total, summary.conforms, summary.regression, summary.known_gap) == (3, 2, 1, 0)


def test_new_module_serialises_required_null_fields():
    data = ModuleResult(name="x", verdict=Verdict.REGRESSION, verdict_reason="timeout").to_dict()
    assert data["test_id"] is None and data["result"] is None
    assert data["failures"] == [] and data["handoffs"] == []
    assert "review" not in data and "links" not in data


def test_dump_writes_lf_json_that_loads_again(tmp_path, examples_dir):
    results = model.load_results(examples_dir / "results-certify.example.json")
    target = tmp_path / "results.json"
    model.dump(results, target)
    raw = target.read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"}\n")
    assert model.load_results(target) == results


# --------------------------------------------------------------------------------------------------------------
# Kind detection, errors and the schema folder
# --------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "data", "kind"),
    [
        ("verify.expected-failures.json", [], DocumentKind.EXPECTED_FAILURES),
        ("certify.expected-skips.json", [], DocumentKind.EXPECTED_SKIPS),
        ("manifest.json", {}, DocumentKind.RUN_MANIFEST),
        ("results.json", {}, DocumentKind.RESULTS),
        ("out.json", {"modules": []}, DocumentKind.RESULTS),
        ("out.json", {"components": []}, DocumentKind.RUN_MANIFEST),
        ("out.json", [{"test-name": "x", "condition": "C"}], DocumentKind.EXPECTED_FAILURES),
        ("out.json", [{"test-name": "x"}], DocumentKind.EXPECTED_SKIPS),
        ("out.json", [], None),
        ("out.json", "text", None),
    ],
)
def test_detect_kind(name, data, kind):
    assert model.detect_kind(name, data) is kind


def test_load_raises_contract_error_listing_every_problem(tmp_path, verify_results):
    verify_results["modules"][0]["verdict"] = "passed"
    verify_results["component"] = "wallet"
    path = tmp_path / "results.json"
    path.write_text(json.dumps(verify_results), encoding="utf-8")
    with pytest.raises(ContractError) as caught:
        model.load_results(path)
    assert _paths(caught.value.issues) == ["$.component", "$.modules[0].verdict"]
    assert "results.json is not valid as results" in str(caught.value)


def test_load_benchmark_refuses_other_files(examples_dir):
    with pytest.raises(ContractError, match="not a benchmark file"):
        model.load_benchmark(examples_dir / "results-verify.example.json")


def test_schema_folder_from_environment(monkeypatch, schema_dir, tmp_path):
    monkeypatch.setenv(model.SCHEMA_DIR_ENV, str(schema_dir))
    assert model.find_schema_dir() == schema_dir
    monkeypatch.setenv(model.SCHEMA_DIR_ENV, str(tmp_path))
    with pytest.raises(SchemaNotFoundError, match=r"results\.schema\.json"):
        model.find_schema_dir()


def test_schema_folder_found_from_the_checkout(monkeypatch, schema_dir):
    monkeypatch.delenv(model.SCHEMA_DIR_ENV, raising=False)
    assert model.find_schema_dir().resolve() == schema_dir.resolve()


def test_every_schema_is_a_valid_draft_2020_12_schema(schema_dir):
    import jsonschema

    for name in model.SCHEMA_FILES:
        schema = json.loads((schema_dir / name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        assert schema["$id"].startswith("urn:inji-conformance:schema:")


# --------------------------------------------------------------------------------------------------------------
# Schema rules
# --------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["../outside.html", "/abs/path.html", "C:/x/y.html", "exports\\a.html", " lead"])
def test_relative_paths_stay_inside_the_run_folder(verify_results, path):
    verify_results["modules"][0]["links"]["export"] = path
    assert _paths(model.validate(verify_results, DocumentKind.RESULTS)) == ["$.modules[0].links.export"]


def test_results_benchmark_owner_uses_the_benchmark_schema_enum(certify_results):
    gap = _module(certify_results, "fail-unknown-credential-configuration")
    gap["benchmark"][0]["owner"] = "nobody"
    issues = model.validate(certify_results, DocumentKind.RESULTS)
    assert _paths(issues) == ["$.modules[12].benchmark[0].owner"]


def test_timestamps_need_a_time_zone(verify_results):
    verify_results["started_at"] = "2026-10-04T19:30:00"
    assert _paths(model.validate(verify_results, DocumentKind.RESULTS)) == ["$.started_at"]


@pytest.fixture
def expected_failure(load_example):
    return load_example("certify.expected-failures.example.json")[0]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("comment", "short"),
        ("comment", "          "),
        ("owner", "team"),
        ("spec", ""),
        ("issue", "see the ticket"),
        ("issue", "http://example.org/1"),
        ("variant", {}),
        ("expected-result", "error"),
        ("condition", "Not A Class"),
    ],
)
def test_benchmark_field_rules(expected_failure, field, value):
    expected_failure[field] = value
    assert model.validate([expected_failure], DocumentKind.EXPECTED_FAILURES), field


@pytest.mark.parametrize("field", ["comment", "owner", "spec", "issue", "current-block", "variant"])
def test_benchmark_required_fields(expected_failure, field):
    del expected_failure[field]
    assert model.validate([expected_failure], DocumentKind.EXPECTED_FAILURES), field


def test_benchmark_issue_may_be_a_draft_or_an_https_url(expected_failure):
    for issue in ("docs/findings/a-b.md", "docs/findings/a.md#section", "https://github.com/inji/inji-verify/issues/1"):
        expected_failure["issue"] = issue
        assert model.validate([expected_failure], DocumentKind.EXPECTED_FAILURES) == [], issue


def test_skip_entries_cannot_carry_conditions(load_example):
    skip = load_example("certify.expected-skips.example.json")[0]
    skip["condition"] = "EnsureHttpStatusCodeIs200"
    assert model.validate([skip], DocumentKind.EXPECTED_SKIPS)


def test_variant_object_matches_part_of_a_variant(expected_failure):
    expected_failure["variant"] = {"sender_constrain": "dpop"}
    assert model.validate([expected_failure], DocumentKind.EXPECTED_FAILURES) == []


def test_duplicate_benchmark_entries_are_rejected(expected_failure):
    issues = model.validate([expected_failure, dict(expected_failure)], DocumentKind.EXPECTED_FAILURES)
    assert _paths(issues) == ["$[1]"]


# --------------------------------------------------------------------------------------------------------------
# Rules beyond the schema: results
# --------------------------------------------------------------------------------------------------------------


def test_summary_must_match_the_modules(verify_results):
    verify_results["summary"]["total"] = 12
    assert _paths(model.validate(verify_results, DocumentKind.RESULTS)) == ["$.summary.total"]


def test_duplicate_module_names_are_rejected(verify_results):
    verify_results["modules"][1]["name"] = verify_results["modules"][0]["name"]
    issues = model.validate(verify_results, DocumentKind.RESULTS)
    assert "$.modules[1].name" in _paths(issues)


def test_gate_passed_must_match_exit_code(verify_results):
    verify_results["gate"]["exit_code"] = 3
    assert _paths(model.validate(verify_results, DocumentKind.RESULTS)) == ["$.gate"]


def test_gate_cannot_pass_with_a_regression(load_example):
    results = load_example("results-verify-regression.example.json")
    results["gate"].update(passed=True, exit_code=0)
    assert _paths(model.validate(results, DocumentKind.RESULTS)) == ["$.gate.passed"]


def test_gate_failure_needs_a_failing_module(verify_results):
    verify_results["gate"].update(passed=False, exit_code=1)
    assert _paths(model.validate(verify_results, DocumentKind.RESULTS)) == ["$.gate.exit_code"]


def test_environment_failure_may_fail_the_gate_without_regressions(verify_results):
    verify_results["gate"].update(passed=False, exit_code=3)
    assert model.validate(verify_results, DocumentKind.RESULTS) == []


def test_stale_entries_pass_the_gate_with_allow_stale(load_example):
    results = load_example("results-certify-regression.example.json")
    happy = _module(results, "issuer-happy-flow")
    happy.update(result="PASSED", verdict="conforms", failures=[])
    del happy["verdict_reason"]
    results["gate"]["allow_stale"] = True
    _resync(results)
    assert results["gate"]["passed"] is True and results["summary"]["stale_benchmark"] == 1
    assert model.validate(results, DocumentKind.RESULTS) == []


def test_non_gating_track_never_fails_the_gate(load_example):
    results = load_example("results-verify-regression.example.json")
    results.update(track="haip", gating=False)
    assert _paths(model.validate(results, DocumentKind.RESULTS)) == ["$.gate.exit_code"]
    results["gate"].update(passed=True, exit_code=0)
    assert model.validate(results, DocumentKind.RESULTS) == []


def test_finished_before_started_is_rejected(verify_results):
    verify_results["finished_at"] = "2026-10-04T18:00:00Z"
    assert _paths(model.validate(verify_results, DocumentKind.RESULTS)) == ["$"]


# --------------------------------------------------------------------------------------------------------------
# Rules beyond the schema: verdict against the suite's outcome (the verdict table)
# --------------------------------------------------------------------------------------------------------------


def _issues_for(results, suffix, **changes):
    _module(results, suffix).update(changes)
    _resync(results)
    return model.validate(results, DocumentKind.RESULTS)


def test_review_conforms_needs_matching_evidence(verify_results):
    happy = _module(verify_results, "happy-flow")
    happy["review"]["evidence"] = None
    assert _paths(model.validate(verify_results, DocumentKind.RESULTS)) == ["$.modules[0].review"]
    happy["review"].update(evidence="evidence/x.png", observed="invalid")
    assert _paths(model.validate(verify_results, DocumentKind.RESULTS)) == ["$.modules[0].review"]
    del happy["review"]
    assert _paths(model.validate(verify_results, DocumentKind.RESULTS)) == ["$.modules[0].review"]


def test_conforms_needs_passed_or_review(verify_results):
    issues = _issues_for(verify_results, "request-uri-fetched-twice", result="WARNING")
    assert _paths(issues) == ["$.modules[3].verdict"]


def test_unfinished_module_is_always_a_regression(verify_results):
    issues = _issues_for(verify_results, "request-uri-fetched-twice", status="INTERRUPTED")
    assert _paths(issues) == ["$.modules[3].verdict"]
    issues = _issues_for(verify_results, "request-uri-fetched-twice", verdict="regression", verdict_reason="timeout")
    assert issues == []


def test_regression_needs_a_reason(load_example):
    results = load_example("results-verify-regression.example.json")
    del _module(results, "invalid-kb-jwt-nonce")["verdict_reason"]
    assert _paths(model.validate(results, DocumentKind.RESULTS)) == ["$.modules[7].verdict_reason"]


def test_known_gap_cannot_hide_an_unexpected_failure(verify_results):
    gap = _module(verify_results, "request-uri-method-post")
    gap["failures"].append({"condition": "EnsureRequestUriIsHttps", "severity": "FAILURE", "expected": False})
    assert _paths(model.validate(verify_results, DocumentKind.RESULTS)) == ["$.modules[2].verdict"]


def test_known_gap_needs_a_matched_expected_failure(verify_results):
    gap = _module(verify_results, "request-uri-method-post")
    gap["benchmark"][0]["matched"] = False
    assert "$.modules[2].benchmark" in _paths(model.validate(verify_results, DocumentKind.RESULTS))


def test_known_gap_needs_a_failed_or_warning_result(verify_results):
    issues = _issues_for(verify_results, "request-uri-method-post", result="PASSED")
    assert _paths(issues) == ["$.modules[2].verdict"]


def test_not_applicable_needs_an_expected_skip(certify_results):
    skipped = _module(certify_results, "metadata-test-signed")
    skipped["benchmark"] = []
    assert _paths(model.validate(certify_results, DocumentKind.RESULTS)) == ["$.modules[1].benchmark"]


def test_not_applicable_needs_a_skipped_or_failed_result(certify_results):
    issues = _issues_for(certify_results, "metadata-test-signed", result="PASSED")
    assert _paths(issues) == ["$.modules[1].verdict"]


def test_stale_benchmark_needs_an_unmatched_entry(load_example):
    results = load_example("results-certify-regression.example.json")
    _module(results, "unknown-credential-configuration")["benchmark"][0]["matched"] = True
    assert _paths(model.validate(results, DocumentKind.RESULTS)) == ["$.modules[12].benchmark"]


def test_conforms_with_an_unmatched_entry_must_be_stale(load_example):
    results = load_example("results-certify-regression.example.json")
    module = _module(results, "unknown-credential-configuration")
    module["verdict"] = "conforms"
    del module["verdict_reason"]
    _resync(results)
    assert "$.modules[12].verdict" in _paths(model.validate(results, DocumentKind.RESULTS))


# --------------------------------------------------------------------------------------------------------------
# Rules beyond the schema: run manifest
# --------------------------------------------------------------------------------------------------------------


@pytest.fixture
def manifest(load_example):
    return load_example("run-manifest.example.json")


def test_combined_manifest_needs_both_components(manifest):
    manifest["components"].pop()
    assert _paths(model.validate(manifest, DocumentKind.RUN_MANIFEST)) == ["$.components"]
    manifest["mode"] = "component"
    assert model.validate(manifest, DocumentKind.RUN_MANIFEST) == []


def test_manifest_components_are_unique(manifest):
    manifest["components"][1]["component"] = "certify"
    issues = _paths(model.validate(manifest, DocumentKind.RUN_MANIFEST))
    assert "$.components[1].component" in issues


def test_manifest_gate_cannot_pass_when_a_component_failed(manifest):
    manifest["components"][0]["exit_code"] = 1
    assert _paths(model.validate(manifest, DocumentKind.RUN_MANIFEST)) == ["$.gate.passed"]
