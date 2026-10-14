# Command reference

## Entry scripts

| Command | Does |
|---|---|
| `./run-conformance.sh --component certify\|verify [OPTIONS]` | one component: preflight, stack, runner, testrig step, report, teardown; exit code = gate |
| `./run-conformance.sh --combined [OPTIONS]` | both components, plans in parallel (`--serial` for one after the other) |
| `./run-full-stack-conformance.sh [--prepare-only \| --no-prepare] [OPTIONS]` | pull and build, then `run-conformance.sh --combined` |
| `bash scripts/dc.sh ARGS...` | `docker compose` with the project, files, `env.local` and the run folder set |
| `bash scripts/check.sh [eol secrets shell runner testrigs workflows docs \| all]` | the repository checks |
| `bash scripts/ci-local.sh certify\|verify [OPTIONS]` | the CI job of one component on this machine |
| `bash testrigs/build.sh [--image]` | the two testrig jars, and the testrig image |
| `bash testrigs/run-testrig.sh certify\|verify --results FILE \| --invoke [--out DIR]` | one api-testrig's conformance suite in the testrig image |
| `bash compose/smoke.sh PROFILE...` | start, check and remove a profile of the stack |
| `bash demo/demo.sh [--regression]` | the demo ([demo/README.md](../../demo/README.md)) |

Options of `run-conformance.sh`: `--runner-only`, `--keep-stack`, `--out NAME`, `--compare DIR`, and the runner
options below (`--modules`, `--track`, `--serial`, `--allow-stale`, `--variant`, `--template`, `--no-gate`,
`--no-seed`, `--timeout-minutes`), passed through unchanged. `./run-conformance.sh --help` prints examples.

## `inji-conformance` (the runner)

Inside the stack: `bash scripts/dc.sh run --rm runner inji-conformance ...`; on the host:
`run/venv/bin/inji-conformance ...` after `bash scripts/check.sh runner`.

| Subcommand | Does |
|---|---|
| `run (--component C \| --combined) [--target URL] [--modules A,B] [--track gate\|haip] [--no-gate] [--allow-stale] [--serial] [--no-seed] [--benchmark-dir DIR] [--template NAME] [--variant NAME=VALUE]... [--timeout-minutes N] [--out DIR] [--run-id ID]` | run the plan(s), answer the handoffs, apply the benchmark, write `<out>/<component>/results.json` and `<out>/manifest.json` |
| `seed certify [--target URL] [--track gate\|haip]` | create the credential configuration the issuer plan needs (idempotent: `created` or `already present`) |
| `gate --run DIR [--benchmark-dir DIR] [--allow-stale] [--junit FILE]` | classify a recorded run against the benchmark, print the gate, exit with its code |
| `report --run DIR [--run DIR]... [--combined] [--compare PREV] --out DIR` | `summary.html`, `badge.svg`, `summary.md`, and `diff.html` with `--compare` |
| `diff A B [--out DIR] [--json FILE] [--strict]` | compare the verdicts of two runs; exit 0 same, 16 different; `--strict`: 1 only for a new regression |
| `validate FILE... [--kind KIND] [-q]` | check results, manifest and benchmark files against the schemas and rules |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | gate passed (or `--no-gate`, or a non-gating track); file valid; runs the same |
| 1 | gate failed: a regression or a stale benchmark entry; a file is invalid |
| 2 | usage or configuration error, also a benchmark that matches no module or a gate that disagrees with `run-test-plan.py` |
| 3 | environment, not Inji: Docker, ports, a service or the suite did not answer; the suite or the Inji component stopped answering during a run whose gate failed; a component's run crashed; or the run collected no module results |
| 4 | the whole run reached its time limit; results are still written |
| 5 | internal error: the harness itself crashed outside a component run (a bug to report, not a verdict on Inji) |
| 16 | `diff`: the runs differ |

Only 1 says something about Inji's conformance. A CI job can therefore tell a regression (1) apart from an outage or a
crash (3, 5) and retry the latter. `./run-conformance.sh` exits with the highest code of the runner and the testrig
steps, so an outage in one component hides a regression in the other; the per-component `results.json` and the
report keep both.
