"""Loading runs: run folders, component folders, results files, and the errors for broken input."""

from __future__ import annotations

import pytest

from inji_conformance.model import Component, Verdict
from inji_conformance.report.runs import RunLoadError, combine, load_run


def test_run_folder_with_manifest(run_a):
    run = load_run(run_a)
    assert run.run_id == "20261004T191000Z-1a2b3c4"
    assert [item.component for item in run.components] == [Component.CERTIFY, Component.VERIFY]
    assert run.combined and run.gate_passed is True
    assert run.count(Verdict.CONFORMS) == 20 and run.count(Verdict.KNOWN_GAP) == 2


def test_manifest_file_path_is_the_same_as_its_folder(run_a):
    assert load_run(run_a / "manifest.json").run_id == load_run(run_a).run_id


def test_component_folder_and_results_file(run_a):
    folder = load_run(run_a / "verify")
    single = load_run(run_a / "verify" / "results.json")
    assert [c.component for c in folder.components] == [Component.VERIFY] == [c.component for c in single.components]
    assert folder.manifest is None and not folder.combined


def test_failed_gate_of_run_b(run_b):
    assert load_run(run_b).gate_passed is False


def test_locate_finds_run_relative_paths_and_ignores_missing_files(run_a):
    verify = load_run(run_a).component(Component.VERIFY)
    assert verify.locate("verify/exports/vpexample0001.html") == run_a / "verify" / "exports" / "vpexample0001.html"
    assert verify.locate("verify/exports/vpexample0002.html") is None
    assert verify.locate(None) is None


def test_combine_component_runs_into_one(run_a):
    run = combine([load_run(run_a / "verify"), load_run(run_a / "certify")])
    assert [c.component for c in run.components] == [Component.CERTIFY, Component.VERIFY]
    assert run.combined


def test_combine_refuses_a_component_twice(run_a, run_b):
    with pytest.raises(RunLoadError, match="certify appears twice"):
        combine([load_run(run_a / "certify"), load_run(run_b / "certify")])


def test_missing_folder(tmp_path):
    with pytest.raises(RunLoadError, match="no such run folder"):
        load_run(tmp_path / "absent")


def test_folder_without_results(tmp_path):
    with pytest.raises(RunLoadError, match=r"neither manifest\.json nor results\.json"):
        load_run(tmp_path)


def test_invalid_results_name_the_problem(copied_runs, edit_json):
    results = copied_runs / "run-a" / "verify" / "results.json"
    edit_json(results, lambda data: data["summary"].update(conforms=3))
    with pytest.raises(RunLoadError, match=r"\$\.summary\.conforms"):
        load_run(copied_runs / "run-a")


def test_not_json(tmp_path):
    (tmp_path / "results.json").write_text("{", encoding="utf-8")
    with pytest.raises(RunLoadError, match="not JSON"):
        load_run(tmp_path)


def test_manifest_component_must_match_the_results(copied_runs, edit_json):
    def swap(data):
        data["components"][0]["results"], data["components"][1]["results"] = (
            data["components"][1]["results"],
            data["components"][0]["results"],
        )

    edit_json(copied_runs / "run-a" / "manifest.json", swap)
    with pytest.raises(RunLoadError, match="holds verify results, the manifest says certify"):
        load_run(copied_runs / "run-a")
