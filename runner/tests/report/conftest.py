"""Fixtures for the report tests: the two fixture runs and copies of them that a test may change."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"
# Set to 1 to rewrite the snapshot files from the current templates instead of comparing against them.
UPDATE_ENV = "INJI_CONFORMANCE_UPDATE_SNAPSHOTS"
# 2026-10-04T12:00:00Z: a fixed "generated at" time, so rendered pages are byte-identical between runs.
FIXED_EPOCH = "1791115200"


@pytest.fixture
def run_a() -> Path:
    return FIXTURES / "run-a"


@pytest.fixture
def run_b() -> Path:
    return FIXTURES / "run-b"


@pytest.fixture
def fixed_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", FIXED_EPOCH)


@pytest.fixture
def copied_runs(tmp_path: Path) -> Path:
    """A copy of both fixture runs under ``tmp_path/fixtures``, safe to change in a test."""
    target = tmp_path / "fixtures"
    for name in ("run-a", "run-b"):
        shutil.copytree(FIXTURES / name, target / name)
    return target


@pytest.fixture
def edit_json() -> Callable[[Path, Callable[[Any], None]], None]:
    """Returns ``edit(path, change)``: loads the JSON file, lets ``change`` modify it in place, writes it back."""

    def edit(path: Path, change: Callable[[Any], None]) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return edit
