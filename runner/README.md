# runner

Python package `inji_conformance` with the command `inji-conformance`. It drives the conformance suite's
`run-test-plan.py` (vendored unchanged in `third_party/`), answers every step where the suite waits for the system
under test, and turns the suite's exports into one results file, a benchmark verdict and a report.

Lane: runner, except `src/inji_conformance/report/` and `tests/report/`, which belong to the delivery lane.
Status on 2026-10-04: empty.

## Planned contents

| Path | Purpose |
|---|---|
| `pyproject.toml` | Package metadata, runtime dependencies, a `dev` extra with ruff and pytest, the `inji-conformance` command |
| `src/inji_conformance/` | Plan rendering, plan driver, handoff responder, Inji adapters, results and gate |
| `src/inji_conformance/report/` | HTML summary, badge and run diff (delivery lane) |
| `tests/` | pytest unit tests on recorded suite responses; no network |
| `Dockerfile` | Image that runs the runner on the compose network |

## What `bash scripts/check.sh runner` expects

The check runs once `runner/pyproject.toml` exists:

1. Creates `$HARNESS_RUN_DIR/venv` if missing and runs `pip install --editable "./runner[dev]"` whenever
   `pyproject.toml` changes. The `dev` extra must include `ruff` and `pytest`.
2. `ruff check runner`.
3. `pytest -q runner/tests` when `runner/tests/` exists.
4. `inji-conformance validate <file>` for every `conformance/schema/examples/*.json`: exit status 0 for a valid
   file, non-zero for files named `*.invalid.json`, which must be rejected.
