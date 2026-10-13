"""The run manifest: ``manifest.json`` at the top of a run folder (``conformance/schema/run-manifest.schema.json``).

The runner writes it after every ``inji-conformance run``. What only the host knows comes in through the
environment, because the runner itself runs in a container without the git checkout or the Docker socket:

- ``HARNESS_GIT_COMMIT`` and ``HARNESS_GIT_DIRTY`` (``1`` or ``0``): the harness checkout;
- ``HARNESS_IMAGES_FILE``: a JSON list of ``{"service", "image", "digest", "commit"}``, one per container of the
  stack, written by ``run-conformance.sh`` after ``up``;
- ``HARNESS_COMMAND``: the host command line, one argument per line;
- ``HARNESS_HOST_OS``: a short description of the host.

Without ``HARNESS_GIT_COMMIT`` there is nothing valid to put in ``harness.git_commit``, so no manifest is written; a
report can still read the component folders.
"""

from __future__ import annotations

import json
import os
import platform
import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from inji_conformance import __version__, model
from inji_conformance.model import ComponentRun, ExitCode, RunMode, Track

ENV_GIT_COMMIT = "HARNESS_GIT_COMMIT"
ENV_GIT_DIRTY = "HARNESS_GIT_DIRTY"
ENV_IMAGES_FILE = "HARNESS_IMAGES_FILE"
ENV_COMMAND = "HARNESS_COMMAND"
ENV_HOST_OS = "HARNESS_HOST_OS"
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")


def seconds_between(started: str | None, finished: str | None) -> float | None:
    if not started or not finished:
        return None
    return round((datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds(), 1)


def component_entry(results: model.Results, out: Path, exit_code: int) -> ComponentRun:
    return ComponentRun(
        component=results.component,
        plan=results.plan.name,
        results=f"{results.component.value}/results.json",
        started_at=results.started_at,
        finished_at=results.finished_at,
        wall_time_s=seconds_between(results.started_at, results.finished_at),
        exit_code=ExitCode(exit_code),
    )


def _images() -> tuple[model.ImageInfo, ...]:
    path = os.environ.get(ENV_IMAGES_FILE)
    if not path or not Path(path).is_file():
        return ()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    images = []
    for item in data if isinstance(data, list) else ():
        if isinstance(item, dict) and item.get("service") and item.get("image"):
            images.append(
                model.ImageInfo(
                    service=str(item["service"]),
                    image=str(item["image"]),
                    digest=item.get("digest") or None,
                    commit=item.get("commit") or None,
                )
            )
    return tuple(images)


def build(
    run_id: str,
    mode: RunMode,
    track: Track,
    started_at: str,
    finished_at: str,
    components: Sequence[tuple[model.Results, int]],
    *,
    parallel: bool | None,
    out: Path,
    command: Sequence[str] = (),
) -> model.RunManifest | None:
    """The manifest of one run, or None without ``HARNESS_GIT_COMMIT``."""
    commit = os.environ.get(ENV_GIT_COMMIT, "").strip().lower()
    if not _COMMIT.match(commit):
        return None
    dirty = os.environ.get(ENV_GIT_DIRTY)
    host_command = [line for line in os.environ.get(ENV_COMMAND, "").splitlines() if line]
    entries = tuple(component_entry(results, out, code) for results, code in components)
    worst = max((code for _results, code in components), default=0)
    suite = next(
        (model.ManifestSuite(base_url=r.suite.base_url, version=r.suite.version) for r, _c in components), None
    )
    host: dict[str, Any] = {"python": platform.python_version()}
    if os.environ.get(ENV_HOST_OS):
        host["os"] = os.environ[ENV_HOST_OS]
    return model.RunManifest(
        schema_version=model.RESULTS_SCHEMA_VERSION,
        run_id=run_id,
        mode=mode,
        track=track,
        parallel=parallel,
        started_at=started_at,
        finished_at=finished_at,
        wall_time_s=seconds_between(started_at, finished_at),
        command=tuple(host_command or command),
        harness=model.HarnessInfo(
            git_commit=commit, git_dirty=None if dirty is None else dirty == "1", runner_version=__version__
        ),
        suite=suite,
        images=_images(),
        components=entries,
        gate=model.ManifestGate(passed=worst == 0, exit_code=ExitCode(worst)),
        host=host,
    )


def write(manifest: model.RunManifest, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / "manifest.json"
    model.dump(manifest, path)
    return path
