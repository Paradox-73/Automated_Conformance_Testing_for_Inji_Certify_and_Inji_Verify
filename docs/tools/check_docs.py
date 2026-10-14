#!/usr/bin/env python3
"""Checks of the repository's Markdown documents; ``bash scripts/check.sh docs`` runs it.

Standard library only. Every Markdown file git tracks (or would add) is checked, except imported upstream trees
(``third_party/``, ``testrigs/inji-*-api-test/``) and generated run evidence (``docs/evidence/``). The rules:

- ``lint``: a subset of markdownlint: the file starts with a level-1 heading (MD041), heading levels go down one
  step at a time (MD001), no trailing spaces (MD009), no tab characters outside code blocks (MD010), no two blank
  lines in a row (MD012), every code fence is closed, and the file ends with exactly one newline (MD047).
- ``link``: every relative link and image resolves to a file or folder in the repository, and an ``#anchor`` to a
  heading that exists (GitHub's anchor rules), also within the same file.
- ``dated``: in the user documents (``docs/`` and the top-level ``README.md``) every ``bash``/``sh``/``console`` code
  block carries the date it was last run, ``<!-- run YYYY-MM-DD -->`` on one of the three lines above the fence,
  between 2026-10-04 and today. ``CONTRIBUTING.md`` and the lane READMEs hold commands for work
  in progress and are not held to it; ``docs/design/`` holds no commands.
- ``evidence``: every run id cited in ``docs/test-report.md`` has a folder ``docs/evidence/<date>-<run id>/`` with a
  ``manifest.json`` that started on 2026-10-04 or later.
- ``finding``: every issue draft in ``docs/findings/`` (except its README) has the headings Summary, Affected
  version, Spec reference, Suite condition, Steps, Expected, Actual, Evidence and Proposed fix.
- ``benchmark``: every ``issue`` of ``conformance/benchmark/*.json`` that is a repository path exists.

Exit status 0 when nothing was found, 1 otherwise; one line per finding: ``<file>:<line>: <rule>: <message>``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

EARLIEST_RUN = dt.date(2026, 10, 4)
UPSTREAM = ("third_party/", "testrigs/inji-certify-api-test/", "testrigs/inji-verify-api-test/")
GENERATED = ("docs/evidence/",)  # files the runner wrote (summary.md of a run), copied as evidence
NOT_DATED = ("docs/design/",)
COMMAND_LANGUAGES = {"bash", "sh", "shell", "console"}
FINDING_HEADINGS = (
    "Summary",
    "Affected version",
    "Spec reference",
    "Suite condition",
    "Steps",
    "Expected",
    "Actual",
    "Evidence",
    "Proposed fix",
)
RUN_MARKER = re.compile(r"<!--\s*run (\d{4}-\d{2}-\d{2})\s*-->")
RUN_ID = re.compile(r"\b(\d{8}T\d{6}Z-[0-9a-f]{6,8})\b")
FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
INLINE_CODE = re.compile(r"`[^`]*`")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.message}"


@dataclass
class Document:
    path: Path
    relative: str
    lines: list[str]
    # line index -> True for lines inside a fenced code block (fence lines included)
    in_code: list[bool]
    headings: list[tuple[int, int, str]]  # (line number, level, text)
    blocks: list[tuple[int, int | None, str]]  # fenced code blocks: (opening index, closing index or None, info)

    @classmethod
    def read(cls, root: Path, relative: str) -> Document:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        in_code = [False] * len(lines)
        headings = []
        blocks: list[tuple[int, int | None, str]] = []
        fence: str | None = None
        for index, line in enumerate(lines):
            match = FENCE.match(line)
            if fence is None and match:
                fence = match.group(2)[0] * 3
                in_code[index] = True
                blocks.append((index, None, match.group(3).strip()))
                continue
            if fence is not None:
                in_code[index] = True
                if match and match.group(2).startswith(fence) and not match.group(3).strip():
                    fence = None
                    blocks[-1] = (blocks[-1][0], index, blocks[-1][2])
                continue
            heading = HEADING.match(line)
            if heading:
                headings.append((index + 1, len(heading.group(1)), heading.group(2)))
        return cls(path, relative, lines, in_code, headings, blocks)

    def anchors(self) -> set[str]:
        seen: dict[str, int] = {}
        out = set()
        for _line, _level, text in self.headings:
            slug = github_slug(text)
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            out.add(slug if count == 0 else f"{slug}-{count}")
        return out


def github_slug(text: str) -> str:
    """GitHub's heading anchor: lower case, markup and punctuation removed, spaces to hyphens."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_~]", "", text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def markdown_files(root: Path) -> list[str]:
    """The Markdown files git would commit, without imported upstream trees."""
    try:
        listed = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", "*.md"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        listed = [p.relative_to(root).as_posix() for p in root.rglob("*.md") if "/run/" not in f"/{p}"]
    return sorted({name for name in listed if (root / name).is_file() and not name.startswith(UPSTREAM + GENERATED)})


# ---------------------------------------------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------------------------------------------


def check_lint(doc: Document) -> Iterator[Finding]:
    text = doc.path.read_text(encoding="utf-8")
    first = next((i for i, line in enumerate(doc.lines) if line.strip()), None)
    if first is None or not doc.lines[first].startswith("# "):
        yield Finding(doc.relative, (first or 0) + 1, "lint", "the file must start with a level-1 heading (MD041)")
    previous = 0
    for line, level, _text in doc.headings:
        if previous and level > previous + 1:
            yield Finding(doc.relative, line, "lint", f"heading level {level} after {previous} (MD001)")
        previous = level
    blank_run = 0
    for index, line in enumerate(doc.lines):
        number = index + 1
        if line != line.rstrip(" \t") and not (doc.in_code[index] and line.strip() == ""):
            yield Finding(doc.relative, number, "lint", "trailing whitespace (MD009)")
        if "\t" in line and not doc.in_code[index]:
            yield Finding(doc.relative, number, "lint", "tab character outside a code block (MD010)")
        blank_run = blank_run + 1 if not line.strip() and not doc.in_code[index] else 0
        if blank_run == 2 and index < len(doc.lines) - 1:
            yield Finding(doc.relative, number, "lint", "two blank lines in a row (MD012)")
    for opening, closing, _info in doc.blocks:
        if closing is None:
            yield Finding(doc.relative, opening + 1, "lint", "code fence is never closed")
    if not text.endswith("\n") or text.endswith("\n\n"):
        yield Finding(doc.relative, len(doc.lines), "lint", "the file must end with exactly one newline (MD047)")


def check_links(doc: Document, root: Path, documents: dict[str, Document]) -> Iterator[Finding]:
    for index, line in enumerate(doc.lines):
        if doc.in_code[index]:
            continue
        for match in LINK.finditer(INLINE_CODE.sub("", line)):
            target = match.group(1)
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE) or target.startswith("//"):
                continue  # http(s), mailto and other absolute URLs
            path_part, _sep, anchor = target.partition("#")
            if path_part:
                resolved = (doc.path.parent / path_part).resolve()
                try:
                    inside = resolved.relative_to(root.resolve()).as_posix()
                except ValueError:
                    yield Finding(doc.relative, index + 1, "link", f"{target} points outside the repository")
                    continue
                if not resolved.exists():
                    yield Finding(doc.relative, index + 1, "link", f"{target} does not exist")
                    continue
            else:
                inside = doc.relative
            if anchor and inside.endswith(".md"):
                target_doc = documents.get(inside) or Document.read(root, inside)
                if anchor.lower() not in target_doc.anchors():
                    yield Finding(doc.relative, index + 1, "link", f"{target}: no heading with anchor #{anchor}")


def needs_dates(relative: str) -> bool:
    if relative.startswith(NOT_DATED):
        return False
    return relative == "README.md" or relative.startswith("docs/")


def check_dated_commands(doc: Document, today: dt.date) -> Iterator[Finding]:
    if not needs_dates(doc.relative):
        return
    for opening, _closing, info in doc.blocks:
        language = info.split(" ")[0].lower() if info else ""
        if language not in COMMAND_LANGUAGES:
            continue
        found = [m.group(1) for m in map(RUN_MARKER.search, doc.lines[max(0, opening - 3) : opening]) if m]
        if not found:
            yield Finding(doc.relative, opening + 1, "dated", "command block without <!-- run YYYY-MM-DD --> above it")
            continue
        try:
            day = dt.date.fromisoformat(found[-1])
        except ValueError:
            yield Finding(doc.relative, opening + 1, "dated", f"not a date: {found[-1]}")
            continue
        if not EARLIEST_RUN <= day <= today:
            yield Finding(doc.relative, opening + 1, "dated", f"run date {day} is outside {EARLIEST_RUN} to {today}")


def check_evidence(root: Path) -> Iterator[Finding]:
    report = root / "docs" / "test-report.md"
    if not report.is_file():
        return
    evidence = root / "docs" / "evidence"
    folders = [p for p in evidence.iterdir() if p.is_dir()] if evidence.is_dir() else []
    seen = set()
    for number, line in enumerate(report.read_text(encoding="utf-8").split("\n"), 1):
        for run_id in RUN_ID.findall(line):
            if run_id in seen:
                continue
            seen.add(run_id)
            matches = [p for p in folders if p.name.endswith(f"-{run_id}")]
            if not matches:
                yield Finding(
                    "docs/test-report.md", number, "evidence", f"run {run_id} has no docs/evidence/<date>-{run_id}/"
                )
                continue
            manifest = matches[0] / "manifest.json"
            try:
                started = json.loads(manifest.read_text(encoding="utf-8"))["started_at"]
                day = dt.date.fromisoformat(started[:10])
            except (OSError, ValueError, KeyError) as error:
                yield Finding("docs/test-report.md", number, "evidence", f"{manifest.relative_to(root)}: {error}")
                continue
            if day < EARLIEST_RUN:
                yield Finding(
                    "docs/test-report.md", number, "evidence", f"run {run_id} started {day}, before {EARLIEST_RUN}"
                )


def check_findings(documents: dict[str, Document]) -> Iterator[Finding]:
    for relative, doc in documents.items():
        if not relative.startswith("docs/findings/") or relative.endswith("README.md"):
            continue
        present = {text for _line, level, text in doc.headings if level == 2}
        missing = [heading for heading in FINDING_HEADINGS if heading not in present]
        if missing:
            yield Finding(relative, 1, "finding", "missing level-2 headings: " + ", ".join(missing))


def check_benchmark_issues(root: Path) -> Iterator[Finding]:
    for path in sorted((root / "conformance" / "benchmark").glob("*.json")):
        relative = path.relative_to(root).as_posix()
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            yield Finding(relative, 1, "benchmark", str(error))
            continue
        issues = {str(entry.get("issue", "")) for entry in entries if isinstance(entry, dict)}
        for issue in sorted(issues):
            if issue and not issue.startswith("https://") and not (root / issue).is_file():
                yield Finding(relative, 1, "benchmark", f"issue {issue} does not exist")


def run_checks(root: Path, today: dt.date) -> tuple[list[Finding], dict[str, int]]:
    documents = {relative: Document.read(root, relative) for relative in markdown_files(root)}
    findings: list[Finding] = []
    blocks = 0
    for doc in documents.values():
        findings += check_lint(doc)
        findings += check_links(doc, root, documents)
        findings += check_dated_commands(doc, today)
        if needs_dates(doc.relative):
            blocks += sum(1 for _o, _c, info in doc.blocks if info.split(" ")[0].lower() in COMMAND_LANGUAGES)
    findings += check_evidence(root)
    findings += check_findings(documents)
    findings += check_benchmark_issues(root)
    return findings, {"files": len(documents), "dated blocks": blocks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2], help="repository root")
    parser.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today(), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    findings, counts = run_checks(args.root.resolve(), args.today)
    for finding in findings:
        print(finding)
    summary = ", ".join(f"{value} {name}" for name, value in counts.items())
    print(f"check_docs: {summary}, {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
