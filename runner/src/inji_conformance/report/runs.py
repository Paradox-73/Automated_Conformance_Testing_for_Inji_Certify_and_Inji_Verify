"""Loading run folders for the report and the diff.

A *run* is what one invocation of the harness produced. ``report`` and ``diff`` accept it in three shapes:

- a run folder holding ``manifest.json`` (the normal case, ``${HARNESS_RUN_DIR}/reports/<run id>/``): the manifest
  names each component's ``results.json``;
- a component folder holding only ``results.json`` (for example a copy of one component's results);
- the path of a ``results.json`` file itself.

Every file is validated against the contract in ``conformance/schema/`` while loading, so the rest of the report
package trusts the verdicts and never re-derives them.

Paths inside a results file are relative to the run folder (the folder with ``manifest.json``). Early results
files wrote module export paths relative to the component folder instead, so :meth:`ComponentRun.locate` tries the
run folder first and the component folder second.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Sequence
from pathlib import Path

from inji_conformance import model
from inji_conformance.model import Component, ModuleResult, Results, RunManifest, Summary, Verdict

MANIFEST_FILE = "manifest.json"
RESULTS_FILE = "results.json"

# Order of components on every page: the issuer side first, as in the problem statement.
COMPONENT_ORDER = (Component.CERTIFY, Component.VERIFY)


class RunLoadError(ValueError):
    """A run folder or file cannot be used: missing, unreadable or not following the contract."""


@dataclasses.dataclass(frozen=True)
class ComponentRun:
    """One component's validated results and where they came from."""

    results: Results
    results_path: Path
    run_root: Path

    @property
    def component(self) -> Component:
        return self.results.component

    @property
    def summary(self) -> Summary:
        """Counts per verdict: the file's own summary (validated to match), or computed when it has none."""
        return self.results.summary or Summary.of(self.results.modules)

    @property
    def gate_passed(self) -> bool | None:
        """The component gate as the runner recorded it; None when the gate was not applied (``--no-gate``)."""
        return self.results.gate.passed if self.results.gate else None

    def locate(self, relative: str | None) -> Path | None:
        """The existing file a contract path points to, or None when it is absent or not on this machine."""
        if not relative:
            return None
        for base in (self.run_root, self.results_path.parent):
            candidate = base / relative
            if candidate.is_file():
                return candidate
        return None


@dataclasses.dataclass(frozen=True)
class Run:
    """One or more component runs reported together, with the manifest of each run folder involved."""

    components: tuple[ComponentRun, ...]
    manifests: tuple[RunManifest, ...] = ()
    sources: tuple[Path, ...] = ()

    @property
    def manifest(self) -> RunManifest | None:
        """The manifest when exactly one run folder with a manifest is involved."""
        return self.manifests[0] if len(self.manifests) == 1 else None

    @property
    def run_id(self) -> str:
        """The run id; several ids joined with "+" for a report that combines separate runs."""
        ids = [m.run_id for m in self.manifests] or [c.results.run_id for c in self.components]
        return "+".join(dict.fromkeys(ids))

    @property
    def combined(self) -> bool:
        return {c.component for c in self.components} == set(COMPONENT_ORDER)

    @property
    def gate_passed(self) -> bool | None:
        """Overall gate: every manifest's gate, else every component gate; None when no gate was applied."""
        if self.manifests:
            return all(m.gate.passed for m in self.manifests)
        gates = [c.gate_passed for c in self.components if c.gate_passed is not None]
        return all(gates) if gates else None

    def component(self, component: Component) -> ComponentRun | None:
        for item in self.components:
            if item.component is component:
                return item
        return None

    def modules(self) -> Iterable[tuple[ComponentRun, ModuleResult]]:
        for item in self.components:
            for module in item.results.modules:
                yield item, module

    def count(self, verdict: Verdict) -> int:
        return sum(getattr(item.summary, verdict.value) for item in self.components)


def _load(loader, path: Path, schema_dir: Path | None):
    try:
        return loader(path, schema_dir)
    except FileNotFoundError as error:
        raise RunLoadError(f"{path}: no such file") from error
    except json.JSONDecodeError as error:
        raise RunLoadError(f"{path}: not JSON: {error}") from error
    except (OSError, UnicodeDecodeError) as error:
        raise RunLoadError(f"{path}: cannot read: {error}") from error
    except model.ContractError as error:
        raise RunLoadError(str(error)) from error


def _sorted(components: Iterable[ComponentRun]) -> tuple[ComponentRun, ...]:
    return tuple(sorted(components, key=lambda item: COMPONENT_ORDER.index(item.component)))


def load_run(path: str | Path, schema_dir: Path | None = None) -> Run:
    """Load a run folder (with ``manifest.json``), a component folder (with ``results.json``) or a results file.

    Raises :class:`RunLoadError` with a message that names the file and every problem.
    """
    path = Path(path)
    if path.is_file():
        if path.name == MANIFEST_FILE:
            path = path.parent
        else:
            results = _load(model.load_results, path, schema_dir)
            return Run((ComponentRun(results, path, path.parent),), (), (path,))
    if not path.is_dir():
        raise RunLoadError(f"{path}: no such run folder or results file")

    manifest_path = path / MANIFEST_FILE
    if manifest_path.is_file():
        manifest = _load(model.load_manifest, manifest_path, schema_dir)
        components = []
        for entry in manifest.components:
            results_path = path / entry.results
            results = _load(model.load_results, results_path, schema_dir)
            if results.component is not entry.component:
                raise RunLoadError(
                    f"{manifest_path}: {entry.results} holds {results.component.value} results, "
                    f"the manifest says {entry.component.value}"
                )
            components.append(ComponentRun(results, results_path, path))
        return Run(_sorted(components), (manifest,), (path,))

    results_path = path / RESULTS_FILE
    if results_path.is_file():
        results = _load(model.load_results, results_path, schema_dir)
        return Run((ComponentRun(results, results_path, path),), (), (path,))
    raise RunLoadError(f"{path}: holds neither {MANIFEST_FILE} nor {RESULTS_FILE}")


def combine(runs: Sequence[Run]) -> Run:
    """One run made of the components of several runs; each component may appear only once."""
    seen: dict[Component, Path] = {}
    for run in runs:
        for item in run.components:
            if item.component in seen:
                raise RunLoadError(
                    f"{item.component.value} appears twice: in {seen[item.component]} and in {item.results_path}"
                )
            seen[item.component] = item.results_path
    return Run(
        _sorted(item for run in runs for item in run.components),
        tuple(m for run in runs for m in run.manifests),
        tuple(source for run in runs for source in run.sources),
    )
