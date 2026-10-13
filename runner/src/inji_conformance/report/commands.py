"""The ``inji-conformance report`` and ``inji-conformance diff`` subcommands.

``report --run DIR [--run DIR] [--combined] [--compare PREV] --out DIR`` writes into ``--out``:

- ``summary.html``: the consolidated report (one self-contained page);
- ``badge.svg``: the status badge with per-component counts;
- ``summary.md``: a short Markdown table of the same counts, for a CI job summary or a pull request comment;
- ``diff.html``: only with ``--compare``, the run diff from PREV to this run.

``--run`` may be given more than once to report separate component runs together (for example a Certify run and a
Verify run made by two CI jobs). ``--combined`` asks for the consolidated cross-component report and fails with exit
code 2 when the runs do not hold results of both Inji Certify and Inji Verify. The report command exits 0 when the
files were written, whatever the gate says: the gate's exit code belongs to the run and the ``gate`` subcommand.

``diff A B [--out DIR] [--json FILE] [--strict]`` prints one line per difference and exits:

- 0 when the runs have the same verdicts, 16 when they differ (the convention of the suite's compare-results.py);
- with ``--strict``: 1 when B has a regression that A did not have, 0 otherwise (also when other things changed).

Both exit 2 when a run cannot be loaded; the message names the file and every problem found.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from inji_conformance import __version__
from inji_conformance.model import ExitCode, Verdict
from inji_conformance.report import badge, diff, html, runs

SUMMARY_FILE = "summary.html"
BADGE_FILE = "badge.svg"
MARKDOWN_FILE = "summary.md"
DIFF_FILE = "diff.html"


def add_report_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--run",
        required=True,
        type=Path,
        action="append",
        metavar="DIR",
        help="run folder (with manifest.json), component folder or results.json; repeat to report several together",
    )
    parser.add_argument(
        "--combined",
        action="store_true",
        help="consolidated report of both components; fails when the runs lack Inji Certify or Inji Verify results",
    )
    parser.add_argument(
        "--compare", type=Path, metavar="PREV", help="earlier run to compare against (writes diff.html)"
    )
    parser.add_argument("--out", required=True, type=Path, metavar="DIR", help="folder for summary.html and badge.svg")
    parser.add_argument("--schema-dir", type=Path, metavar="DIR", help=argparse.SUPPRESS)


def add_diff_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("before", type=Path, metavar="A", help="earlier run folder or results.json")
    parser.add_argument("after", type=Path, metavar="B", help="later run folder or results.json")
    parser.add_argument("--out", type=Path, metavar="DIR", help="also write diff.html into this folder")
    parser.add_argument("--json", type=Path, metavar="FILE", help="also write the differences as JSON")
    parser.add_argument("--strict", action="store_true", help="exit 1 only when B has a regression A did not have")
    parser.add_argument("--schema-dir", type=Path, metavar="DIR", help=argparse.SUPPRESS)


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 with LF endings through a temporary file, so a reader never sees a half-written report.

    Carriage returns inside the text (for example an error page a server answered with CRLF, quoted in a note) become
    plain line feeds, so the report is LF throughout.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def markdown_summary(run: runs.Run, run_diff: diff.RunDiff | None = None) -> str:
    """Counts per component as a Markdown table (for ``$GITHUB_STEP_SUMMARY`` and pull request comments)."""
    gate = {True: "passed", False: "failed", None: "not applied"}[run.gate_passed]
    lines = [
        f"### Inji conformance: gate {gate}",
        "",
        f"Run `{run.run_id}`",
        "",
        "| Component | Modules | Conforms | Known gap | Regression | Not applicable | Stale benchmark |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in run.components:
        s = item.summary
        counts = [s.conforms, s.known_gap, s.regression, s.not_applicable, s.stale_benchmark]
        lines.append(f"| {item.component.value} | {s.total} | " + " | ".join(str(c) for c in counts) + " |")
    regressions = [(item, m) for item, m in run.modules() if m.verdict is Verdict.REGRESSION]
    if regressions:
        lines += ["", "Regressions:", ""]
        lines += [
            f"- {item.component.value} `{m.name}`: {m.verdict_reason or 'no reason recorded'}"
            for item, m in regressions
        ]
    if run_diff is not None:
        counts = run_diff.counts()
        lines += [
            "",
            f"Compared with `{run_diff.before.run_id}`: {counts['changed']} changed, {counts['added']} added, "
            f"{counts['removed']} removed, {counts['new_regressions']} new regressions, {counts['fixed']} fixed.",
        ]
    return "\n".join(lines) + "\n"


def _error(command: str, message: str) -> int:
    print(f"{command}: {message}", file=sys.stderr)
    return ExitCode.USAGE


def run_report(args: argparse.Namespace) -> int:
    schema_dir = getattr(args, "schema_dir", None)
    sources = args.run if isinstance(args.run, list) else [args.run]
    try:
        run = runs.combine([runs.load_run(source, schema_dir) for source in sources])
        previous = runs.load_run(args.compare, schema_dir) if args.compare else None
    except runs.RunLoadError as error:
        return _error("report", str(error))
    if args.combined and not run.combined:
        found = ", ".join(item.component.value for item in run.components) or "none"
        return _error("report", f"--combined needs results of both certify and verify; found: {found}")

    out: Path = args.out
    meta = html.generated_now(f"inji-conformance {__version__}")
    run_diff = diff.diff_runs(previous, run) if previous else None
    written = []
    if run_diff is not None:
        write_text(out / DIFF_FILE, html.render_diff(run_diff, meta, ("Previous run", "This run")))
        written.append(DIFF_FILE)
    write_text(out / SUMMARY_FILE, html.render_summary(run, out, meta, run_diff, DIFF_FILE, BADGE_FILE))
    write_text(out / BADGE_FILE, badge.render_badge(badge.badge_for(run)))
    write_text(out / MARKDOWN_FILE, markdown_summary(run, run_diff))
    written[:0] = [SUMMARY_FILE, BADGE_FILE, MARKDOWN_FILE]

    print(f"report {run.run_id}: {badge.badge_for(run).message}")
    for name in written:
        print(f"wrote {out / name}")
    return ExitCode.OK


def run_diff(args: argparse.Namespace) -> int:
    schema_dir = getattr(args, "schema_dir", None)
    try:
        before = runs.load_run(args.before, schema_dir)
        after = runs.load_run(args.after, schema_dir)
    except runs.RunLoadError as error:
        return _error("diff", str(error))

    result = diff.diff_runs(before, after)
    sys.stdout.write(diff.format_text(result))
    if args.out:
        meta = html.generated_now(f"inji-conformance {__version__}")
        write_text(args.out / DIFF_FILE, html.render_diff(result, meta))
        print(f"wrote {args.out / DIFF_FILE}")
    if args.json:
        write_text(args.json, json.dumps(result.to_dict(), indent=2) + "\n")
        print(f"wrote {args.json}")
    return result.exit_code(strict=args.strict)
