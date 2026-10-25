"""Rendering ``summary.html`` and ``diff.html``.

The pages are Jinja2 templates (``templates/``) with the style sheet and script from ``assets/`` copied inline, so
each page is one file with no external requests. This module turns the loaded runs into plain view objects; the
templates only lay them out.

Every value a template prints passes through :func:`inji_conformance.report.redact.redact_value` (the engine's
``finalize`` hook) and is HTML-escaped. Links to files of the run folder are written relative to the output folder,
so a report written inside the run folder keeps working when the folder is copied or zipped.

What the pages never show: the rendered suite configuration (``plan.config_file`` in a results file names it, and it
holds the test clients' private keys). Nothing here reads that file, and its path is not printed either.
"""

from __future__ import annotations

import dataclasses
import functools
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from urllib.parse import quote, urlsplit

import jinja2
from markupsafe import Markup

from inji_conformance.model import (
    BenchmarkKind,
    BenchmarkRef,
    Component,
    Failure,
    Handoff,
    ImageInfo,
    ModuleResult,
    Review,
    Verdict,
    Workaround,
)
from inji_conformance.report.diff import Change, ModuleChange, RunDiff
from inji_conformance.report.redact import redact_value
from inji_conformance.report.runs import ComponentRun, Run

PACKAGE = "inji_conformance.report"


# ---------------------------------------------------------------------------------------------------------------
# Vocabulary shared by both pages and the tests
# ---------------------------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class VerdictStyle:
    label: str  # the word shown next to the icon
    css: str  # suffix of the CSS class and of the icon id
    rank: int  # sort order in the module table: what needs attention first


VERDICTS: dict[Verdict, VerdictStyle] = {
    Verdict.REGRESSION: VerdictStyle("Regression", "regression", 0),
    Verdict.STALE_BENCHMARK: VerdictStyle("Stale benchmark", "stale", 1),
    Verdict.KNOWN_GAP: VerdictStyle("Known gap", "gap", 2),
    Verdict.CONFORMS: VerdictStyle("Conforms", "conforms", 3),
    Verdict.NOT_APPLICABLE: VerdictStyle("Not applicable", "na", 4),
}

# Order of the verdict counts on a component card and of the filter checkboxes.
CARD_ORDER = (
    Verdict.CONFORMS,
    Verdict.KNOWN_GAP,
    Verdict.REGRESSION,
    Verdict.NOT_APPLICABLE,
    Verdict.STALE_BENCHMARK,
)

COMPONENT_TITLES = {
    Component.CERTIFY: ("Inji Certify", "issuer"),
    Component.VERIFY: ("Inji Verify", "verifier"),
}

HANDOFF_LABELS = {
    "authorization_request": "Authorization request handed to the suite's wallet",
    "credential_offer": "Credential offer handed to the suite's wallet",
    "tx_code": "Transaction code entered",
    "start_test": "Configured module started",
    "browser_visit": "Browser visit performed",
    "verification_evidence": "Evidence of Inji Verify's verdict uploaded",
}

CHANGE_LABELS = {
    Change.CHANGED: "Changed",
    Change.ADDED: "Added",
    Change.REMOVED: "Removed",
    Change.UNCHANGED: "Unchanged",
}


@dataclasses.dataclass(frozen=True)
class ReportMeta:
    """Facts about the report itself, printed in the footer."""

    generator: str  # for example "inji-conformance 0.1.0"
    generated_at: str  # ISO 8601 UTC


def generated_now(generator: str) -> ReportMeta:
    """Meta for a report made now. ``SOURCE_DATE_EPOCH`` (reproducible builds convention) fixes the time."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    moment = datetime.fromtimestamp(int(epoch), UTC) if epoch and epoch.isdigit() else datetime.now(UTC)
    return ReportMeta(generator, moment.strftime("%Y-%m-%dT%H:%M:%SZ"))


# ---------------------------------------------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------------------------------------------


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.astimezone(UTC) if moment.tzinfo is not None else moment


def format_time(value: str | None) -> str:
    """``2026-10-04T19:08:12Z`` as ``2026-10-04 19:08:12 UTC``; other offsets are converted to UTC."""
    if not value:
        return "not recorded"
    moment = _parse_time(value)
    return moment.strftime("%Y-%m-%d %H:%M:%S UTC") if moment else value


def format_duration(seconds: float | None) -> str:
    """``6.7 s``, ``17 min 44 s``, ``1 h 2 min``; empty for an unknown duration."""
    if seconds is None:
        return ""
    if seconds < 60:
        return f"{seconds:.1f} s"
    whole = round(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min {secs} s"


def _span(started: str | None, finished: str | None) -> float | None:
    start, end = _parse_time(started), _parse_time(finished)
    if start is None or end is None:
        return None
    return max((end - start).total_seconds(), 0.0)


def plural(count: int, singular: str, many: str | None = None) -> str:
    return f"{count} {singular if count == 1 else many or singular + 's'}"


def safe_url(value: str | None) -> str | None:
    """``value`` when it is an absolute http or https URL, else None.

    Results files are data written by the runner from suite responses; a ``javascript:`` or ``data:`` link taken
    from such a file must never become a clickable link.
    """
    if not value:
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    return value if parts.scheme in ("http", "https") and parts.netloc else None


# ---------------------------------------------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Linker:
    """Makes hrefs to files of a run, relative to the folder the page is written to."""

    out_dir: Path

    def to_run_file(self, item: ComponentRun, relative: str | None) -> str | None:
        """A relative href to a file that exists in the run folder, else None: the template then prints plain text.

        No href is made when the page has no relative path to the file (another drive on Windows): an absolute
        ``file:`` link breaks as soon as the folder is copied.
        """
        target = item.locate(relative)
        if target is None:
            return None
        try:
            relative_href = os.path.relpath(target, self.out_dir.resolve())
        except ValueError:
            return None
        return quote(Path(relative_href).as_posix())


def issue_href(issue: str) -> str | None:
    """A benchmark issue is a filed issue URL (linked) or a repository path to a draft (shown as text)."""
    return safe_url(issue) if issue.startswith("https://") else None


# ---------------------------------------------------------------------------------------------------------------
# View objects for the summary page
# ---------------------------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Fact:
    label: str
    value: str
    code: bool = False  # show in a fixed-width font


@dataclasses.dataclass(frozen=True)
class ImageRow:
    service: str
    image: str
    digest: str
    commit: str


@dataclasses.dataclass(frozen=True)
class GateView:
    """The gate as shown in the page header and on each card."""

    state: str  # "passed", "failed", "none" (not applied) or "info" (a non-gating track)
    text: str


@dataclasses.dataclass(frozen=True)
class Card:
    component: str
    title: str
    role: str
    plan: str
    variant: str
    track: str
    counts: tuple[tuple[Verdict, int], ...]
    gate: GateView
    target: str
    target_commit: str
    suite_version: str
    module_count: int
    duration: str
    export_href: str | None


@dataclasses.dataclass(frozen=True)
class FailureView:
    failure: Failure

    @property
    def listed(self) -> str:
        if self.failure.expected is True:
            return "listed in the benchmark"
        if self.failure.expected is False:
            return "not in the benchmark"
        return ""


@dataclasses.dataclass(frozen=True)
class BenchmarkView:
    ref: BenchmarkRef
    issue_href: str | None

    @property
    def kind(self) -> str:
        return "Expected failure" if self.ref.kind is BenchmarkKind.EXPECTED_FAILURE else "Expected skip"

    @property
    def matched_text(self) -> str:
        if self.ref.matched:
            return "the listed problem happened in this run"
        return "the listed problem did not happen: remove or update the entry"


@dataclasses.dataclass(frozen=True)
class Row:
    anchor: str
    component: str
    module: ModuleResult
    verdict: Verdict
    result: str
    failures: tuple[FailureView, ...]
    failure_summary: str
    benchmark: tuple[BenchmarkView, ...]
    review: Review | None
    evidence_href: str | None
    handoffs: tuple[Handoff, ...]
    duration: str
    suite_log: str | None
    export_href: str | None
    search: str

    @property
    def has_details(self) -> bool:
        m = self.module
        return bool(
            m.description or m.verdict_reason or m.failures or m.benchmark or m.review or m.handoffs or self.suite_log
        )


@dataclasses.dataclass(frozen=True)
class CompareView:
    previous_run_id: str
    counts: Mapping[str, int]
    diff_href: str
    highlights: tuple[ModuleChange, ...]
    context_count: int


@dataclasses.dataclass(frozen=True)
class WorkaroundView:
    component: str
    workaround: Workaround


@dataclasses.dataclass(frozen=True)
class Header:
    title: str
    run_id: str
    mode: str
    track: str
    started: str
    finished: str
    duration: str
    gate: GateView
    totals: tuple[tuple[Verdict, int], ...]
    module_total: int
    facts: tuple[Fact, ...]
    images: tuple[ImageRow, ...]
    notes: tuple[str, ...]
    workarounds: tuple[WorkaroundView, ...]


def _failure_summary(module: ModuleResult) -> str:
    if not module.failures:
        return "None"
    unlisted = sum(1 for f in module.failures if f.expected is not True)
    total = len(module.failures)
    if unlisted == 0:
        return f"{total} (all listed)"
    if unlisted == total:
        return f"{total} (none listed)" if any(f.expected is False for f in module.failures) else str(total)
    return f"{total} ({unlisted} not listed)"


def _rows(run: Run, linker: Linker) -> list[Row]:
    """One row per module, sorted by what needs attention first, then component, then plan order."""
    order = {item.component: position for position, item in enumerate(run.components)}
    keyed = []
    for position, (item, module) in enumerate(run.modules()):
        links = module.links
        search = " ".join(
            [item.component.value, module.name, VERDICTS[module.verdict].label]
            + [failure.condition for failure in module.failures]
        ).lower()
        row = Row(
            anchor=f"m-{item.component.value}-{module.name}",
            component=item.component.value,
            module=module,
            verdict=module.verdict,
            result=module.result.value if module.result else module.status.value,
            failures=tuple(FailureView(failure) for failure in module.failures),
            failure_summary=_failure_summary(module),
            benchmark=tuple(BenchmarkView(ref, issue_href(ref.issue)) for ref in module.benchmark),
            review=module.review,
            evidence_href=linker.to_run_file(item, module.review.evidence if module.review else None),
            handoffs=module.handoffs,
            duration=format_duration(module.duration_s),
            suite_log=safe_url(links.suite_log if links else None),
            export_href=linker.to_run_file(item, links.export if links else None),
            search=search,
        )
        keyed.append(((VERDICTS[module.verdict].rank, order[item.component], position), row))
    return [row for _key, row in sorted(keyed, key=lambda pair: pair[0])]


def _with_workarounds(view: GateView, count: int) -> GateView:
    """The gate text names the workarounds: a gate that passed with one passed against patched input."""
    return dataclasses.replace(view, text=f"{view.text} with {plural(count, 'workaround')}") if count else view


def _gate_of_component(item: ComponentRun) -> GateView:
    count = len(item.results.workarounds)
    if not item.results.gating:
        return _with_workarounds(GateView("info", f"Not gating ({item.results.track.value} track)"), count)
    if item.gate_passed is None:
        return _with_workarounds(GateView("none", "Gate not applied"), count)
    view = GateView("passed", "Gate passed") if item.gate_passed else GateView("failed", "Gate failed")
    return _with_workarounds(view, count)


def _gate_of_run(run: Run) -> GateView:
    passed = run.gate_passed
    count = sum(len(item.results.workarounds) for item in run.components)
    if passed is None:
        return _with_workarounds(GateView("none", "Gate not applied"), count)
    view = GateView("passed", "Gate passed") if passed else GateView("failed", "Gate failed")
    return _with_workarounds(view, count)


def _wall_time(run: Run, item: ComponentRun) -> float | None:
    """The component's wall time from its manifest entry, else the span of its results file."""
    for manifest in run.manifests:
        for entry in manifest.components:
            if entry.component is item.component and entry.wall_time_s is not None:
                return entry.wall_time_s
    return _span(item.results.started_at, item.results.finished_at)


def _cards(run: Run, linker: Linker) -> list[Card]:
    cards = []
    for item in run.components:
        results = item.results
        title, role = COMPONENT_TITLES[item.component]
        summary = item.summary
        cards.append(
            Card(
                component=item.component.value,
                title=title,
                role=role,
                plan=results.plan.name,
                variant=" · ".join(value for _key, value in sorted(results.plan.variant.items())),
                track=results.track.value,
                counts=tuple((verdict, getattr(summary, verdict.value)) for verdict in CARD_ORDER),
                gate=_gate_of_component(item),
                target=results.target.base_url,
                target_commit=results.target.commit or results.target.version or "not recorded",
                suite_version=results.suite.version,
                module_count=summary.total,
                duration=format_duration(_wall_time(run, item)),
                export_href=linker.to_run_file(item, results.plan.export),
            )
        )
    return cards


def _images(run: Run) -> list[ImageRow]:
    """Images from the manifests; for a run without one, the suite and target images named in the results."""
    images: dict[str, ImageInfo] = {}
    for manifest in run.manifests:
        for image in manifest.images:
            images.setdefault(image.service, image)
    if not images:
        for item in run.components:
            suite, target = item.results.suite, item.results.target
            if suite.image:
                images.setdefault("suite-server", ImageInfo("suite-server", suite.image, suite.digest))
            if target.image:
                service = item.component.value
                images.setdefault(service, ImageInfo(service, target.image, target.digest, target.commit))
    return [
        ImageRow(
            service=image.service,
            image=image.image,
            digest=image.digest or "none (no registry digest)",
            commit=image.commit or "not labelled",
        )
        for image in images.values()
    ]


def _header(run: Run) -> Header:
    manifest = run.manifest
    results = [item.results for item in run.components]
    if manifest:
        started, finished, wall = manifest.started_at, manifest.finished_at, manifest.wall_time_s
        mode = "Combined run" if manifest.mode.value == "combined" else "Component run"
        track = manifest.track.value
    else:
        starts = sorted(r.started_at for r in results if r.started_at)
        ends = sorted(r.finished_at for r in results if r.finished_at)
        started = starts[0] if starts else None
        finished = ends[-1] if ends else None
        wall = None
        mode = "Combined run" if run.combined else "Component run"
        track = ", ".join(dict.fromkeys(r.track.value for r in results))
    duration = format_duration(wall if wall is not None else _span(started, finished))

    facts: list[Fact] = []
    for item in run.manifests:
        dirty = {True: " (uncommitted changes)", False: " (clean)"}.get(item.harness.git_dirty, "")
        facts.append(Fact("Harness commit", item.harness.git_commit + dirty, code=True))
        if item.harness.runner_version:
            facts.append(Fact("Runner", f"inji-conformance {item.harness.runner_version}"))
        if item.parallel is not None:
            facts.append(Fact("Plans", "in parallel" if item.parallel else "one after the other"))
        if item.command:
            facts.append(Fact("Command", " ".join(item.command), code=True))
        for key, value in sorted((item.host or {}).items()):
            facts.append(Fact(f"Host {key}", value))
    suites = dict.fromkeys(f"{r.suite.version} at {r.suite.base_url}" for r in results)
    facts.insert(min(len(facts), 2), Fact("Suite", "; ".join(suites) or "not recorded"))

    notes = [note for m in run.manifests for note in m.notes] + [note for r in results for note in r.notes]
    module_total = sum(item.summary.total for item in run.components)
    return Header(
        title="Inji conformance report",
        run_id=run.run_id,
        mode=mode,
        track=track,
        started=format_time(started),
        finished=format_time(finished),
        duration=duration,
        gate=_gate_of_run(run),
        totals=tuple((verdict, run.count(verdict)) for verdict in CARD_ORDER),
        module_total=module_total,
        facts=tuple(facts),
        images=tuple(_images(run)),
        notes=tuple(dict.fromkeys(notes)),
        workarounds=tuple(
            WorkaroundView(item.component.value, w) for item in run.components for w in item.results.workarounds
        ),
    )


def _compare(diff: RunDiff, diff_href: str) -> CompareView:
    highlights = tuple(item for item in diff.differences if item.new_regression or item.fixed)
    return CompareView(
        previous_run_id=diff.before.run_id,
        counts=diff.counts(),
        diff_href=diff_href,
        highlights=highlights,
        context_count=len(diff.context),
    )


# ---------------------------------------------------------------------------------------------------------------
# Template engine
# ---------------------------------------------------------------------------------------------------------------


@functools.cache
def _asset(name: str) -> str:
    return resources.files(PACKAGE).joinpath("assets", name).read_text(encoding="utf-8")


@functools.cache
def _environment() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.PackageLoader(PACKAGE, "templates"),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
        finalize=redact_value,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.globals.update(
        VERDICTS=VERDICTS,
        CARD_ORDER=CARD_ORDER,
        HANDOFF_LABELS=HANDOFF_LABELS,
        CHANGE_LABELS=CHANGE_LABELS,
        Change=Change,
        plural=plural,
        format_time=format_time,
        # The style sheet and script are trusted package files, inlined unescaped.
        style=Markup(_asset("report.css")),
        script=Markup(_asset("report.js")),
    )
    return env


def render_summary(
    run: Run,
    out_dir: Path,
    meta: ReportMeta,
    diff: RunDiff | None = None,
    diff_href: str = "diff.html",
    badge_href: str = "badge.svg",
) -> str:
    """The consolidated report page of ``run``, with links relative to ``out_dir``."""
    linker = Linker(out_dir)
    rows = _rows(run, linker)
    return (
        _environment()
        .get_template("summary.html.j2")
        .render(
            header=_header(run),
            cards=_cards(run, linker),
            rows=rows,
            components=[item.component.value for item in run.components],
            compare=_compare(diff, diff_href) if diff else None,
            badge_href=badge_href,
            meta=meta,
        )
    )


@dataclasses.dataclass(frozen=True)
class DiffRow:
    change: ModuleChange
    label: str  # the word for the kind of change
    css: str


def _diff_rows(diff: RunDiff) -> list[DiffRow]:
    rows = []
    for item in diff.differences:
        if item.new_regression:
            rows.append(DiffRow(item, "New regression", "regression"))
        elif item.fixed:
            rows.append(DiffRow(item, "Fixed", "conforms"))
        else:
            rows.append(DiffRow(item, CHANGE_LABELS[item.change], item.change.value))
    return rows


def render_diff(diff: RunDiff, meta: ReportMeta, labels: Sequence[str] = ("Run A", "Run B")) -> str:
    """The run diff page: what changed between run A (``diff.before``) and run B (``diff.after``)."""
    return (
        _environment()
        .get_template("diff.html.j2")
        .render(diff=diff, rows=_diff_rows(diff), counts=diff.counts(), labels=labels, meta=meta)
    )
