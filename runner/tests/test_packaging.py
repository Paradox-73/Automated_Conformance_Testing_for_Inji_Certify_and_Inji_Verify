"""runner/pyproject.toml declares what the runner and the vendored suite scripts need at run time."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1]
VENDORED_REQUIREMENTS = RUNNER.parent / "third_party" / "oidf-conformance-suite" / "scripts" / "requirements.txt"


def _names(requirements):
    return {re.split(r"[<>=!~\[; ]", line.strip(), maxsplit=1)[0].lower() for line in requirements if line.strip()}


def _project():
    return tomllib.loads((RUNNER / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_runtime_dependencies():
    assert _names(_project()["dependencies"]) == {"httpx", "pyparsing", "jinja2", "pillow", "jsonschema"}


def test_vendored_suite_scripts_requirements_are_declared():
    vendored = _names(VENDORED_REQUIREMENTS.read_text(encoding="utf-8").splitlines())
    assert vendored, "the vendored requirements.txt lists the suite scripts' imports"
    assert vendored <= _names(_project()["dependencies"])


def test_dev_extra_has_the_check_tools():
    assert {"pytest", "ruff", "respx"} <= _names(_project()["optional-dependencies"]["dev"])


def test_console_script():
    assert _project()["scripts"] == {"inji-conformance": "inji_conformance.cli:main"}
