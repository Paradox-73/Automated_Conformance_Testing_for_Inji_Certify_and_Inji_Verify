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
| `run --component verify` | Done: plan template, staged suite scripts, handoff responder, `results.json` without a benchmark |
| `run --component certify`, `run --combined` | Registered; say "this version runs --component verify only" and exit 2 |
| `seed`, `gate` | Registered with their options; they print "not available in this version" and exit 2 |
| `report`, `diff` | Done (delivery lane): consolidated HTML report, badge, run diff; see [`src/inji_conformance/report/README.md`](src/inji_conformance/report/README.md) |

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
inji-conformance report --run DIR [--run DIR] [--combined] [--compare PREV] --out DIR
inji-conformance diff A B [--out DIR] [--json FILE] [--strict]
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

## How `run` works

`inji-conformance run --component verify [--modules A,B] [--no-gate] [--target URL] [--timeout-minutes N] --out DIR`
runs the OpenID4VP verifier plan against Inji Verify. It runs in the compose `runner` container, where every
hostname of the test network resolves:

```bash
bash scripts/dc.sh --profile tools build runner
bash scripts/dc.sh --profile verify up -d --wait
bash scripts/dc.sh run --rm runner inji-conformance run --component verify \
  --modules oid4vp-1final-verifier-happy-flow --no-gate --out /reports/try1
bash scripts/dc.sh down -v
```

`/reports` in the container is `$HARNESS_RUN_DIR/reports` on the host. Steps:

1. Waits up to 120 s for the suite (`GET /api/server`) and Inji Verify (`GET /actuator/health`); exit 3 if either
   stays down.
2. Renders the plan template `conformance/plans/verify.oid4vp-1final-verifier.json`
   ([format](../conformance/plans/README.md)) into `<out>/verify/config/`. The alias is `inji-verify-<run id>`.
3. Copies `run-test-plan.py`, `conformance.py` and `test_plan_parser.py` unchanged from
   `third_party/oidf-conformance-suite/scripts/` into `<out>/verify/suite-scripts/`, with a `certs-keys/` folder
   holding the run's suite signing key. The script reads every file in the `certs-keys` folder next to itself and
   fills the config's `{suite-signing.jwk.json}` placeholder with it.
4. Starts `run-test-plan.py --export-dir exports <plan spec> config/<template>.json` with `CONFORMANCE_SERVER`,
   `CONFORMANCE_SERVER_MTLS` and `CONFORMANCE_DEV_MODE` set, and the handoff responder next to it. The script
   creates the plan and each module, waits for each to finish and exports the plan. Its output is shown with the
   prefix `suite |` and kept in `logs/run-test-plan.log`.
5. Reads each module from the suite (`/api/plan`, `/api/info`, `/api/log`) and writes `results.json`; deletes the
   staged `certs-keys/` folder, so the run folder holds no private key.

There is no benchmark yet (it comes in a later version), so every problem is a `regression`. A REVIEW result
counts as `conforms` only with an evidence image of Inji Verify's verdict, which a later version uploads; until
then a REVIEW module is recorded as `regression` with the reason "no evidence image". `--no-gate` writes
`gating: false` and exits 0 whatever the verdicts; without it the run exits 1 when any module is a regression.

Measured on 2026-10-04 (this laptop, compose profile `verify`, module `oid4vp-1final-verifier-happy-flow`,
`--no-gate`): exit code 0, run time 23 s after the stack was up; the module reached FINISHED with result FAILED;
one `authorization_request` handoff, HTTP 200 from the suite in 1750 ms. The failing conditions were
`ValidateRequestObjectSignatureAgainstX5cHeader` (the request object's x5c leaf is self-signed),
`EnsureHttpStatusCodeIs200` (Inji Verify's `direct-post` answered HTTP 500: its database has no
`vp_submission.response_code` column, see `compose/verify/init.sql`), and the warnings
`ValidateRequestObjectIssIfPresent` and `ValidateDirectPostResponse`. These are open items for the compose set-up
and the findings write-up, not runner errors.

| Exit code | Cause in `run` |
|---|---|
| 0 | Finished; gate passed, or `--no-gate` |
| 1 | Gate failed |
| 2 | Bad options or plan template |
| 3 | Suite or Inji Verify not reachable, or a run key missing |
| 4 | `--timeout-minutes` (default 30) reached: `run-test-plan.py` is stopped and `results.json` still records every module, unfinished ones as regressions (also with `--no-gate`) |

### The handoff responder

A thread that polls `GET /api/runner/running` every second and handles only tests whose alias is this run's alias
(`handoff.py`):

| Suite state | Action | `handoffs[].kind` |
|---|---|---|
| WAITING, `authorization_endpoint` exposed | `POST /v1/verify/v2/vp-request` at Inji Verify, then `GET <authorization_endpoint>?<query>` with the query string the Inji Verify SDK puts in its `openid4vp://authorize?` QR code | `authorization_request` |
| WAITING, `browser.urls` not yet visited | `GET` the URL, then `POST /api/runner/browser/{id}/visit` | `browser_visit` |
| CONFIGURED for 5 s | `POST /api/runner/{id}` (the suite starts nearly every test by itself) | `start_test` |

The query string comes from `authorization_query` in `inji_verify.py`, a line-by-line port of the SDK's
`getAuthorizationRequestParams` (`OpenID4VPVerification.tsx` lines 56-83, release-1.0.x). It serialises like the
browser's `URLSearchParams` (`~` encoded, `*` not, space as `+`), which `urllib.parse.urlencode` does not.
`tests/golden/sdk_query.mjs` runs the SDK function under Node.js on the cases in `sdk_query_cases.json`. The
golden test compares the Python output with the stored `sdk_query.json`; when Node.js is installed, a second test
checks that the stored file still matches what the SDK function produces.

Each handoff is printed as one line (`handoff authorization_request <module> (<test id>): HTTP 302 in 140 ms`),
appended to `logs/handoffs.jsonl` and copied into the module's `handoffs` in `results.json`.

### Run folder

```text
<out>/verify/results.json                                results.json v1 (conformance/schema/results.schema.json)
<out>/verify/config/verify.oid4vp-1final-verifier.json   rendered suite configuration, no keys
<out>/verify/exports/test-log-<plan id>.zip              the suite's plan export
<out>/verify/logs/run-test-plan.log                      the suite script's output
<out>/verify/logs/handoffs.jsonl                         one JSON line per handoff
<out>/verify/suite-scripts/                              staged suite scripts (keys removed after the run)
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
| `src/inji_conformance/run.py` | `run`: readiness checks, staging, the `run-test-plan.py` subprocess, results assembly |
| `src/inji_conformance/plans.py` | Plan templates: loading, `${...}` and certs-keys rendering, the plan spec |
| `src/inji_conformance/handoff.py` | The handoff responder thread and its handoff kinds |
| `src/inji_conformance/inji_verify.py` | Inji Verify API client and the SDK-identical query string |
| `src/inji_conformance/suite.py` | The suite REST calls the harness makes itself |
| `src/inji_conformance/collect.py` | Suite log entries and outcomes to `results.json` modules and verdicts |
| `Dockerfile` | Runner image; build context is the repository root, `Dockerfile.dockerignore` limits what is sent |
| `src/inji_conformance/report/` | HTML summary, badge and run diff (delivery lane) |
| `tests/` | pytest unit tests; no network, no containers (HTTP is mocked with respx) |
| `tests/golden/` | SDK query-string cases, the Node.js script that runs the SDK function on them, and its output |

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
