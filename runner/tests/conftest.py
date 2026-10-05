"""Shared fixtures for the runner's unit tests. The tests use no network and no containers."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "conformance" / "schema"
EXAMPLES_DIR = SCHEMA_DIR / "examples"


def _read_example(name: str) -> Any:
    return copy.deepcopy(json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8")))


@pytest.fixture(autouse=True)
def isolated_run_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep every test away from the developer's run folder and stack settings.

    ``inji-conformance run`` and ``seed`` read their defaults from the environment; without ``--out`` a run writes
    below ``$HARNESS_RUN_DIR`` (default ``<repo>/run``). Tests get an empty run folder under ``tmp_path`` and none
    of the ``HARNESS_*`` locations, so a test that reaches ``run_component`` cannot write into the repository.
    """
    for name in (
        "HARNESS_SUITE_URL",
        "HARNESS_SUITE_MTLS_URL",
        "HARNESS_VERIFY_URL",
        "HARNESS_CERTIFY_URL",
        "HARNESS_PKI_DIR",
        "HARNESS_REPORTS_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HARNESS_RUN_DIR", str(tmp_path / "harness-run"))


@pytest.fixture
def schema_dir() -> Path:
    return SCHEMA_DIR


@pytest.fixture
def examples_dir() -> Path:
    return EXAMPLES_DIR


@pytest.fixture
def load_example() -> Callable[[str], Any]:
    """Returns a function that reads an example file into a fresh object, safe to change in a test."""
    return _read_example


@pytest.fixture
def verify_results() -> dict[str, Any]:
    return _read_example("results-verify.example.json")


@pytest.fixture
def certify_results() -> dict[str, Any]:
    return _read_example("results-certify.example.json")
