# runner

Python package `inji_conformance` with the command `inji-conformance`. It drives the conformance suite's
`run-test-plan.py` (vendored unchanged in `third_party/`), answers every step where the suite waits for the system
under test, and turns the suite's exports into one results file, a benchmark verdict and a report.

Lane: runner, except `src/inji_conformance/report/` and `tests/report/`, which belong to the delivery lane.

## Status on 2026-10-04

| Part | State |
|---|---|
| `inji_conformance.model` | Done: typed model of `results.json` v1, the run manifest and the benchmark files, with loaders and validation |
| `inji-conformance validate` | Done |
| `run`, `seed`, `gate` | Registered with their options; they print "not available in this version" and exit 2 |
| `report`, `diff` | Registered; they run `inji_conformance.report`, which the delivery lane provides |

The data contract itself (schemas, rules, examples) is described in
[`conformance/schema/README.md`](../conformance/schema/README.md).

## Install and test

```bash
python -m venv "$HARNESS_RUN_DIR/venv"
"$HARNESS_RUN_DIR/venv/Scripts/python" -m pip install --editable "./runner[dev]"   # bin/ instead of Scripts/ on Linux and macOS
bash scripts/check.sh runner     # does the above, then ruff, pytest and validation of every schema example
```

Python 3.12 or newer. Runtime dependencies (`pyproject.toml`): `httpx` and `pyparsing` (imported by the vendored
suite scripts), `jinja2` (HTML report), `pillow` (evidence image for REVIEW modules), `jsonschema`. The `dev` extra
adds `pytest`, `respx` and `ruff`.

## Command reference

```text
inji-conformance run --component certify|verify | --combined [--target URL] [--modules A,B] [--track gate|haip]
                     [--no-gate] [--allow-stale] [--serial] [--no-seed] [--timeout-minutes N] [--out DIR]
inji-conformance seed certify
inji-conformance gate --run DIR [--benchmark-dir DIR] [--allow-stale] [--junit FILE]
inji-conformance report --run DIR [--combined] [--compare PREV] --out DIR
inji-conformance diff A B [--out DIR] [--strict]
inji-conformance validate FILE... [--kind results|run-manifest|expected-failures|expected-skips]
                          [--schema-dir DIR] [--quiet]
```

| Exit code | Meaning |
|---|---|
| 0 | Gate passed, or every file valid |
| 1 | Gate failed (a regression, or a stale benchmark entry without `--allow-stale`), or a file is invalid |
| 2 | Usage or configuration error (also: a subcommand not available in this version) |
| 3 | Environment not ready |
| 4 | The whole run hit its time limit |
| 16 | `diff` only: the two runs differ |

Example, from the repository root:

```text
$ inji-conformance validate conformance/schema/examples/results-verify.example.json
validate results-verify.example.json: valid (results v1, verify, 11 modules)
```

## How `report` and `diff` reach the report package

`cli.py` registers both subcommands and imports `inji_conformance.report` when the command starts. That package
provides `run_report(args) -> int` and `run_diff(args) -> int`, and may provide `add_report_arguments(parser)` and
`add_diff_arguments(parser)` to define its own options; otherwise the options in the reference above apply. If the
package is missing or fails to import, `report` and `diff` print the reason and exit 2, and every other subcommand
keeps working.

## Layout

| Path | Purpose |
|---|---|
| `pyproject.toml` | Package metadata, runtime dependencies, the `dev` extra, the `inji-conformance` command, ruff and pytest settings |
| `src/inji_conformance/model.py` | Data contract: dataclasses, schema loading, validation rules, `load_*` and `dump` |
| `src/inji_conformance/cli.py` | The `inji-conformance` command |
| `src/inji_conformance/report/` | HTML summary, badge and run diff (delivery lane) |
| `tests/` | pytest unit tests; no network, no containers |

## What `bash scripts/check.sh runner` does

1. Creates `$HARNESS_RUN_DIR/venv` if missing and runs `pip install --editable "./runner[dev]"` whenever
   `pyproject.toml` changes.
2. `ruff check runner`.
3. `pytest -q runner/tests`.
4. `inji-conformance validate <file>` for every `conformance/schema/examples/*.json`: exit status 0 for a valid
   file, non-zero for files named `*.invalid.json`, which must be rejected.

On Windows with Smart App Control on, a freshly written `inji-conformance.exe` launcher was once refused with
"Permission denied" (2026-10-04); `pip install --force-reinstall --no-deps --editable ./runner` into the same venv
wrote a launcher that ran.
