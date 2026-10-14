"""Tests of docs/tools/check_docs.py on small throwaway repositories. Standard library only.

    python3 -m unittest discover -s docs/tools -p 'test_*.py'

"bash scripts/check.sh docs" runs these tests before the checker itself.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import check_docs

TODAY = dt.date(2026, 10, 14)
GOOD_GUIDE = """# Guide

How to run it, see [the design](design/README.md#all-tasks) and [below](#run-it).

## Run it

<!-- run 2026-10-14 -->
```bash
./run-conformance.sh --component verify --runner-only
```

![badge](badge.svg)
"""
FINDING = """# Finding

## Summary

## Affected version

## Spec reference

## Suite condition

## Steps

## Expected

## Actual

## Evidence

## Proposed fix
"""


class CheckDocsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.write("README.md", "# Project\n\nSee [the guide](docs/README.md).\n")
        self.write("docs/README.md", GOOD_GUIDE)
        self.write("docs/design/README.md", "# Design\n\n## All tasks\n\n```bash\nnot dated, allowed here\n```\n")
        self.write("docs/badge.svg", "<svg/>\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def findings(self) -> list[str]:
        found, _counts = check_docs.run_checks(self.root, TODAY)
        return [str(f) for f in found]

    def test_a_clean_tree_has_no_findings(self) -> None:
        self.assertEqual([], self.findings())

    def test_removing_a_dated_marker_is_found(self) -> None:
        self.write("docs/README.md", GOOD_GUIDE.replace("<!-- run 2026-10-14 -->\n", ""))
        self.assertEqual(
            ["docs/README.md:7: dated: command block without <!-- run YYYY-MM-DD --> above it"], self.findings()
        )

    def test_a_date_in_the_future_or_before_the_project_is_found(self) -> None:
        for day in ("2026-10-15", "2026-10-01"):
            self.write("docs/README.md", GOOD_GUIDE.replace("2026-10-14", day))
            self.assertIn("is outside 2026-10-04 to 2026-10-14", self.findings()[0])

    def test_a_broken_link_or_anchor_is_found(self) -> None:
        self.write("docs/README.md", GOOD_GUIDE.replace("design/README.md#all-tasks", "design/README.md#no-such"))
        self.assertEqual(
            ["docs/README.md:3: link: design/README.md#no-such: no heading with anchor #no-such"], self.findings()
        )
        self.write("docs/README.md", GOOD_GUIDE.replace("badge.svg", "missing.svg"))
        self.assertEqual(["docs/README.md:12: link: missing.svg does not exist"], self.findings())

    def test_links_in_code_are_not_checked(self) -> None:
        self.write("docs/README.md", GOOD_GUIDE + "\n`[x](nowhere.md)`\n")
        self.assertEqual([], self.findings())

    def test_lint_rules(self) -> None:
        self.write("docs/extra.md", "Text first\n\n## Two\n\n#### Skipped a level  \n\n\n\ttab\n")
        rules = {line.split(": ")[1] for line in self.findings()}
        self.assertEqual({"lint"}, rules)
        messages = "\n".join(self.findings())
        for expected in ("MD041", "MD001", "MD009", "MD012", "MD010"):
            self.assertIn(expected, messages)

    def test_unclosed_fence_and_missing_final_newline(self) -> None:
        self.write("docs/extra.md", "# Extra\n\n```text\nopen")
        messages = "\n".join(self.findings())
        self.assertIn("code fence is never closed", messages)
        self.assertIn("MD047", messages)

    def test_findings_need_every_heading(self) -> None:
        self.write("docs/findings/good.md", FINDING)
        self.write("docs/findings/bad.md", FINDING.replace("\n## Proposed fix\n", ""))
        self.assertEqual(["docs/findings/bad.md:1: finding: missing level-2 headings: Proposed fix"], self.findings())

    def test_cited_runs_need_dated_evidence(self) -> None:
        self.write("docs/test-report.md", "# Report\n\nRun 20261014T010203Z-abc123 passed.\n")
        self.assertIn("run 20261014T010203Z-abc123 has no docs/evidence/", self.findings()[0])
        self.write(
            "docs/evidence/2026-10-14-20261014T010203Z-abc123/manifest.json",
            json.dumps({"started_at": "2026-10-14T01:02:03Z"}),
        )
        self.assertEqual([], self.findings())
        self.write(
            "docs/evidence/2026-10-14-20261014T010203Z-abc123/manifest.json",
            json.dumps({"started_at": "2026-10-03T01:02:03Z"}),
        )
        self.assertIn("before 2026-10-04", self.findings()[0])

    def test_benchmark_issues_must_exist(self) -> None:
        self.write(
            "conformance/benchmark/verify.expected-skips.json",
            json.dumps([{"issue": "docs/findings/missing.md"}, {"issue": "https://example.org/1"}]),
        )
        self.assertEqual(
            [
                (
                    "conformance/benchmark/verify.expected-skips.json:1: benchmark: issue "
                    "docs/findings/missing.md does not exist"
                )
            ],
            self.findings(),
        )

    def test_main_exit_codes(self) -> None:
        self.assertEqual(0, check_docs.main(["--root", str(self.root), "--today", "2026-10-14"]))
        self.write("docs/README.md", GOOD_GUIDE.replace("badge.svg", "missing.svg"))
        self.assertEqual(1, check_docs.main(["--root", str(self.root), "--today", "2026-10-14"]))


if __name__ == "__main__":
    unittest.main()
