"""The benchmark gate: classify every module of a run against the expected failures and skips.

The benchmark is two files per component in ``conformance/benchmark/``, in the suite's own format plus ``comment``,
``owner``, ``spec`` and ``issue`` (``conformance/schema/README.md``):

- ``<component>.expected-failures.json``: conditions that are allowed to fail or warn in a module;
- ``<component>.expected-skips.json``: modules the suite is allowed to skip.

An entry applies to a module when its ``test-name`` and ``configuration-filename`` patterns match (``fnmatch``, as
``run-test-plan.py`` does) and every key of its ``variant`` object has the module's value (``"*"`` matches every
variant). :func:`classify` turns the runner's verdicts into the benchmark verdicts of the verdict table:

- a FAILED or WARNING module whose every failure and warning is listed is a ``known_gap``;
- an unlisted condition, an unlisted skip, a module that did not finish or an unconfirmed REVIEW is a
  ``regression``;
- a listed condition that did not occur, or a listed skip of a module that ran, is a ``stale_benchmark``;
- a listed skip of a skipped module is ``not_applicable``.

The gate fails (exit 1) on any regression, and on any stale entry unless ``--allow-stale`` is given.

:func:`suite_gate_passes` computes the same decision the way ``run-test-plan.py`` does with the same files, that is
without the two harness extensions (the REVIEW evidence check and ``--allow-stale``), so the runner can cross-check
the two and fail loudly when they disagree.
"""

from __future__ import annotations

import dataclasses
import fnmatch
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from inji_conformance import model
from inji_conformance.collect import verdict_without_benchmark
from inji_conformance.model import (
    BenchmarkKind,
    BenchmarkRef,
    Component,
    ExitCode,
    ExpectedFailure,
    ExpectedResult,
    ExpectedSkip,
    ModuleResult,
    ModuleStatus,
    Severity,
    SuiteResult,
    Verdict,
)

BENCHMARK_RELATIVE = Path("conformance", "benchmark")


class BenchmarkError(Exception):
    """A benchmark file is missing or does not follow the contract."""


@dataclasses.dataclass(frozen=True)
class Benchmark:
    """The expected failures and skips of one component, with the files they came from."""

    failures: tuple[ExpectedFailure, ...] = ()
    skips: tuple[ExpectedSkip, ...] = ()
    files: tuple[Path, ...] = ()

    def entries_for(
        self, test_name: str, config_file: str, variant: Mapping[str, str]
    ) -> tuple[list[ExpectedFailure], list[ExpectedSkip]]:
        """The entries that apply to one module."""
        return (
            [entry for entry in self.failures if applies(entry, test_name, config_file, variant)],
            [entry for entry in self.skips if applies(entry, test_name, config_file, variant)],
        )

    def restricted_to(self, modules: Iterable[tuple[str, Mapping[str, str]]], config_file: str) -> Benchmark:
        """Only the entries that apply to at least one of ``modules`` (name, variant).

        ``run-test-plan.py`` fails a run when an entry matches no module of the run, so a run of selected modules
        (``--modules``) gives it only the entries for those modules.
        """
        modules = list(modules)

        def used(entry: ExpectedFailure | ExpectedSkip) -> bool:
            return any(applies(entry, name, config_file, variant) for name, variant in modules)

        return Benchmark(
            tuple(entry for entry in self.failures if used(entry)),
            tuple(entry for entry in self.skips if used(entry)),
            self.files,
        )

    def write(self, folder: Path, component: Component) -> tuple[Path, Path]:
        """Write the entries as the two benchmark files into ``folder`` (for ``run-test-plan.py``)."""
        folder.mkdir(parents=True, exist_ok=True)
        paths = (
            folder / f"{component.value}.expected-failures.json",
            folder / f"{component.value}.expected-skips.json",
        )
        for path, entries in zip(paths, (self.failures, self.skips), strict=True):
            text = json.dumps([entry.to_dict() for entry in entries], indent=2, ensure_ascii=False) + "\n"
            path.write_text(text, encoding="utf-8", newline="\n")
        return paths


def default_dir(home: Path) -> Path:
    return home / BENCHMARK_RELATIVE


def load(folder: Path, component: Component) -> Benchmark:
    """Read ``<component>.expected-failures.json`` and ``<component>.expected-skips.json`` from ``folder``.

    A missing file means no entries of that kind; an invalid one raises BenchmarkError naming every problem.
    """
    if not folder.is_dir():
        raise BenchmarkError(f"benchmark folder {folder} does not exist")
    failures: list[ExpectedFailure] = []
    skips: list[ExpectedSkip] = []
    files = []
    for kind, target in (
        (model.DocumentKind.EXPECTED_FAILURES, failures),
        (model.DocumentKind.EXPECTED_SKIPS, skips),
    ):
        path = folder / f"{component.value}.{kind.value}.json"
        if not path.is_file():
            continue
        try:
            target.extend(model.load_benchmark(path, kind))
        except model.ContractError as error:
            raise BenchmarkError(str(error)) from error
        except (OSError, json.JSONDecodeError) as error:
            raise BenchmarkError(f"cannot read {path}: {error}") from error
        files.append(path)
    return Benchmark(tuple(failures), tuple(skips), tuple(files))


def applies(
    entry: ExpectedFailure | ExpectedSkip, test_name: str, config_file: str, variant: Mapping[str, str]
) -> bool:
    """``run-test-plan.py``'s ``is_expected_for_this_test``: name and file name patterns, then the variant keys."""
    if not fnmatch.fnmatch(test_name, entry.test_name):
        return False
    if not fnmatch.fnmatch(config_file, entry.configuration_filename):
        return False
    if isinstance(entry.variant, str):
        return entry.variant == "*"
    return all(key in variant and variant[key] == value for key, value in entry.variant.items())


def _lists(entry: ExpectedFailure, failure: model.Failure) -> bool:
    """True when ``entry`` lists ``failure``: same condition, same block (or ``*``) and same severity."""
    severity = Severity.FAILURE if entry.expected_result is ExpectedResult.FAILURE else Severity.WARNING
    block = failure.block or ""
    return entry.condition == failure.condition and entry.current_block in ("*", block) and severity is failure.severity


def _ref(entry: ExpectedFailure | ExpectedSkip, matched: bool) -> BenchmarkRef:
    if isinstance(entry, ExpectedFailure):
        return BenchmarkRef(
            kind=BenchmarkKind.EXPECTED_FAILURE,
            comment=entry.comment,
            owner=entry.owner,
            spec=entry.spec,
            issue=entry.issue,
            matched=matched,
            condition=entry.condition,
            current_block=entry.current_block,
            expected_result=entry.expected_result,
        )
    return BenchmarkRef(
        kind=BenchmarkKind.EXPECTED_SKIP,
        comment=entry.comment,
        owner=entry.owner,
        spec=entry.spec,
        issue=entry.issue,
        matched=matched,
    )


def classify_module(
    module: ModuleResult, benchmark: Benchmark, config_file: str, plan_variant: Mapping[str, str]
) -> ModuleResult:
    """``module`` with ``failures[].expected``, ``benchmark`` refs, verdict and reason set from the benchmark."""
    variant = {**plan_variant, **(module.variant or {})}
    expected_failures, expected_skips = benchmark.entries_for(module.name, config_file, variant)

    used: set[int] = set()
    failures = []
    for failure in module.failures:
        listed = [index for index, entry in enumerate(expected_failures) if _lists(entry, failure)]
        used.update(listed)
        failures.append(dataclasses.replace(failure, expected=bool(listed)))
    skipped = module.result is SuiteResult.SKIPPED
    refs = [_ref(entry, index in used) for index, entry in enumerate(expected_failures)]
    refs += [_ref(entry, skipped) for entry in expected_skips]

    unexpected = sorted({f.condition for f in failures if not f.expected})
    stale = [ref for ref in refs if not ref.matched]
    # The verdict without a benchmark, recomputed so that an already classified file classifies the same way.
    verdict, reason = verdict_without_benchmark(module.status, module.result, failures, module.review)
    confirmed_review = module.result is SuiteResult.REVIEW and module.review is not None and module.review.confirmed

    if not module.completed:
        pass  # regression: "never started", "handoff not delivered or timeout"
    elif module.result is SuiteResult.SKIPPED:
        if expected_skips:
            verdict, reason = Verdict.NOT_APPLICABLE, None
        else:
            verdict, reason = Verdict.REGRESSION, "the suite skipped the module and no expected skip lists it"
    elif unexpected:
        verdict, reason = (
            Verdict.REGRESSION,
            f"result {_value(module.result)}: not in the benchmark: " + ", ".join(unexpected),
        )
    elif module.result is SuiteResult.REVIEW and not confirmed_review:
        pass  # regression: the review was not confirmed, the reason says why
    elif stale:
        verdict, reason = (
            Verdict.STALE_BENCHMARK,
            "listed but did not happen: " + ", ".join(_describe(ref) for ref in stale),
        )
    elif module.result in (SuiteResult.FAILED, SuiteResult.WARNING):
        if failures:
            verdict, reason = Verdict.KNOWN_GAP, None
        else:
            verdict, reason = Verdict.REGRESSION, f"result {_value(module.result)} with no logged condition"
    elif module.result is SuiteResult.PASSED or confirmed_review:
        verdict, reason = Verdict.CONFORMS, None
    return dataclasses.replace(
        module, failures=tuple(failures), benchmark=tuple(refs), verdict=verdict, verdict_reason=reason
    )


def _value(result: SuiteResult | None) -> str:
    return result.value if result else "none"


def _describe(ref: BenchmarkRef) -> str:
    if ref.kind is BenchmarkKind.EXPECTED_SKIP:
        return "expected skip (the module ran)"
    block = f" in block {ref.current_block!r}" if ref.current_block not in (None, "*", "") else ""
    return f"{ref.condition} ({ref.expected_result.value if ref.expected_result else 'failure'}){block}"


def gate_of(
    modules: Sequence[ModuleResult], benchmark: Benchmark, *, gating: bool, allow_stale: bool, home: Path | None
) -> model.Gate:
    """The gate for classified modules: exit 1 on a regression, or on a stale entry without ``allow_stale``."""
    summary = model.Summary.of(modules)
    failing = summary.regression + (0 if allow_stale else summary.stale_benchmark)
    passed = failing == 0 or not gating
    messages = [gate_line(summary)]
    for module in modules:
        if module.fails_gate and not (allow_stale and module.verdict is Verdict.STALE_BENCHMARK):
            messages.append(f"{module.verdict.value}: {module.name}: {module.verdict_reason}")
    if allow_stale and summary.stale_benchmark:
        messages.append(f"--allow-stale: {summary.stale_benchmark} stale benchmark entries only warn")
    if not gating:
        messages.append("this track never gates: the exit code ignores the verdicts")
    return model.Gate(
        passed=passed,
        exit_code=ExitCode.OK if passed else ExitCode.GATE_FAILED,
        allow_stale=allow_stale,
        benchmark_files=tuple(_display(path, home) for path in benchmark.files),
        messages=tuple(messages),
    )


def gate_line(summary: model.Summary) -> str:
    """The one-line outcome, for example ``gate: 0 regressions, 7 known gaps, 0 stale``."""
    return (
        f"gate: {summary.regression} regressions, {summary.known_gap} known gaps, {summary.stale_benchmark} stale"
        + (f", {summary.not_applicable} not applicable" if summary.not_applicable else "")
    )


def _display(path: Path, home: Path | None) -> str:
    """``path`` relative to the checkout, else its folder and name: results.json holds no absolute paths."""
    if home is not None:
        try:
            return path.resolve().relative_to(home.resolve()).as_posix()
        except ValueError:
            pass
    return f"{path.parent.name}/{path.name}" if path.parent.name else path.name


def classify(
    results: model.Results,
    benchmark: Benchmark,
    *,
    allow_stale: bool = False,
    home: Path | None = None,
    extra_messages: Sequence[str] = (),
) -> model.Results:
    """``results`` with every module classified, the summary recounted and the gate applied."""
    config_file = config_name(results)
    modules = tuple(classify_module(module, benchmark, config_file, results.plan.variant) for module in results.modules)
    # The track decides, not the file: a run written with --no-gate still gates when the gate command applies the
    # benchmark to it later. The haip readiness track never gates.
    gating = results.track is model.Track.GATE
    gate = gate_of(modules, benchmark, gating=gating, allow_stale=allow_stale, home=home)
    if extra_messages:
        gate = dataclasses.replace(gate, messages=(*gate.messages, *extra_messages))
    return dataclasses.replace(results, gating=gating, modules=modules, summary=model.Summary.of(modules), gate=gate)


def unused_entries(results: model.Results, benchmark: Benchmark) -> list[ExpectedFailure | ExpectedSkip]:
    """Entries that apply to no module of ``results`` (``run-test-plan.py`` fails a run that has one)."""
    config_file = config_name(results)
    modules = [(module.name, {**results.plan.variant, **(module.variant or {})}) for module in results.modules]
    return [
        entry
        for entry in (*benchmark.failures, *benchmark.skips)
        if not any(applies(entry, name, config_file, variant) for name, variant in modules)
    ]


def entry_label(entry: ExpectedFailure | ExpectedSkip) -> str:
    if isinstance(entry, ExpectedFailure):
        return f"{entry.test_name} {entry.condition} ({entry.expected_result.value})"
    return f"{entry.test_name} (expected skip)"


def config_name(results: model.Results) -> str:
    """The configuration file name the patterns are matched against, as ``run-test-plan.py`` was given it."""
    return results.plan.config_file or f"config/{results.component.value}.json"


def suite_gate_passes(results: model.Results) -> bool:
    """The gate as ``run-test-plan.py`` computes it from the same benchmark files.

    The suite counts REVIEW as a finished result and has no ``--allow-stale``. Entries that match no module of the
    run fail it too; :meth:`Benchmark.restricted_to` keeps those out of the files it is given.
    """
    for module in results.modules:
        if module.status not in (ModuleStatus.FINISHED, ModuleStatus.INTERRUPTED):
            return False  # the script counts INTERRUPTED as completed and analyses its log
        if module.verdict is Verdict.STALE_BENCHMARK:
            return False
        if module.verdict is Verdict.REGRESSION and not (
            module.result is SuiteResult.REVIEW and all(f.expected for f in module.failures)
        ):
            return False
    return True


def cross_check(results: model.Results, script_exit_code: int | None) -> str | None:
    """A message when the gate and ``run-test-plan.py``'s exit code disagree, None when they agree."""
    if script_exit_code is None:
        return None  # stopped at the time limit: there is no exit code to compare
    ours = suite_gate_passes(results)
    theirs = script_exit_code == 0
    if ours == theirs:
        return None
    return (
        f"cross-check failed: without the harness extensions the gate {'passes' if ours else 'fails'}, "
        f"but run-test-plan.py exited {script_exit_code} with the same benchmark files"
    )


def junit_xml(results: model.Results) -> str:
    """JUnit XML for CI: one test case per module; regressions and stale entries are failures."""
    from xml.sax.saxutils import escape, quoteattr

    summary = results.summary or model.Summary.of(results.modules)
    failing = sum(1 for module in results.modules if module.fails_gate)
    skipped = summary.not_applicable
    suite_name = f"inji-conformance.{results.component.value}.{results.plan.name}"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<testsuites name={quoteattr("inji-conformance")} tests="{summary.total}" failures="{failing}">',
        f'  <testsuite name={quoteattr(suite_name)} tests="{summary.total}" failures="{failing}" '
        f'skipped="{skipped}" errors="0">',
    ]
    for module in results.modules:
        time = f' time="{module.duration_s:.1f}"' if module.duration_s is not None else ""
        lines.append(f"    <testcase classname={quoteattr(suite_name)} name={quoteattr(module.name)}{time}>")
        if module.fails_gate:
            message = f"{module.verdict.value}: {module.verdict_reason or ''}"
            lines.append(f"      <failure message={quoteattr(message)} type={quoteattr(module.verdict.value)}>")
            for failure in module.failures:
                mark = "listed" if failure.expected else "NOT LISTED"
                lines.append(
                    "        "
                    + escape(f"{failure.severity.value} {failure.condition} [{mark}]: {failure.message or ''}")
                )
            lines.append("      </failure>")
        elif module.verdict is Verdict.NOT_APPLICABLE:
            lines.append(f"      <skipped message={quoteattr('expected skip')}/>")
        else:
            listed = [ref for ref in module.benchmark if ref.matched]
            if listed:
                text = "; ".join(f"{ref.condition or 'skip'}: {ref.comment} ({ref.issue})" for ref in listed)
                lines.append(f"      <system-out>{escape('known gap: ' + text)}</system-out>")
        lines.append("    </testcase>")
    lines += ["  </testsuite>", "</testsuites>", ""]
    return "\n".join(lines)


def as_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
