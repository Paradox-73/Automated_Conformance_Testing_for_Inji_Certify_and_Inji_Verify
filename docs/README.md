# Install and run

Step by step from an empty machine to a conformance report of Inji Certify and Inji Verify. Every command block
below carries the date it was last run; on 2026-10-14 that was macOS 15.6.1 on Apple silicon with Docker Desktop
(Engine 28.3.0, Compose 2.38.1, a 4 GiB VM), GNU bash 5.3, Python 3.12.15. The same commands run in Git Bash on
Windows and in bash on Linux; the team's Windows measurements of 2026-10-04 are in [STATUS.md](STATUS.md).

Other documents: [architecture](architecture.md), [handoffs](handoffs.md), [API automation](api-automation.md),
[benchmark](benchmark.md), [testrig integration](testrig-integration.md), [CI](ci.md),
[configuration](configuration.md), [troubleshooting](troubleshooting.md),
[self-certification](self-certification.md), [command reference](reference/cli.md),
[results file](reference/results-schema.md), [test report](test-report.md), [Inji findings](findings/README.md).

## 1. Prerequisites

| Tool | Needed for | Windows | macOS | Linux |
|---|---|---|---|---|
| Git and bash 4.4+ | everything | Git for Windows (Git Bash) | `brew install git bash` (macOS ships bash 3.2) | distribution packages |
| Docker with Compose v2, at least 4 GiB of memory for Docker | the stack | Docker Desktop | Docker Desktop | Docker Engine and the Compose plugin |
| Python 3.12+ | repository checks | python.org installer | `brew install python@3.12` | distribution packages |
| JDK 21+ and Maven 3.9 (optional) | building the testrigs on the host; without them `testrigs/build.sh` builds in a container | Temurin 21 | `brew install openjdk maven` | distribution packages |
| shellcheck, actionlint (optional) | `bash scripts/check.sh shell workflows` | release binaries | `brew install shellcheck actionlint` | distribution packages |

About 10 GB of free disk: the suite, Inji and database images take about 6 GB, the testrig image 2.1 GB.

## 2. Get the code

<!-- run 2026-10-14 -->
```bash
git -c core.longpaths=true clone https://github.com/Paradox-73/Automated_Conformance_Testing_for_Inji_Certify_and_Inji_Verify.git ps01
cd ps01
```

Everything the harness writes at run time (passwords, keys, reports, logs) goes to `run/` in the clone, which git
ignores; `export HARNESS_RUN_DIR=...` moves it elsewhere.

## 3. Prepare once

<!-- run 2026-10-14 -->
```bash
./run-full-stack-conformance.sh --prepare-only
```

Pulls every image (about 2 GB compressed the first time) and builds the runner image and, with Maven or Docker, the
two testrig jars and the testrig image. Measured: 8 s with warm caches; the testrig build took 95 s with a warm Maven
cache.

## 4. Run

One component, conformance runner only (no testrig, no MinIO):

<!-- run 2026-10-14 -->
```bash
./run-conformance.sh --component verify --runner-only
./run-conformance.sh --component certify --runner-only
```

Both components in parallel, with the api-testrig step and the MinIO upload:

<!-- run 2026-10-14 -->
```bash
./run-full-stack-conformance.sh --no-prepare
```

Expected output, last lines (Inji Verify alone, 80 s on 2026-10-14):

```text
gate: 0 regressions, 0 known gaps, 0 stale
results: /reports/<run id>/verify/results.json (11 modules, gate passed)
run <run id> finished in 80 s, exit code 0
  run folder   .../run/reports/<run id>
  verify       .../run/reports/<run id>/verify/results.json
  report       .../run/reports/<run id>/report/summary.html
  badge        .../run/reports/<run id>/report/badge.svg
[info] stack stopped and removed
```

Exit codes: 0 gate passed, 1 gate failed (a regression or a stale benchmark entry; the lines above name the module
and condition), 2 usage or configuration error, 3 environment (a service did not answer or stopped answering, a run
crashed, or no module results were collected), 4 time limit, 5 harness bug. The full table is in
[reference/cli.md](reference/cli.md#exit-codes). `./run-conformance.sh
--help` lists every option.

## 5. Read the results

- `report/summary.html`: the consolidated report, one row per module with its verdict, failing conditions,
  handoffs, the benchmark entry that explains a known gap, and links to the suite's log and the extracted HTML
  export. `badge.svg` is the status badge.
- `<component>/results.json`: the same data for machines ([results file](reference/results-schema.md)).
- `manifest.json`: git commit, image digests, wall time per plan.
- `testrig/<component>/`: the api-testrig `EmailableReport`, also uploaded to MinIO
  (`http://127.0.0.1:18901` while the stack runs, bucket `automationtests`).

Compare two runs:

<!-- run 2026-10-14 -->
```bash
run/venv/bin/inji-conformance diff run/reports/wp10-combined-1 run/reports/wp10-combined-2
```

`run/venv` is the virtual environment `bash scripts/check.sh runner` creates; inside the stack the same command is
`bash scripts/dc.sh run --rm runner inji-conformance diff /reports/<run 1> /reports/<run 2>`.

## 6. Check the repository

<!-- run 2026-10-14 -->
```bash
bash scripts/check.sh all
```

Runs line endings, secrets, shellcheck and the shell tests, the runner's ruff and pytest, the testrig Maven
verify, actionlint and the documentation checks; [CONTRIBUTING.md](../CONTRIBUTING.md) explains each.
