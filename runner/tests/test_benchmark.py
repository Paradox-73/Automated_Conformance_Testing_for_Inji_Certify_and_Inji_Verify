"""The benchmark gate: matching entries to modules, the verdict table, the cross-check and the gate command."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from inji_conformance import benchmark, cli, model
from inji_conformance.model import (
    Component,
    ExitCode,
    Failure,
    ModuleResult,
    ModuleStatus,
    Review,
    ReviewOutcome,
    Severity,
    SuiteResult,
    Verdict,
)

CONFIG = "certify/config/certify.oid4vci-1_0-issuer.json"
PATTERN = "*certify.oid4vci-1_0-issuer*.json"


def failure_entry(test: str, condition: str, *, result: str = "failure", block: str = "*", **extra: Any) -> dict:
    return {
        "test-name": test,
        "variant": extra.pop("variant", "*"),
        "configuration-filename": extra.pop("configuration_filename", PATTERN),
        "current-block": block,
        "condition": condition,
        "expected-result": result,
        "comment": "Inji Certify answers this with an error the suite does not expect.",
        "owner": "inji",
        "spec": "OID4VCI-1FINAL-8.2",
        "issue": "docs/findings/example.md",
    }


def skip_entry(test: str) -> dict:
    return {
        "test-name": test,
        "variant": "*",
        "configuration-filename": PATTERN,
        "comment": "The issuer offers no batch issuance, so the suite skips this module.",
        "owner": "inji",
        "spec": "OID4VCI-1FINAL-12.2.4",
        "issue": "docs/findings/example.md",
    }


def write_benchmark(folder: Path, failures: list[dict], skips: list[dict] | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "certify.expected-failures.json").write_text(json.dumps(failures), encoding="utf-8")
    if skips is not None:
        (folder / "certify.expected-skips.json").write_text(json.dumps(skips), encoding="utf-8")
    return folder


def fail(condition: str, severity: Severity = Severity.FAILURE, block: str = "Call Credential Endpoint") -> Failure:
    return Failure(condition=condition, severity=severity, message="m", block=block, expected=False)


def module(
    name: str,
    result: SuiteResult | None,
    failures: tuple[Failure, ...] = (),
    status: ModuleStatus = ModuleStatus.FINISHED,
    review: Review | None = None,
) -> ModuleResult:
    return ModuleResult(
        name=name,
        test_id="t-" + name,
        status=status,
        result=result,
        verdict=Verdict.REGRESSION,
        verdict_reason="not classified yet",
        failures=failures,
        review=review,
    )


def results_of(*modules: ModuleResult, gating: bool = True) -> model.Results:
    return model.Results(
        schema_version="1",
        run_id="20261014T000000Z-abc123",
        component=Component.CERTIFY,
        track=model.Track.GATE if gating else model.Track.HAIP,
        gating=gating,
        suite=model.SuiteInfo(base_url="https://suite", version="5.3.1"),
        target=model.TargetInfo(base_url="https://certify.inji.test:18450"),
        plan=model.PlanInfo(
            name="oid4vci-1_0-issuer-test-plan", variant={"sender_constrain": "dpop"}, config_file=CONFIG
        ),
        modules=modules,
        summary=model.Summary.of(modules),
        gate=model.Gate(passed=True, exit_code=ExitCode.OK),
    )


def bench(failures: list[dict], skips: list[dict] | None = None, tmp_path: Path | None = None) -> benchmark.Benchmark:
    folder = write_benchmark(tmp_path or Path("."), failures, skips or [])
    return benchmark.load(folder, Component.CERTIFY)


def classify_one(tmp_path: Path, mod: ModuleResult, failures: list[dict], skips: list[dict] | None = None):
    classified = benchmark.classify(results_of(mod), bench(failures, skips, tmp_path))
    assert model.validate(classified.to_dict(), model.DocumentKind.RESULTS) == []
    return classified.modules[0], classified


# --- matching ----------------------------------------------------------------------------------------------------


def test_applies_uses_name_and_file_patterns_and_listed_variant_keys(tmp_path):
    entry = bench(
        [failure_entry("oid4vci-1_0-issuer-*", "X", variant={"sender_constrain": "dpop"})], tmp_path=tmp_path
    ).failures[0]
    assert benchmark.applies(entry, "oid4vci-1_0-issuer-happy-flow", CONFIG, {"sender_constrain": "dpop", "a": "b"})
    assert not benchmark.applies(entry, "oid4vci-1_0-issuer-happy-flow", CONFIG, {"sender_constrain": "mtls"})
    assert not benchmark.applies(entry, "oid4vci-1_0-issuer-happy-flow", CONFIG, {})
    assert not benchmark.applies(entry, "oid4vp-1final-verifier-happy-flow", CONFIG, {"sender_constrain": "dpop"})
    assert not benchmark.applies(
        entry, "oid4vci-1_0-issuer-happy-flow", "verify/config/x.json", {"sender_constrain": "dpop"}
    )


def test_missing_benchmark_folder_and_invalid_file_are_errors(tmp_path):
    with pytest.raises(benchmark.BenchmarkError, match="does not exist"):
        benchmark.load(tmp_path / "nope", Component.CERTIFY)
    entry = failure_entry("a", "B")
    del entry["owner"]
    write_benchmark(tmp_path, [entry])
    with pytest.raises(benchmark.BenchmarkError, match="owner"):
        benchmark.load(tmp_path, Component.CERTIFY)


def test_missing_files_mean_no_entries(tmp_path):
    loaded = benchmark.load(tmp_path, Component.VERIFY)
    assert (loaded.failures, loaded.skips, loaded.files) == ((), (), ())


# --- the verdict table -------------------------------------------------------------------------------------------


def test_passed_and_not_listed_conforms(tmp_path):
    mod, classified = classify_one(tmp_path, module("m", SuiteResult.PASSED), [])
    assert (mod.verdict, mod.verdict_reason) == (Verdict.CONFORMS, None)
    assert classified.gate.exit_code is ExitCode.OK
    assert classified.gate.messages[0] == "gate: 0 regressions, 0 known gaps, 0 stale"


def test_every_failure_listed_is_a_known_gap(tmp_path):
    mod, classified = classify_one(
        tmp_path,
        module("m", SuiteResult.FAILED, (fail("A"), fail("B", Severity.WARNING))),
        [failure_entry("m", "A"), failure_entry("m", "B", result="warning", block="Call Credential Endpoint")],
    )
    assert mod.verdict is Verdict.KNOWN_GAP
    assert all(f.expected for f in mod.failures)
    assert [ref.matched for ref in mod.benchmark] == [True, True]
    assert classified.gate.passed and classified.gate.messages[0] == "gate: 0 regressions, 1 known gaps, 0 stale"


def test_one_unlisted_condition_is_a_regression_named_in_the_gate(tmp_path):
    mod, classified = classify_one(
        tmp_path, module("m", SuiteResult.FAILED, (fail("A"), fail("B"))), [failure_entry("m", "A")]
    )
    assert mod.verdict is Verdict.REGRESSION
    assert mod.verdict_reason == "result FAILED: not in the benchmark: B"
    assert classified.gate.exit_code is ExitCode.GATE_FAILED
    assert "regression: m: result FAILED: not in the benchmark: B" in classified.gate.messages


@pytest.mark.parametrize(
    ("entry", "why"),
    [
        (failure_entry("m", "A", result="warning"), "warning listed, failure logged"),
        (failure_entry("m", "A", block="Another block"), "other block"),
        (failure_entry("other-module", "A"), "other module"),
    ],
)
def test_entry_must_match_severity_block_and_module(tmp_path, entry, why):
    mod, _ = classify_one(tmp_path, module("m", SuiteResult.FAILED, (fail("A"),)), [entry])
    assert mod.verdict is Verdict.REGRESSION, why


def test_listed_condition_that_did_not_happen_is_stale(tmp_path):
    mod, classified = classify_one(tmp_path, module("m", SuiteResult.PASSED), [failure_entry("m", "A")])
    assert mod.verdict is Verdict.STALE_BENCHMARK
    assert "A (failure)" in mod.verdict_reason
    assert classified.gate.exit_code is ExitCode.GATE_FAILED


def test_allow_stale_turns_stale_entries_into_a_warning(tmp_path):
    results = results_of(module("m", SuiteResult.PASSED))
    classified = benchmark.classify(results, bench([failure_entry("m", "A")], tmp_path=tmp_path), allow_stale=True)
    assert model.validate(classified.to_dict(), model.DocumentKind.RESULTS) == []
    assert classified.gate.passed and classified.gate.allow_stale
    assert any("--allow-stale" in line for line in classified.gate.messages)


def test_skips(tmp_path):
    listed, _ = classify_one(tmp_path, module("m", SuiteResult.SKIPPED), [], [skip_entry("m")])
    assert listed.verdict is Verdict.NOT_APPLICABLE
    unlisted, _ = classify_one(tmp_path, module("m", SuiteResult.SKIPPED), [], [])
    assert unlisted.verdict is Verdict.REGRESSION
    ran, _ = classify_one(tmp_path, module("m", SuiteResult.PASSED), [], [skip_entry("m")])
    assert ran.verdict is Verdict.STALE_BENCHMARK and "expected skip" in ran.verdict_reason


def test_module_interrupted_by_a_failing_condition_is_judged_like_a_failed_one(tmp_path):
    interrupted = module("m", SuiteResult.FAILED, (fail("A"),), status=ModuleStatus.INTERRUPTED)
    mod, _ = classify_one(tmp_path, interrupted, [failure_entry("m", "A")])
    assert mod.verdict is Verdict.KNOWN_GAP


@pytest.mark.parametrize(
    "mod",
    [
        module("m", None, status=ModuleStatus.NOT_STARTED),
        module("m", None, status=ModuleStatus.WAITING),
        module("m", SuiteResult.FAILED, (fail("A", Severity.WARNING),), status=ModuleStatus.INTERRUPTED),
    ],
)
def test_module_that_did_not_complete_stays_a_regression(tmp_path, mod):
    classified, _ = classify_one(tmp_path, mod, [failure_entry("m", "A", result="warning")])
    assert classified.verdict is Verdict.REGRESSION


def test_review_needs_confirmed_evidence(tmp_path):
    confirmed = Review(expected=ReviewOutcome.VALID, observed=ReviewOutcome.VALID, evidence="verify/evidence/m.png")
    mod, _ = classify_one(tmp_path, module("m", SuiteResult.REVIEW, review=confirmed), [])
    assert mod.verdict is Verdict.CONFORMS
    unconfirmed = Review(expected=ReviewOutcome.VALID, observed=ReviewOutcome.INVALID, evidence=None)
    mod, _ = classify_one(tmp_path, module("m", SuiteResult.REVIEW, review=unconfirmed), [])
    assert mod.verdict is Verdict.REGRESSION


def test_classifying_twice_gives_the_same_verdicts(tmp_path):
    entries = bench([failure_entry("m", "A")], tmp_path=tmp_path)
    once = benchmark.classify(results_of(module("m", SuiteResult.FAILED, (fail("A"),))), entries)
    twice = benchmark.classify(once, entries)
    assert twice.to_dict() == once.to_dict()


def test_non_gating_track_never_fails(tmp_path):
    results = results_of(module("m", SuiteResult.FAILED, (fail("A"),)), gating=False)
    classified = benchmark.classify(results, bench([], tmp_path=tmp_path))
    assert classified.gate.exit_code is ExitCode.OK and classified.summary.regression == 1
    assert model.validate(classified.to_dict(), model.DocumentKind.RESULTS) == []


# --- what run-test-plan.py is given, and the cross-check ---------------------------------------------------------


def test_restricted_to_keeps_only_entries_for_the_selected_modules(tmp_path):
    entries = bench([failure_entry("a", "X"), failure_entry("b", "Y")], [skip_entry("c")], tmp_path)
    kept = entries.restricted_to([("a", {})], "config/certify.oid4vci-1_0-issuer.json")
    assert [e.test_name for e in kept.failures] == ["a"] and kept.skips == ()
    paths = kept.write(tmp_path / "given", Component.CERTIFY)
    assert [p.name for p in paths] == ["certify.expected-failures.json", "certify.expected-skips.json"]
    assert json.loads(paths[0].read_text(encoding="utf-8"))[0]["test-name"] == "a"
    assert json.loads(paths[1].read_text(encoding="utf-8")) == []


def test_entries_for_another_configuration_are_left_out(tmp_path):
    other = failure_entry("a", "X", configuration_filename="*verify.other.json")
    entries = bench([failure_entry("a", "X"), other], tmp_path=tmp_path)
    assert [e.configuration_filename for e in entries.for_config(CONFIG).failures] == [PATTERN]
    results = results_of(module("a", SuiteResult.FAILED, (fail("X"),)))
    assert benchmark.unused_entries(results, entries) == []


def test_unused_entries_are_found(tmp_path):
    entries = bench([failure_entry("a", "X"), failure_entry("zzz", "Y")], tmp_path=tmp_path)
    results = results_of(module("a", SuiteResult.FAILED, (fail("X"),)))
    assert [e.test_name for e in benchmark.unused_entries(results, entries)] == ["zzz"]


@pytest.mark.parametrize(
    ("mods", "script_code", "agrees"),
    [
        ((module("a", SuiteResult.PASSED),), 0, True),
        ((module("a", SuiteResult.PASSED),), 1, False),
        ((module("a", SuiteResult.FAILED, (fail("Z"),)),), 1, True),
        ((module("a", SuiteResult.FAILED, (fail("Z"),)),), 0, False),
        # REVIEW without evidence fails the harness gate but not the suite's: an extension, not a disagreement.
        ((module("a", SuiteResult.REVIEW),), 0, True),
        ((module("a", SuiteResult.PASSED),), None, True),
    ],
)
def test_cross_check(tmp_path, mods, script_code, agrees):
    classified = benchmark.classify(results_of(*mods), bench([], tmp_path=tmp_path))
    message = benchmark.cross_check(classified, script_code)
    assert (message is None) is agrees
    if message:
        assert "run-test-plan.py exited" in message


def test_stale_entry_disagrees_with_a_passing_script(tmp_path):
    classified = benchmark.classify(
        results_of(module("a", SuiteResult.PASSED)), bench([failure_entry("a", "X")], tmp_path=tmp_path)
    )
    assert benchmark.cross_check(classified, 1) is None
    assert benchmark.cross_check(classified, 0) is not None


# --- JUnit and the gate command ----------------------------------------------------------------------------------


def test_junit_has_one_case_per_module_and_fails_regressions(tmp_path):
    classified = benchmark.classify(
        results_of(
            module("ok", SuiteResult.PASSED),
            module("gap", SuiteResult.FAILED, (fail("A"),)),
            module("bad", SuiteResult.FAILED, (fail("B"),)),
            module("skip", SuiteResult.SKIPPED),
        ),
        bench([failure_entry("gap", "A")], [skip_entry("skip")], tmp_path),
    )
    root = ET.fromstring(benchmark.junit_xml(classified))
    suite = root.find("testsuite")
    assert (suite.get("tests"), suite.get("failures"), suite.get("skipped")) == ("4", "1", "1")
    cases = {case.get("name"): case for case in suite.iter("testcase")}
    assert cases["bad"].find("failure") is not None and "B [NOT LISTED]" in cases["bad"].find("failure").text
    assert cases["skip"].find("skipped") is not None
    assert "known gap" in cases["gap"].find("system-out").text


def test_gate_command_exits_with_the_gate_and_names_module_and_condition(tmp_path, capsys):
    run = tmp_path / "run" / "certify"
    run.mkdir(parents=True)
    recorded = results_of(module("m", SuiteResult.FAILED, (fail("A"), fail("B"))))
    model.dump(benchmark.classify(recorded, benchmark.Benchmark()), run / "results.json")
    full = write_benchmark(tmp_path / "full", [failure_entry("m", "A"), failure_entry("m", "B")], [])
    short = write_benchmark(tmp_path / "short", [failure_entry("m", "A")], [])

    assert cli.main(["gate", "--run", str(run), "--benchmark-dir", str(full)]) == ExitCode.OK
    assert "gate: 0 regressions, 1 known gaps, 0 stale" in capsys.readouterr().out

    junit = tmp_path / "out" / "junit.xml"
    code = cli.main(["gate", "--run", str(run / "results.json"), "--benchmark-dir", str(short), "--junit", str(junit)])
    out = capsys.readouterr().out
    assert code == ExitCode.GATE_FAILED
    assert "regression: m: result FAILED: not in the benchmark: B" in out
    assert junit.is_file()


def test_gate_command_usage_errors(tmp_path, capsys):
    assert cli.main(["gate", "--run", str(tmp_path / "missing")]) == ExitCode.USAGE
    assert "no results file" in capsys.readouterr().err
    run = tmp_path / "r"
    run.mkdir()
    model.dump(results_of(module("m", SuiteResult.PASSED)), run / "results.json")
    assert cli.main(["gate", "--run", str(run), "--benchmark-dir", str(tmp_path / "nope")]) == ExitCode.USAGE


def test_repository_benchmark_files_are_valid():
    folder = Path(__file__).resolve().parents[2] / "conformance" / "benchmark"
    for component in Component:
        loaded = benchmark.load(folder, component)
        assert loaded.files, f"no benchmark files for {component.value}"


def test_a_run_without_modules_fails_with_exit_3_on_every_track(tmp_path):
    for gating in (True, False):
        classified = benchmark.classify(results_of(gating=gating), bench([], tmp_path=tmp_path))
        assert (classified.gate.passed, classified.gate.exit_code) == (False, ExitCode.ENVIRONMENT_NOT_READY)
        assert classified.gate.messages == (model.NO_MODULES,)
        assert model.validate(classified.to_dict(), model.DocumentKind.RESULTS) == []


def test_validate_rejects_a_passed_gate_without_modules():
    issues = model.validate(results_of().to_dict(), model.DocumentKind.RESULTS)
    assert any("no module results" in str(issue) for issue in issues)


def test_gate_command_on_a_recorded_run_without_modules_never_passes(tmp_path, capsys):
    run = tmp_path / "certify"
    run.mkdir()
    full = write_benchmark(tmp_path / "bench", [], [])
    recorded = benchmark.classify(results_of(), benchmark.Benchmark())  # what the runner writes: exit 3
    model.dump(recorded, run / "results.json")
    assert cli.main(["gate", "--run", str(run), "--benchmark-dir", str(full)]) == ExitCode.ENVIRONMENT_NOT_READY
    assert model.NO_MODULES in capsys.readouterr().out
    # A file from an older harness that recorded such a run as passed is rejected as invalid.
    (run / "results.json").write_text(json.dumps(results_of().to_dict()), encoding="utf-8")
    assert cli.main(["gate", "--run", str(run), "--benchmark-dir", str(full)]) == ExitCode.USAGE
    assert "no module results" in capsys.readouterr().err
