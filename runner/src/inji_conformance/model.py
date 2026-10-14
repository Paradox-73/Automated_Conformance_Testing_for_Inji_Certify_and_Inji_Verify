"""Typed model of the harness's data contract, with loaders and validation.

Three kinds of file make up the contract, each with a JSON Schema in ``conformance/schema/``:

- ``results.json`` (version 1): one per component and run. The runner writes it; the gate, the HTML report, CI and
  the TestNG bridge in the testrigs read it.
- ``manifest.json``: one per run folder; what ran, on which commit and images, and where each results file is.
- benchmark files (``<component>.expected-failures.json`` and ``<component>.expected-skips.json``): the suite's own
  expected-failures and expected-skips format plus the required fields ``comment``, ``owner``, ``spec`` and
  ``issue``.

Validation has two layers. The JSON Schema checks the shape of a file. :func:`validate` then checks the rules a
schema cannot express: summary counts that match the modules, a gate result that matches the verdicts, and a
verdict that is possible for the suite's result (the verdict table in ``conformance/schema/README.md``). Readers
can then trust a validated file without re-deriving anything.

The dataclasses below mirror the schemas field for field. Optional fields that are absent in the file are ``None``
(or an empty tuple for lists) in the model, and :meth:`Document.to_dict` leaves them out again, so a load followed by
``to_dict`` gives back the original document.
"""

from __future__ import annotations

import dataclasses
import functools
import json
import os
import types
import typing
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import field
from datetime import datetime
from enum import Enum, IntEnum, StrEnum
from pathlib import Path
from typing import Any, ClassVar, Self

import jsonschema
import referencing
import referencing.jsonschema
from jsonschema.exceptions import ValidationError, best_match

# Environment variable that points at the folder holding the *.schema.json files. Needed only where the package is
# installed away from the repository (for example in a container image); in a checkout the folder is found by
# walking up from this file.
SCHEMA_DIR_ENV = "INJI_CONFORMANCE_SCHEMA_DIR"

RESULTS_SCHEMA_VERSION = "1"


# ---------------------------------------------------------------------------------------------------------------
# Enumerations. Values are the exact strings in the files.
# ---------------------------------------------------------------------------------------------------------------


class ExitCode(IntEnum):
    """Exit codes of the ``inji-conformance`` command, also recorded in ``gate.exit_code``."""

    OK = 0
    GATE_FAILED = 1  # a regression, or a stale benchmark entry without --allow-stale
    USAGE = 2  # usage or configuration error
    ENVIRONMENT_NOT_READY = 3  # also a run that collected no module results
    TIMEOUT = 4  # the whole run took longer than its time limit
    DIFF_CHANGED = 16  # "diff" only: the two runs differ (the convention of the suite's compare-results.py)


NO_MODULES = "no module results were collected (the plan was not created or the suite listed no modules)"


class Component(StrEnum):
    CERTIFY = "certify"
    VERIFY = "verify"


class RunMode(StrEnum):
    COMPONENT = "component"  # one component
    COMBINED = "combined"  # both components in one run


class Track(StrEnum):
    GATE = "gate"  # the OpenID4VCI 1.0 and OpenID4VP 1.0 Final plans the benchmark gates on
    HAIP = "haip"  # the HAIP certification plans, a readiness track that never changes the exit code


class ModuleStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"  # the harness's own value: a module of the plan that never started
    CREATED = "CREATED"
    CONFIGURED = "CONFIGURED"
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    INTERRUPTED = "INTERRUPTED"
    UNKNOWN = "UNKNOWN"


class SuiteResult(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"
    REVIEW = "REVIEW"
    SKIPPED = "SKIPPED"
    UNKNOWN = "UNKNOWN"


class Verdict(StrEnum):
    """The harness's verdict for one module, computed once by the runner and only mapped by every reader."""

    CONFORMS = "conforms"
    KNOWN_GAP = "known_gap"  # every problem is listed in the benchmark
    REGRESSION = "regression"  # fails the gate
    NOT_APPLICABLE = "not_applicable"  # an expected skip
    STALE_BENCHMARK = "stale_benchmark"  # a listed problem did not happen; fails the gate unless --allow-stale


class Severity(StrEnum):
    FAILURE = "FAILURE"
    WARNING = "WARNING"


class Owner(StrEnum):
    """Who has to act to remove a benchmark entry."""

    INJI = "inji"
    SUITE = "suite"
    ENVIRONMENT = "environment"


class ExpectedResult(StrEnum):
    FAILURE = "failure"
    WARNING = "warning"


class BenchmarkKind(StrEnum):
    EXPECTED_FAILURE = "expected_failure"
    EXPECTED_SKIP = "expected_skip"


class ReviewOutcome(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    MISSING = "missing"  # observed only: no verdict could be read from Inji Verify


class HandoffKind(StrEnum):
    AUTHORIZATION_REQUEST = "authorization_request"  # Inji Verify's request handed to the suite's wallet
    CREDENTIAL_OFFER = "credential_offer"  # Inji Certify's offer handed to the suite's wallet
    TX_CODE = "tx_code"
    START_TEST = "start_test"  # a module left in CONFIGURED was started
    BROWSER_VISIT = "browser_visit"  # a URL the suite asked a browser to open
    VERIFICATION_EVIDENCE = "verification_evidence"  # image of Inji Verify's verdict uploaded to the suite


class DocumentKind(StrEnum):
    """The kinds of file :func:`validate` knows, with the schema each one is checked against."""

    RESULTS = "results"
    RUN_MANIFEST = "run-manifest"
    EXPECTED_FAILURES = "expected-failures"
    EXPECTED_SKIPS = "expected-skips"

    @property
    def schema_ref(self) -> str:
        return _SCHEMA_REFS[self]


_RESULTS_ID = "urn:inji-conformance:schema:results:v1"
_MANIFEST_ID = "urn:inji-conformance:schema:run-manifest:v1"
_BENCHMARK_ID = "urn:inji-conformance:schema:benchmark:v1"
_SCHEMA_REFS = {
    DocumentKind.RESULTS: _RESULTS_ID,
    DocumentKind.RUN_MANIFEST: _MANIFEST_ID,
    DocumentKind.EXPECTED_FAILURES: _BENCHMARK_ID + "#/$defs/expected_failures_file",
    DocumentKind.EXPECTED_SKIPS: _BENCHMARK_ID + "#/$defs/expected_skips_file",
}
SCHEMA_FILES = ("results.schema.json", "run-manifest.schema.json", "benchmark.schema.json")


# ---------------------------------------------------------------------------------------------------------------
# Serialisation helpers shared by every dataclass.
#
# Field metadata:
#   key       the JSON key when it is not the Python name (benchmark files use "test-name" and similar)
#   nullable  write None as null instead of leaving the key out (for keys the schema requires, such as test_id)
#   always    write an empty list instead of leaving the key out
# ---------------------------------------------------------------------------------------------------------------


def _json_key(name: str) -> dict[str, str]:
    """Field metadata for a JSON key that is not a Python identifier (benchmark files use "test-name")."""
    return {"key": name}


_NULLABLE = {"nullable": True}
_ALWAYS = {"always": True}


class Document:
    """Base of every model class: generic conversion from and to the JSON form."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        """Build the object from a mapping that already passed schema validation."""
        hints = typing.get_type_hints(cls)
        kwargs = {}
        for item in dataclasses.fields(cls):  # type: ignore[arg-type]
            key = item.metadata.get("key", item.name)
            if key in data:
                kwargs[item.name] = _from_json(hints[item.name], data[key])
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        """The JSON form: enums as their values, tuples as lists, absent optional fields left out."""
        out: dict[str, Any] = {}
        for item in dataclasses.fields(self):  # type: ignore[arg-type]
            value = getattr(self, item.name)
            if value is None and not item.metadata.get("nullable"):
                continue
            if isinstance(value, tuple) and not value and not item.metadata.get("always"):
                continue
            out[item.metadata.get("key", item.name)] = _to_json(value)
        return out


def _from_json(tp: Any, value: Any) -> Any:
    origin = typing.get_origin(tp)
    if origin in (typing.Union, types.UnionType):
        if value is None:
            return None
        options = [arg for arg in typing.get_args(tp) if arg is not type(None)]
        # "X | None" converts as X. A union of plain JSON types (such as a benchmark variant, "*" or an object) is
        # kept as it is.
        return _from_json(options[0], value) if len(options) == 1 else value
    if origin is tuple:
        (inner, _ellipsis) = typing.get_args(tp)
        return tuple(_from_json(inner, item) for item in value)
    if origin in (dict, Mapping) or tp is Any:
        return value
    if isinstance(tp, type) and issubclass(tp, Document):
        return tp.from_dict(value)
    if isinstance(tp, type) and issubclass(tp, Enum):
        return tp(value)
    return value


def _to_json(value: Any) -> Any:
    if isinstance(value, Document):
        return value.to_dict()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple | list):
        return [_to_json(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _to_json(item) for key, item in value.items()}
    return value


# A variant as a benchmark entry states it: "*" (every variant) or the variant keys that must match.
VariantMatch = str | Mapping[str, str]


# ---------------------------------------------------------------------------------------------------------------
# Benchmark files
# ---------------------------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ExpectedFailure(Document):
    """One entry of ``<component>.expected-failures.json``: a condition that is allowed to fail or warn."""

    test_name: str = field(metadata=_json_key("test-name"))
    variant: VariantMatch
    configuration_filename: str = field(metadata=_json_key("configuration-filename"))
    current_block: str = field(metadata=_json_key("current-block"))
    condition: str
    expected_result: ExpectedResult = field(metadata=_json_key("expected-result"))
    comment: str
    owner: Owner
    spec: str
    issue: str

    @property
    def suite_key(self) -> tuple[Any, ...]:
        """The fields run-test-plan.py uses to find duplicate entries."""
        variant = self.variant if isinstance(self.variant, str) else tuple(sorted(self.variant.items()))
        return (self.test_name, variant, self.configuration_filename, self.condition, self.current_block)


@dataclasses.dataclass(frozen=True)
class ExpectedSkip(Document):
    """One entry of ``<component>.expected-skips.json``: a module the suite is allowed to skip."""

    test_name: str = field(metadata=_json_key("test-name"))
    variant: VariantMatch
    configuration_filename: str = field(metadata=_json_key("configuration-filename"))
    comment: str
    owner: Owner
    spec: str
    issue: str

    @property
    def suite_key(self) -> tuple[Any, ...]:
        variant = self.variant if isinstance(self.variant, str) else tuple(sorted(self.variant.items()))
        return (self.test_name, variant, self.configuration_filename, None, None)


BenchmarkEntry = ExpectedFailure | ExpectedSkip


# ---------------------------------------------------------------------------------------------------------------
# results.json v1
# ---------------------------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class SuiteInfo(Document):
    base_url: str
    version: str
    image: str | None = None
    digest: str | None = None


@dataclasses.dataclass(frozen=True)
class TargetInfo(Document):
    base_url: str
    image: str | None = None
    digest: str | None = None
    commit: str | None = None
    version: str | None = None


@dataclasses.dataclass(frozen=True)
class PlanInfo(Document):
    name: str
    variant: Mapping[str, str]
    id: str | None = None
    config_file: str | None = None
    export: str | None = None
    certification_profile: str | None = None


@dataclasses.dataclass(frozen=True)
class Failure(Document):
    """A FAILURE or WARNING log entry of a module."""

    condition: str
    severity: Severity
    message: str | None = None
    block: str | None = None
    requirements: tuple[str, ...] = ()
    expected: bool | None = None


@dataclasses.dataclass(frozen=True)
class BenchmarkRef(Document):
    """A benchmark entry that applies to a module, and whether the listed problem occurred."""

    kind: BenchmarkKind
    comment: str
    owner: Owner
    spec: str
    issue: str
    matched: bool
    condition: str | None = None
    current_block: str | None = None
    expected_result: ExpectedResult | None = None


@dataclasses.dataclass(frozen=True)
class Review(Document):
    """Checked outcome of a module the suite leaves in REVIEW."""

    expected: ReviewOutcome
    observed: ReviewOutcome
    evidence: str | None = field(default=None, metadata=_NULLABLE)

    @property
    def confirmed(self) -> bool:
        """True when Inji Verify showed the verdict the module expects and an evidence image exists."""
        return self.observed == self.expected and self.evidence is not None


@dataclasses.dataclass(frozen=True)
class Handoff(Document):
    kind: HandoffKind
    http_status: int | None = field(default=None, metadata=_NULLABLE)
    duration_ms: float = 0
    at: str | None = None
    detail: str | None = None
    error: str | None = None


@dataclasses.dataclass(frozen=True)
class Links(Document):
    suite_log: str | None = None
    export: str | None = None


@dataclasses.dataclass(frozen=True)
class ModuleResult(Document):
    """One test module of the plan."""

    name: str
    test_id: str | None = field(default=None, metadata=_NULLABLE)
    status: ModuleStatus = ModuleStatus.NOT_STARTED
    result: SuiteResult | None = field(default=None, metadata=_NULLABLE)
    verdict: Verdict = Verdict.REGRESSION
    verdict_reason: str | None = None
    description: str | None = None
    variant: Mapping[str, str] | None = None
    failures: tuple[Failure, ...] = field(default=(), metadata=_ALWAYS)
    benchmark: tuple[BenchmarkRef, ...] = field(default=(), metadata=_ALWAYS)
    review: Review | None = None
    handoffs: tuple[Handoff, ...] = field(default=(), metadata=_ALWAYS)
    links: Links | None = None
    duration_s: float | None = None

    @property
    def completed(self) -> bool:
        """True when the suite judged the module: FINISHED, or INTERRUPTED by a failing condition.

        The suite interrupts a module when a condition fails inside a request the module answers (for example the
        token request it makes while handling the transaction code). Such a module has the result FAILED and a
        FAILURE log entry, and ``run-test-plan.py`` analyses it like a finished one. An INTERRUPTED module without
        a logged failure (stopped by a person, or by the suite's time limit) did not complete.
        """
        if self.status is ModuleStatus.FINISHED:
            return True
        return (
            self.status is ModuleStatus.INTERRUPTED
            and self.result is SuiteResult.FAILED
            and any(failure.severity is Severity.FAILURE for failure in self.failures)
        )

    @property
    def fails_gate(self) -> bool:
        """True for a verdict that fails the gate when stale entries are not allowed."""
        return self.verdict in (Verdict.REGRESSION, Verdict.STALE_BENCHMARK)


@dataclasses.dataclass(frozen=True)
class Summary(Document):
    total: int
    conforms: int
    known_gap: int
    regression: int
    not_applicable: int
    stale_benchmark: int

    @classmethod
    def of(cls, modules: Sequence[ModuleResult]) -> Summary:
        """Counts for ``modules``; the runner writes this, and validation compares a file against it."""
        counts = dict.fromkeys(Verdict, 0)
        for module in modules:
            counts[module.verdict] += 1
        return cls(total=len(modules), **{verdict.value: count for verdict, count in counts.items()})


@dataclasses.dataclass(frozen=True)
class Gate(Document):
    passed: bool
    exit_code: ExitCode
    allow_stale: bool | None = None
    benchmark_files: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class Results(Document):
    """A whole ``results.json`` file."""

    schema_version: str
    run_id: str
    component: Component
    track: Track
    gating: bool
    suite: SuiteInfo
    target: TargetInfo
    plan: PlanInfo
    modules: tuple[ModuleResult, ...] = field(default=(), metadata=_ALWAYS)
    summary: Summary | None = None
    gate: Gate | None = None
    started_at: str | None = None
    finished_at: str | None = None
    notes: tuple[str, ...] = ()

    kind: ClassVar[DocumentKind] = DocumentKind.RESULTS

    def module(self, name: str) -> ModuleResult:
        """The module called ``name``; KeyError when the plan has no such module."""
        for module in self.modules:
            if module.name == name:
                return module
        raise KeyError(name)


# ---------------------------------------------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class HarnessInfo(Document):
    git_commit: str
    git_dirty: bool | None = None
    runner_version: str | None = None


@dataclasses.dataclass(frozen=True)
class ManifestSuite(Document):
    base_url: str
    version: str


@dataclasses.dataclass(frozen=True)
class ImageInfo(Document):
    service: str
    image: str
    digest: str | None = field(default=None, metadata=_NULLABLE)  # null: the image has no registry digest
    commit: str | None = None


@dataclasses.dataclass(frozen=True)
class ComponentRun(Document):
    component: Component
    plan: str
    results: str
    started_at: str | None = None
    finished_at: str | None = None
    wall_time_s: float | None = None
    exit_code: ExitCode | None = None


@dataclasses.dataclass(frozen=True)
class ManifestGate(Document):
    passed: bool
    exit_code: ExitCode


@dataclasses.dataclass(frozen=True)
class RunManifest(Document):
    """A run folder's ``manifest.json``."""

    schema_version: str
    run_id: str
    mode: RunMode
    track: Track
    started_at: str
    harness: HarnessInfo
    components: tuple[ComponentRun, ...]
    gate: ManifestGate
    parallel: bool | None = None
    finished_at: str | None = None
    wall_time_s: float | None = None
    command: tuple[str, ...] = ()
    suite: ManifestSuite | None = None
    images: tuple[ImageInfo, ...] = ()
    host: Mapping[str, str] | None = None
    notes: tuple[str, ...] = ()

    kind: ClassVar[DocumentKind] = DocumentKind.RUN_MANIFEST


# ---------------------------------------------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Issue:
    """One problem found in a document: where (a JSONPath such as ``$.modules[2].verdict``) and what."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class ContractError(ValueError):
    """A file does not follow the contract. ``issues`` lists every problem found."""

    def __init__(self, source: str, kind: DocumentKind | None, issues: Sequence[Issue]):
        self.source = source
        self.kind = kind
        self.issues = tuple(issues)
        what = f" as {kind.value}" if kind else ""
        lines = "\n".join(f"  {issue}" for issue in self.issues)
        super().__init__(f"{source} is not valid{what}:\n{lines}")


class SchemaNotFoundError(FileNotFoundError):
    """The JSON Schema folder could not be found (see SCHEMA_DIR_ENV)."""


# ---------------------------------------------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------------------------------------------


def find_schema_dir() -> Path:
    """The folder with the *.schema.json files.

    Order: the folder named by the environment variable ``INJI_CONFORMANCE_SCHEMA_DIR``; then
    ``conformance/schema`` in the nearest parent of this file (an editable install in a checkout); then the same
    below the current directory's parents.
    """
    configured = os.environ.get(SCHEMA_DIR_ENV)
    if configured:
        return require_schema_dir(configured, f"{SCHEMA_DIR_ENV}={configured}")
    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        for parent in (start, *start.parents):
            folder = parent / "conformance" / "schema"
            if (folder / SCHEMA_FILES[0]).is_file():
                return require_schema_dir(folder)
    raise SchemaNotFoundError(
        f"conformance/schema not found above {Path(__file__).parent} or the current directory; "
        f"set {SCHEMA_DIR_ENV} to the folder that holds {SCHEMA_FILES[0]}"
    )


def require_schema_dir(folder: str | os.PathLike[str], label: str | None = None) -> Path:
    """``folder`` as a Path when it holds every schema file; SchemaNotFoundError naming the missing ones otherwise."""
    path = Path(folder)
    missing = [name for name in SCHEMA_FILES if not (path / name).is_file()]
    if missing:
        raise SchemaNotFoundError(f"{label or path} has no {', '.join(missing)}")
    return path


@functools.cache
def _registry(schema_dir: Path) -> referencing.Registry:
    resources = []
    for name in SCHEMA_FILES:
        contents = json.loads((schema_dir / name).read_text(encoding="utf-8"))
        resources.append((contents["$id"], referencing.jsonschema.DRAFT202012.create_resource(contents)))
    return referencing.Registry().with_resources(resources)


def validator_for(kind: DocumentKind, schema_dir: Path | None = None) -> jsonschema.Draft202012Validator:
    """A JSON Schema validator for ``kind`` (formats such as date-time are checked where a checker exists)."""
    folder = require_schema_dir(schema_dir) if schema_dir else find_schema_dir()
    registry = _registry(folder.resolve())
    return jsonschema.Draft202012Validator(
        {"$ref": kind.schema_ref},
        registry=registry,
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
    )


def _json_path(parts: Sequence[str | int]) -> str:
    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def _schema_issues(data: Any, kind: DocumentKind, schema_dir: Path | None) -> list[Issue]:
    issues = []
    for error in sorted(validator_for(kind, schema_dir).iter_errors(data), key=lambda e: list(e.absolute_path)):
        # For anyOf / oneOf the top error only says "not valid under any schema"; the best sub-error says why.
        detail: ValidationError = best_match(error.context) if error.context else error  # type: ignore[assignment]
        issues.append(Issue(_json_path(list(detail.absolute_path)), detail.message))
    return issues


# ---------------------------------------------------------------------------------------------------------------
# Rules beyond the schema
# ---------------------------------------------------------------------------------------------------------------


def _check_times(started: str | None, finished: str | None, path: str) -> Iterator[Issue]:
    if started and finished and datetime.fromisoformat(finished) < datetime.fromisoformat(started):
        yield Issue(path, f"finished_at {finished} is before started_at {started}")


def _check_module(module: ModuleResult, path: str) -> Iterator[Issue]:
    """The verdict must be one the verdict table allows for the suite's outcome."""
    verdict = module.verdict
    unexpected = [f for f in module.failures if not f.expected]
    matched = {ref.kind for ref in module.benchmark if ref.matched}
    stale = [ref for ref in module.benchmark if not ref.matched]

    if verdict in (Verdict.REGRESSION, Verdict.STALE_BENCHMARK) and not module.verdict_reason:
        yield Issue(f"{path}.verdict_reason", f"required when the verdict is {verdict.value}")
    if verdict is not Verdict.REGRESSION and not module.completed:
        yield Issue(
            f"{path}.verdict",
            f"status {module.status.value} (not FINISHED, nor INTERRUPTED by a logged failure) must give the verdict "
            "regression",
        )
    if verdict in (Verdict.CONFORMS, Verdict.KNOWN_GAP, Verdict.STALE_BENCHMARK) and unexpected:
        names = ", ".join(sorted({f.condition for f in unexpected}))
        yield Issue(f"{path}.verdict", f"{verdict.value} with unexpected {names} (must be regression)")

    if verdict is Verdict.CONFORMS:
        if module.result is SuiteResult.REVIEW:
            if module.review is None or not module.review.confirmed:
                yield Issue(
                    f"{path}.review",
                    "conforms after REVIEW needs a review whose observed verdict matches "
                    "the expected one, with an evidence image",
                )
        elif module.result is not SuiteResult.PASSED:
            yield Issue(f"{path}.verdict", f"conforms needs the result PASSED or REVIEW, not {_name(module.result)}")
        if stale:
            yield Issue(f"{path}.verdict", "a benchmark entry did not match: the verdict must be stale_benchmark")
    elif verdict is Verdict.KNOWN_GAP:
        if module.result not in (SuiteResult.FAILED, SuiteResult.WARNING):
            yield Issue(f"{path}.verdict", f"known_gap needs the result FAILED or WARNING, not {_name(module.result)}")
        if not module.failures or BenchmarkKind.EXPECTED_FAILURE not in matched:
            yield Issue(f"{path}.benchmark", "known_gap needs failures listed by a matched expected_failure entry")
    elif verdict is Verdict.NOT_APPLICABLE:
        if BenchmarkKind.EXPECTED_SKIP not in matched:
            yield Issue(f"{path}.benchmark", "not_applicable needs a matched expected_skip entry")
        if module.result not in (SuiteResult.SKIPPED, SuiteResult.FAILED):
            yield Issue(
                f"{path}.verdict", f"not_applicable needs the result SKIPPED or FAILED, not {_name(module.result)}"
            )
    elif verdict is Verdict.STALE_BENCHMARK and not stale:
        yield Issue(f"{path}.benchmark", "stale_benchmark needs a benchmark entry with matched false")


def _name(result: SuiteResult | None) -> str:
    return result.value if result else "null"


def _check_results(results: Results) -> Iterator[Issue]:
    yield from _check_times(results.started_at, results.finished_at, "$")
    seen: dict[str, int] = {}
    for index, module in enumerate(results.modules):
        path = f"$.modules[{index}]"
        if module.name in seen:
            yield Issue(f"{path}.name", f"duplicate module {module.name} (also at index {seen[module.name]})")
        seen.setdefault(module.name, index)
        yield from _check_module(module, path)

    expected = Summary.of(results.modules)
    if results.summary is None or results.gate is None:  # the schema requires both; nothing more to compare
        return
    for item in dataclasses.fields(Summary):
        have, want = getattr(results.summary, item.name), getattr(expected, item.name)
        if have != want:
            yield Issue(f"$.summary.{item.name}", f"is {have}, the modules give {want}")

    gate = results.gate
    if gate.passed != (gate.exit_code == ExitCode.OK):
        yield Issue("$.gate", f"passed={str(gate.passed).lower()} does not match exit_code {int(gate.exit_code)}")
    if not results.modules and gate.passed:
        yield Issue("$.gate.passed", "true although the run has no module results")
    failing = expected.regression + (0 if gate.allow_stale else expected.stale_benchmark)
    if results.gating:
        if failing and gate.passed:
            yield Issue("$.gate.passed", f"true although {failing} modules fail the gate")
        if gate.exit_code == ExitCode.GATE_FAILED and not failing:
            yield Issue("$.gate.exit_code", "1 (gate failed) although no module fails the gate")
    elif gate.exit_code == ExitCode.GATE_FAILED:
        yield Issue("$.gate.exit_code", "a non-gating track never fails the gate")


def _check_manifest(manifest: RunManifest) -> Iterator[Issue]:
    yield from _check_times(manifest.started_at, manifest.finished_at, "$")
    seen: set[Component] = set()
    for index, run in enumerate(manifest.components):
        path = f"$.components[{index}]"
        if run.component in seen:
            yield Issue(f"{path}.component", f"duplicate component {run.component.value}")
        seen.add(run.component)
        yield from _check_times(run.started_at, run.finished_at, path)
    if manifest.mode is RunMode.COMPONENT and len(manifest.components) != 1:
        yield Issue("$.components", "mode component needs exactly one component")
    if manifest.mode is RunMode.COMBINED and seen != set(Component):
        yield Issue("$.components", "mode combined needs both certify and verify")
    gate = manifest.gate
    if gate.passed != (gate.exit_code == ExitCode.OK):
        yield Issue("$.gate", f"passed={str(gate.passed).lower()} does not match exit_code {int(gate.exit_code)}")
    failed = [run.component.value for run in manifest.components if run.exit_code not in (None, ExitCode.OK)]
    if failed and gate.passed:
        yield Issue("$.gate.passed", f"true although {', '.join(failed)} exited non-zero")


def _check_benchmark(entries: Sequence[BenchmarkEntry]) -> Iterator[Issue]:
    # run-test-plan.py drops a duplicate silently after a warning; here it is an error so the file stays clean.
    seen: dict[tuple[Any, ...], int] = {}
    for index, entry in enumerate(entries):
        if entry.suite_key in seen:
            yield Issue(
                f"$[{index}]",
                f"duplicates entry {seen[entry.suite_key]} (same test-name, variant, "
                "configuration-filename, condition and current-block)",
            )
        seen.setdefault(entry.suite_key, index)


# ---------------------------------------------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------------------------------------------


def detect_kind(path: str | os.PathLike[str], data: Any) -> DocumentKind | None:
    """Guess the kind of a document from its file name, then from its content; None when it cannot tell."""
    name = Path(path).name
    if "expected-failures" in name:
        return DocumentKind.EXPECTED_FAILURES
    if "expected-skips" in name:
        return DocumentKind.EXPECTED_SKIPS
    if "manifest" in name:
        return DocumentKind.RUN_MANIFEST
    if name.startswith("results"):
        return DocumentKind.RESULTS
    if isinstance(data, dict):
        if "modules" in data:
            return DocumentKind.RESULTS
        if "components" in data:
            return DocumentKind.RUN_MANIFEST
    if isinstance(data, list) and data and all(isinstance(item, dict) for item in data):
        return DocumentKind.EXPECTED_FAILURES if "condition" in data[0] else DocumentKind.EXPECTED_SKIPS
    return None


def parse(data: Any, kind: DocumentKind) -> Results | RunManifest | list[BenchmarkEntry]:
    """Turn a document that passed schema validation into model objects."""
    if kind is DocumentKind.RESULTS:
        return Results.from_dict(data)
    if kind is DocumentKind.RUN_MANIFEST:
        return RunManifest.from_dict(data)
    entry_type = ExpectedFailure if kind is DocumentKind.EXPECTED_FAILURES else ExpectedSkip
    return [entry_type.from_dict(item) for item in data]


def validate(data: Any, kind: DocumentKind, schema_dir: Path | None = None) -> list[Issue]:
    """Every problem in ``data`` as ``kind``: schema errors first; the further rules only when the shape is right."""
    issues = _schema_issues(data, kind, schema_dir)
    if issues:
        return issues
    parsed = parse(data, kind)
    if isinstance(parsed, Results):
        return list(_check_results(parsed))
    if isinstance(parsed, RunManifest):
        return list(_check_manifest(parsed))
    return list(_check_benchmark(parsed))


def read_json(path: str | os.PathLike[str]) -> Any:
    """Read a JSON file as UTF-8. Raises OSError or json.JSONDecodeError."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load(path: str | os.PathLike[str], kind: DocumentKind | None = None, schema_dir: Path | None = None) -> Any:
    """Read, validate and parse a file. Raises ContractError listing every problem."""
    data = read_json(path)
    kind = kind or detect_kind(path, data)
    if kind is None:
        raise ContractError(str(path), None, [Issue("$", "cannot tell which kind of file this is")])
    issues = validate(data, kind, schema_dir)
    if issues:
        raise ContractError(str(path), kind, issues)
    return parse(data, kind)


def load_results(path: str | os.PathLike[str], schema_dir: Path | None = None) -> Results:
    """A validated ``results.json``."""
    return load(path, DocumentKind.RESULTS, schema_dir)


def load_manifest(path: str | os.PathLike[str], schema_dir: Path | None = None) -> RunManifest:
    """A validated run ``manifest.json``."""
    return load(path, DocumentKind.RUN_MANIFEST, schema_dir)


def load_benchmark(
    path: str | os.PathLike[str], kind: DocumentKind | None = None, schema_dir: Path | None = None
) -> list[BenchmarkEntry]:
    """A validated benchmark file; the kind comes from the file name unless given."""
    data = read_json(path)
    kind = kind or detect_kind(path, data)
    if kind not in (DocumentKind.EXPECTED_FAILURES, DocumentKind.EXPECTED_SKIPS):
        raise ContractError(
            str(path),
            kind,
            [Issue("$", "not a benchmark file (name it *.expected-failures.json or *.expected-skips.json)")],
        )
    return load(path, kind, schema_dir)


def dump(document: Document, path: str | os.PathLike[str]) -> None:
    """Write a model object as JSON (UTF-8, LF line endings, two-space indent, trailing newline)."""
    text = json.dumps(document.to_dict(), indent=2, ensure_ascii=False) + "\n"
    Path(path).write_text(text, encoding="utf-8", newline="\n")
