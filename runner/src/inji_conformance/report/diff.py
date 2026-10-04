"""Comparing the verdicts of two runs.

Modules are matched by component and module name; the suite's test ids differ on every run and are ignored. A
module counts as *changed* when its verdict, its suite status or result, or its set of failing conditions (condition
class and severity) differs. Durations, handoff timings and links never count.

A *new regression* is a module whose verdict in run B is ``regression`` while it was something else in run A, or
was absent from A. ``inji-conformance diff --strict`` fails only on those.

Differences in what ran (harness commit, image digests and commit labels, suite version, plan variant) are listed
as *context* so a reader can see why verdicts moved. They never change the exit status.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from enum import StrEnum

from inji_conformance.model import ExitCode, ModuleResult, Verdict
from inji_conformance.report.runs import COMPONENT_ORDER, ComponentRun, Run


class Change(StrEnum):
    ADDED = "added"  # only in run B
    REMOVED = "removed"  # only in run A
    CHANGED = "changed"
    UNCHANGED = "unchanged"


# A failing condition as the diff compares it: (condition class, severity).
Condition = tuple[str, str]


def _conditions(module: ModuleResult | None) -> frozenset[Condition]:
    if module is None:
        return frozenset()
    return frozenset((failure.condition, failure.severity.value) for failure in module.failures)


def _outcome(module: ModuleResult | None) -> tuple[object, ...]:
    if module is None:
        return ()
    return (module.verdict, module.status, module.result, _conditions(module))


@dataclasses.dataclass(frozen=True)
class ModuleChange:
    """How one module differs between run A (``before``) and run B (``after``)."""

    component: str
    name: str
    change: Change
    before: ModuleResult | None
    after: ModuleResult | None

    @property
    def conditions_added(self) -> tuple[Condition, ...]:
        return tuple(sorted(_conditions(self.after) - _conditions(self.before)))

    @property
    def conditions_removed(self) -> tuple[Condition, ...]:
        return tuple(sorted(_conditions(self.before) - _conditions(self.after)))

    @property
    def new_regression(self) -> bool:
        """B is a regression and A was not (or A did not have the module)."""
        return (
            self.after is not None
            and self.after.verdict is Verdict.REGRESSION
            and (self.before is None or self.before.verdict is not Verdict.REGRESSION)
        )

    @property
    def fixed(self) -> bool:
        """A was a regression and B, which still has the module, is not."""
        return (
            self.before is not None
            and self.before.verdict is Verdict.REGRESSION
            and self.after is not None
            and self.after.verdict is not Verdict.REGRESSION
        )

    def to_dict(self) -> dict[str, object]:
        def side(module: ModuleResult | None) -> dict[str, object] | None:
            if module is None:
                return None
            return {
                "verdict": module.verdict.value,
                "status": module.status.value,
                "result": module.result.value if module.result else None,
            }

        return {
            "component": self.component,
            "module": self.name,
            "change": self.change.value,
            "new_regression": self.new_regression,
            "fixed": self.fixed,
            "before": side(self.before),
            "after": side(self.after),
            "conditions_added": [list(item) for item in self.conditions_added],
            "conditions_removed": [list(item) for item in self.conditions_removed],
        }


@dataclasses.dataclass(frozen=True)
class ContextChange:
    """Something about what ran that differs between the runs, for example an image's commit label."""

    subject: str
    before: str
    after: str

    def to_dict(self) -> dict[str, str]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class RunDiff:
    before: Run
    after: Run
    modules: tuple[ModuleChange, ...]
    context: tuple[ContextChange, ...]

    def of(self, change: Change) -> tuple[ModuleChange, ...]:
        return tuple(item for item in self.modules if item.change is change)

    @property
    def differences(self) -> tuple[ModuleChange, ...]:
        """Every module that is not unchanged: new regressions first, then changed, added, removed."""
        rank = {Change.CHANGED: 1, Change.ADDED: 2, Change.REMOVED: 3}
        return tuple(
            sorted(
                (item for item in self.modules if item.change is not Change.UNCHANGED),
                key=lambda item: 0 if item.new_regression else rank[item.change],
            )
        )

    @property
    def new_regressions(self) -> tuple[ModuleChange, ...]:
        return tuple(item for item in self.modules if item.new_regression)

    @property
    def fixed(self) -> tuple[ModuleChange, ...]:
        return tuple(item for item in self.modules if item.fixed)

    @property
    def same(self) -> bool:
        return not self.differences

    def counts(self) -> dict[str, int]:
        counts = {change.value: len(self.of(change)) for change in Change}
        counts["new_regressions"] = len(self.new_regressions)
        counts["fixed"] = len(self.fixed)
        return counts

    def exit_code(self, strict: bool = False) -> ExitCode:
        """0 same, 16 changed; with ``strict``: 1 when B has a new regression, 0 otherwise."""
        if strict:
            return ExitCode.GATE_FAILED if self.new_regressions else ExitCode.OK
        return ExitCode.OK if self.same else ExitCode.DIFF_CHANGED

    def to_dict(self) -> dict[str, object]:
        return {
            "before": {"run_id": self.before.run_id, "sources": [str(p) for p in self.before.sources]},
            "after": {"run_id": self.after.run_id, "sources": [str(p) for p in self.after.sources]},
            "same": self.same,
            "counts": self.counts(),
            "modules": [item.to_dict() for item in self.differences],
            "context": [item.to_dict() for item in self.context],
        }


def _module_changes(component: str, before: ComponentRun | None, after: ComponentRun | None) -> list[ModuleChange]:
    old = {m.name: m for m in before.results.modules} if before else {}
    new = {m.name: m for m in after.results.modules} if after else {}
    # Plan order of B, then modules only A had, in A's order.
    names = list(new) + [name for name in old if name not in new]
    changes = []
    for name in names:
        a, b = old.get(name), new.get(name)
        if a is None:
            change = Change.ADDED
        elif b is None:
            change = Change.REMOVED
        elif _outcome(a) != _outcome(b):
            change = Change.CHANGED
        else:
            change = Change.UNCHANGED
        changes.append(ModuleChange(component, name, change, a, b))
    return changes


def _text(value: object) -> str:
    return "none" if value in (None, "") else str(value)


def _context_changes(before: Run, after: Run) -> Iterator[ContextChange]:
    def compare(subject: str, a: object, b: object) -> Iterator[ContextChange]:
        if _text(a) != _text(b):
            yield ContextChange(subject, _text(a), _text(b))

    ma, mb = before.manifest, after.manifest
    if ma and mb:
        yield from compare("harness commit", ma.harness.git_commit, mb.harness.git_commit)
        yield from compare("track", ma.track.value, mb.track.value)
        images_a = {image.service: image for image in ma.images}
        images_b = {image.service: image for image in mb.images}
        for service in sorted(images_a.keys() | images_b.keys()):
            ia, ib = images_a.get(service), images_b.get(service)
            for field in ("image", "digest", "commit"):
                # getattr on None gives the default, so an image only one run used compares against "none".
                yield from compare(f"{service} {field}", getattr(ia, field, None), getattr(ib, field, None))
    for component in COMPONENT_ORDER:
        ca, cb = before.component(component), after.component(component)
        if ca is None or cb is None:
            if ca is not cb:
                yield ContextChange(
                    f"{component.value} results", "present" if ca else "absent", "present" if cb else "absent"
                )
            continue
        ra, rb = ca.results, cb.results
        prefix = component.value
        yield from compare(f"{prefix} suite version", ra.suite.version, rb.suite.version)
        yield from compare(f"{prefix} plan", ra.plan.name, rb.plan.name)
        for key in sorted(ra.plan.variant.keys() | rb.plan.variant.keys()):
            yield from compare(f"{prefix} variant {key}", ra.plan.variant.get(key), rb.plan.variant.get(key))
        yield from compare(f"{prefix} target image", ra.target.image, rb.target.image)
        yield from compare(f"{prefix} target digest", ra.target.digest, rb.target.digest)
        yield from compare(f"{prefix} target commit", ra.target.commit, rb.target.commit)


def diff_runs(before: Run, after: Run) -> RunDiff:
    """Compare run A (``before``) with run B (``after``)."""
    modules: list[ModuleChange] = []
    for component in COMPONENT_ORDER:
        ca, cb = before.component(component), after.component(component)
        if ca or cb:
            modules.extend(_module_changes(component.value, ca, cb))
    return RunDiff(before, after, tuple(modules), tuple(_context_changes(before, after)))


def _side(module: ModuleResult | None) -> str:
    if module is None:
        return "absent"
    result = module.result.value if module.result else module.status.value
    return f"{module.verdict.value} ({result})"


def format_text(diff: RunDiff, label_a: str = "A", label_b: str = "B") -> str:
    """The diff as plain text lines for a terminal or a CI log; one line per difference, then a total."""
    lines = [f"diff {label_a} {diff.before.run_id} -> {label_b} {diff.after.run_id}"]
    for item in diff.differences:
        text = f"{item.change.value:<8} {item.component:<8} {item.name}: {_side(item.before)} -> {_side(item.after)}"
        notes = [f"new failing condition {c} ({s})" for c, s in item.conditions_added]
        notes += [f"no longer failing {c} ({s})" for c, s in item.conditions_removed]
        if item.new_regression:
            notes.append("NEW REGRESSION")
        elif item.fixed:
            notes.append("fixed")
        lines.append(text + ("; " + "; ".join(notes) if notes else ""))
    for context in diff.context:
        lines.append(f"context  {context.subject}: {context.before} -> {context.after}")
    counts = diff.counts()
    lines.append(
        f"result: {'same' if diff.same else 'changed'}; {counts['changed']} changed, {counts['added']} added, "
        f"{counts['removed']} removed, {counts['unchanged']} unchanged; {counts['new_regressions']} new "
        f"{'regression' if counts['new_regressions'] == 1 else 'regressions'}, {counts['fixed']} fixed"
    )
    return "\n".join(lines) + "\n"
