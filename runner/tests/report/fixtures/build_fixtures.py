"""Rebuilds the report test fixtures ``run-a/`` and ``run-b/`` from the contract examples.

Run from the repository root after the examples in ``conformance/schema/examples/`` change:

    python runner/tests/report/fixtures/build_fixtures.py

- ``run-a``: a combined run on 2026-10-04 whose gate passed (the two passing results examples).
- ``run-b``: an earlier combined run on 2026-10-03 whose gate failed: the two regression examples, an older Inji
  Verify commit, and without the module ``oid4vp-1final-verifier-request-uri-fetched-twice``, so a diff of the two
  runs has changed, added and context rows.

Paths in the examples' module links are made relative to the run folder (``verify/exports/...``), as the contract
asks. A few modules of ``run-a`` get a placeholder HTML export, so the report shows both a present and an absent
export link. Every file says it is a fixture; none is the output of a measured run.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parents[3] / "conformance" / "schema" / "examples"
NOTE = "Report test fixture built from the contract examples by build_fixtures.py; not a measured run."
REMOVED_IN_B = "oid4vp-1final-verifier-request-uri-fetched-twice"
EXPORTS_IN_A = {
    "certify": ("vciexample0003", "vciexample0013"),
    "verify": ("vpexample0001", "vpexample0003"),
}

VERDICTS = ("conforms", "known_gap", "regression", "not_applicable", "stale_benchmark")


def _example(name: str) -> dict[str, Any]:
    return copy.deepcopy(json.loads((EXAMPLES / name).read_text(encoding="utf-8")))


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def _results(name: str, run_id: str, component: str, *, day: str, drop: tuple[str, ...] = ()) -> dict[str, Any]:
    results = _example(name)
    results["run_id"] = run_id
    results["notes"] = [NOTE]
    results["modules"] = [m for m in results["modules"] if m["name"] not in drop]
    for module in results["modules"]:
        links = module.get("links") or {}
        if links.get("export") and not links["export"].startswith(f"{component}/"):
            links["export"] = f"{component}/{links['export']}"
        review = module.get("review")
        if review and review.get("evidence") and not review["evidence"].startswith(f"{component}/"):
            review["evidence"] = f"{component}/{review['evidence']}"
    counts = dict.fromkeys(VERDICTS, 0)
    for module in results["modules"]:
        counts[module["verdict"]] += 1
    results["summary"] = {"total": len(results["modules"]), **counts}
    text = json.dumps(results).replace("2026-10-04T", f"{day}T")
    return json.loads(text)


def _manifest(run_id: str, *, day: str, commit: str, verify_commit: str, passed: bool, exit_codes: dict) -> dict:
    manifest = _example("run-manifest.example.json")
    manifest["run_id"] = run_id
    manifest["harness"]["git_commit"] = commit
    manifest["notes"] = [NOTE]
    for image in manifest["images"]:
        if image["service"] == "verify-service":
            image["commit"] = verify_commit
    for entry in manifest["components"]:
        entry["exit_code"] = exit_codes[entry["component"]]
    manifest["gate"] = {"passed": passed, "exit_code": 0 if passed else 1}
    return json.loads(json.dumps(manifest).replace("2026-10-04T", f"{day}T"))


def _export_page(component: str, test_id: str) -> str:
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>Fixture export {test_id}</title>\n</head>\n<body>\n"
        f"<h1>Placeholder for the suite's HTML export of {component} module {test_id}</h1>\n"
        "<p>Report test fixture. A real run folder holds the page extracted from the suite's plan export.</p>\n"
        "</body>\n</html>\n"
    )


def build() -> None:
    run_a = HERE / "run-a"
    a_id = "20261004T191000Z-1a2b3c4"
    _write(
        run_a / "manifest.json",
        _manifest(
            a_id,
            day="2026-10-04",
            commit="1a2b3c4",
            verify_commit="ad3595f",
            passed=True,
            exit_codes={"certify": 0, "verify": 0},
        ),
    )
    _write(
        run_a / "certify" / "results.json", _results("results-certify.example.json", a_id, "certify", day="2026-10-04")
    )
    _write(run_a / "verify" / "results.json", _results("results-verify.example.json", a_id, "verify", day="2026-10-04"))
    for component, test_ids in EXPORTS_IN_A.items():
        for test_id in test_ids:
            page = run_a / component / "exports" / f"{test_id}.html"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(_export_page(component, test_id), encoding="utf-8", newline="\n")

    run_b = HERE / "run-b"
    b_id = "20261003T101500Z-9f8e7d6"
    _write(
        run_b / "manifest.json",
        _manifest(
            b_id,
            day="2026-10-03",
            commit="9f8e7d6",
            verify_commit="0bd41e2",
            passed=False,
            exit_codes={"certify": 1, "verify": 1},
        ),
    )
    _write(
        run_b / "certify" / "results.json",
        _results("results-certify-regression.example.json", b_id, "certify", day="2026-10-03"),
    )
    verify_b = _results(
        "results-verify-regression.example.json", b_id, "verify", day="2026-10-03", drop=(REMOVED_IN_B,)
    )
    verify_b["target"]["commit"] = "0bd41e2"
    _write(run_b / "verify" / "results.json", verify_b)


if __name__ == "__main__":
    build()
