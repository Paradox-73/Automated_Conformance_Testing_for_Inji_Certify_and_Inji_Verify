# Contributing

How to set up a computer, run what exists today, and finish one of the remaining tasks. What is done and what is
left: [docs/STATUS.md](docs/STATUS.md).

## Tools and versions

Versions in the second column are the ones the team ran on 2026-10-04 (Windows 11 with Git Bash). Newer minor
versions are expected to work but have not been tried.

| Tool | Known to work | Needed for | Download |
|---|---|---|---|
| Git (on Windows: Git for Windows, which includes Git Bash) | Git for Windows 2.x | everything | <https://git-scm.com/downloads> |
| bash 4.4 or newer | Git Bash; bash on Linux | every script | Linux: built in. macOS ships bash 3.2: install a newer bash, for example with Homebrew (<https://brew.sh>, `brew install bash`) |
| Docker with Compose v2 | Docker Desktop 29.7.2, Compose 5.5.1 | the local stack | Windows and macOS: Docker Desktop <https://docs.docker.com/desktop/>. Linux: Docker Engine <https://docs.docker.com/engine/install/> plus the Compose plugin <https://docs.docker.com/compose/install/linux/> |
| Python 3.12 or newer | 3.12 | the runner, `bash scripts/check.sh runner`, `docs` | <https://www.python.org/downloads/> |
| JDK 21 | Temurin 21.0.12 | testrig lane only | <https://adoptium.net/temurin/releases/?version=21> |
| Maven 3.9 | 3.9.9 | testrig lane only | <https://maven.apache.org/download.cgi> |
| shellcheck | 0.11.0 | `bash scripts/check.sh shell` | <https://github.com/koalaman/shellcheck#installing> |
| actionlint | 1.7.12 | `bash scripts/check.sh workflows` (once `.github/` exists) | <https://github.com/rhysd/actionlint/blob/main/docs/install.md> |
| Node.js (optional) | - | one extra golden test of the runner; `npx --yes html-validate` on reports | <https://nodejs.org/en/download> |
| GitHub CLI `gh` (optional) | - | opening pull requests from the terminal | <https://cli.github.com/> |

- Docker memory: the measured peaks were 0.9 GiB for the `verify` profile and 1.5 GiB for `certify` plus
  `reports`; the runner and testrig containers come on top. The team laptop gave Docker an 8 GB VM shared with
  other projects.
- Disk: the suite images take about 2.3 GB, the Inji Certify image about 2.0 GB, plus Postgres, MinIO, nginx and
  Inji Verify. A cold Maven build of one testrig downloads several hundred MB into `~/.m2`.
- Tools that are not on `PATH` can go in `$HARNESS_TOOLS_DIR/bin` (default `$HARNESS_RUN_DIR/tools/bin`):
  `scripts/check.sh` looks there for shellcheck, actionlint and Maven.

## One-time setup

1. Clone with long paths on (the imported Inji test trees have paths longer than Windows allows by default):

   ```bash
   git -c core.longpaths=true clone https://github.com/Paradox-73/Automated_Conformance_Testing_for_Inji_Certify_and_Inji_Verify.git inji-conformance-harness
   cd inji-conformance-harness
   git config core.longpaths true
   ```

2. Commit under your own GitHub identity (the email must be one verified on your GitHub account):

   ```bash
   git config user.name  "Your Name"
   git config user.email "you@example.com"
   ```

3. Choose the run folder. Everything the harness writes at run time (generated passwords, keys, reports, the
   Python virtual environment, logs) goes to `HARNESS_RUN_DIR`, default `<repo>/run`, which git ignores. To keep it
   outside the clone, export it in every shell, for example in `~/.bashrc`:

   ```bash
   export HARNESS_RUN_DIR="$HOME/inji-harness-run"
   ```

4. Check that the repository checks run (this also creates the Python virtual environment in
   `$HARNESS_RUN_DIR/venv` and installs the runner into it):

   ```bash
   bash scripts/check.sh all
   ```

   Expected: `PASS` for eol, secrets, shell and runner (shell needs shellcheck), `PASS` or `SKIP` for testrigs
   (needs JDK 21 and Maven), `SKIP` for workflows and docs (their inputs do not exist yet). The runner tests took
   about 4 minutes on the team laptop.

5. Pull the images once (about 2 GB compressed):

   ```bash
   bash scripts/dc.sh --profile verify pull
   bash scripts/dc.sh --profile certify --profile reports pull
   bash scripts/dc.sh --profile tools build runner
   ```

## Settings read from the environment

| Variable | Default | Meaning |
|---|---|---|
| `HARNESS_RUN_DIR` | `<repo>/run` | Run folder (see above). |
| `HARNESS_COMPOSE_PROJECT` | `ps01-harness` | Compose project name; must start with `ps01-`. |
| `HARNESS_TOOLS_DIR` | `$HARNESS_RUN_DIR/tools` | Extra tools in `<dir>/bin`. |
| `HARNESS_CHECK_STRICT` | `0` | `1` turns a missing tool into a check failure (`CI=true` does the same). |
| `MAVEN_ARGS` | unset | Extra Maven options for `bash scripts/check.sh testrigs`, for example a settings file with a mirror. |
| `SMOKE_START_TIMEOUT`, `SMOKE_STATS_INTERVAL` | `420`, `3` | Seconds `compose/smoke.sh` waits for a healthy stack, and between memory samples. |
| `PKI_FORCE` | unset | `1` makes `pki-init` write a new key set. |
| `VERIFY_IMAGE`, `CERTIFY_IMAGE`, `SUITE_SERVER_IMAGE`, ... | pinned digests in `docker-compose.yml` | Run against other images; full list in [compose/README.md](compose/README.md). |
| `MINIO_ROOT_USER` | `harness` | MinIO user; its password `MINIO_ROOT_PASSWORD` is generated into `$HARNESS_RUN_DIR/env.local`. |
| `OIDF_SUITE_CLONE`, `OIDF_SUITE_URL` | see [third_party/README.md](third_party/README.md) | Where `bash third_party/reimport.sh verify` finds the upstream suite. |
| `HARNESS_SUITE_URL`, `HARNESS_VERIFY_URL`, `HARNESS_CERTIFY_URL`, `HARNESS_PKI_DIR`, `HARNESS_REPORTS_DIR` | set by the `runner` service | Where the runner finds the suite, Inji and the keys; only needed when running the runner outside Compose. |

`scripts/dc.sh` writes `$HARNESS_RUN_DIR/env.local` on first use with random passwords (`VERIFY_DB_PASSWORD`,
`CERTIFY_DB_PASSWORD`, `CERTIFY_KEYSTORE_PASSWORD`, `MINIO_ROOT_PASSWORD`). It is never committed. Delete it only
together with the volumes (`bash scripts/dc.sh --profile '*' down -v`).

## Build and test

| Command | What it checks | Needs |
|---|---|---|
| `bash scripts/check.sh all` | every check below that has inputs | see each line |
| `bash scripts/check.sh eol secrets` | LF line endings; no keys or passwords in files git would commit | git |
| `bash scripts/check.sh shell` | shellcheck on every script, then `scripts/tests/test-*.sh` | shellcheck |
| `bash scripts/check.sh runner` | ruff, pytest (`runner/tests`), validation of `conformance/schema/examples/*.json` | Python 3.12 |
| `bash scripts/check.sh testrigs` | `mvn verify` of the bridge library `testrigs/apitest-commons-conformance` | JDK 21, Maven 3.9 |
| `bash third_party/reimport.sh check` | the vendored suite scripts still match their import | bash |
| `mvn -B -f testrigs/pom.xml -pl apitest-commons-conformance,inji-verify-api-test -am package -Dgpg.skip=true -Dmaven.gitcommitid.skip=true` | builds the bridge and the Inji Verify rig's shaded jar (8 min 23 s with a warm shared cache on 2026-10-04) | JDK 21, Maven 3.9 |

The runner's virtual environment can also be used directly:

```bash
"$HARNESS_RUN_DIR/venv/Scripts/python" -m pytest -q runner/tests     # Linux and macOS: venv/bin/python
"$HARNESS_RUN_DIR/venv/Scripts/inji-conformance" --help              # Linux and macOS: venv/bin/inji-conformance
```

## The local stack

Always call Compose through `scripts/dc.sh`. It adds the project name, the root `docker-compose.yml`, the
generated `env.local`, and on Windows turns off Git Bash path rewriting. A plain `docker compose` fails with a
missing `VERIFY_DB_PASSWORD`.

```bash
bash scripts/dc.sh --profile verify up -d --wait                 # suite + Inji Verify + TLS proxy
bash scripts/dc.sh --profile certify --profile reports up -d --wait   # suite + Inji Certify + TLS proxy + MinIO
bash scripts/dc.sh --profile '*' down -v                          # stop everything and delete the volumes
bash compose/smoke.sh verify                                      # start, check, measure, remove
bash compose/smoke.sh certify reports
```

Always stop with `--profile '*'`: a plain `down` leaves profiled services running.

| Profile | Services |
|---|---|
| `suite` | `suite-mongodb`, `suite-server`, `suite-nginx` |
| `verify` | the suite, `verify-db`, `verify-service`, `pki-init`, `tls-proxy` |
| `certify` | the suite, `certify-db`, `certify`, `pki-init`, `tls-proxy` |
| `reports` | `minio` with the bucket `automationtests` |
| `tools` | one-off containers for `bash scripts/dc.sh run --rm`: `runner`, `probe` (curl), `minio-mc`, `pki-init` |

Host ports, all bound to 127.0.0.1 only:

| Port | What | Open from the host |
|---|---|---|
| 18443 | suite web page and API | `https://localhost.emobix.co.uk:18443` (self-signed certificate; the name is public DNS for 127.0.0.1) |
| 18444 | suite mTLS listener | - |
| 18450 | Inji Certify over TLS (`https://certify.inji.test:18450` inside the network) | only through containers |
| 18451 | Inji Verify over TLS (`https://verify.inji.test:18451/v1/verify` inside the network) | only through containers |
| 18460, 18461 | Inji Certify and Inji Verify over plain HTTP, for debugging | `http://127.0.0.1:18461/v1/verify/...` |
| 18900, 18901 | MinIO S3 API and web console | `http://127.0.0.1:18901`, user `harness`, password `MINIO_ROOT_PASSWORD` from `env.local` |

The `*.inji.test` names exist only inside the Compose network, so everything that calls them (the runner, the
testrigs, `probe`) runs in a container. Example:
`bash scripts/dc.sh run --rm probe --cacert /pki/ca.crt https://verify.inji.test:18451/v1/verify/actuator/health`.
More detail: [compose/README.md](compose/README.md).

## Running the end-to-end path as far as it works today

What runs on `main` (2026-10-04): the verifier plan against Inji Verify through the runner, the report and diff on
recorded fixtures, and the Inji Verify rig on a results file. The issuer path is on the branch
`wip/2026-10-04-stop` and has not run against a live stack yet.

1. One verifier module, end to end with no person in the loop (measured: exit 0, 23 s once the stack was up):

   ```bash
   bash scripts/dc.sh --profile tools build runner
   bash scripts/dc.sh --profile verify up -d --wait
   bash scripts/dc.sh run --rm runner inji-conformance run --component verify \
     --modules oid4vp-1final-verifier-happy-flow --no-gate --out /reports/try1
   bash scripts/dc.sh --profile '*' down -v
   ```

   Output lands in `$HARNESS_RUN_DIR/reports/try1/verify/` (`results.json`, `logs/`, `exports/`). The module
   currently ends FINISHED with result FAILED, for reasons listed under "Open problems" in
   [docs/STATUS.md](docs/STATUS.md). Leave out `--modules` for the whole plan (it can take over 20 minutes on a
   busy machine; `--timeout-minutes` sets the limit, default 30).

2. Report and diff, on the recorded fixtures:

   ```bash
   inji-conformance report --run runner/tests/report/fixtures/run-a --compare runner/tests/report/fixtures/run-b --out "$HARNESS_RUN_DIR/report-try"
   inji-conformance diff runner/tests/report/fixtures/run-a runner/tests/report/fixtures/run-b; echo "exit $?"   # 16: the runs differ
   ```

   Use the venv's `inji-conformance` (see [Build and test](#build-and-test)). Writes `summary.html`, `badge.svg`,
   `summary.md` and `diff.html`.

3. Inji Verify rig on a results file, after the Maven build above, from `testrigs/inji-verify-api-test`:

   ```bash
   java -Dmodules=injiverify -Denv.user=ps01 -Denv.endpoint=https://verify.inji.test:18451 \
        -Denv.testLevel=smokeAndRegression \
        -Dconformance.results.file=../../conformance/schema/examples/results-verify.example.json \
        -Dconformance.report.dir="$HARNESS_RUN_DIR/rig-try" \
        -cp target/apitest-injiverify-1.0.0-alpha.2-SNAPSHOT-jar-with-dependencies.jar \
        io.inji.testrig.apirig.injiverify.testrunner.ConformanceRigRunner
   echo "exit $?"    # 0; the report has rows TC_OIDF_VERIFY_01 to _11
   ```

   It takes 5-7 minutes, almost all of it the stock resource extraction from the jar.

## Conventions

- **Commit messages**: Conventional Commits (<https://www.conventionalcommits.org>), as in `git log`: `feat:`,
  `fix:`, `docs:`, `test:`, `chore:`, and `import:` for upstream code. One logical change per commit.
- **Sign-off**: every commit is signed off from your own GitHub account: `git commit -s` adds
  `Signed-off-by: Your Name <you@example.com>`. Forgot it on the last commit: `git commit --amend -s --no-edit`.
- **Pull requests**: small (one task card, or one clear part of one), from a branch named after the task, for
  example `feat/issuer-path`. A teammate reviews and approves before merge. Nobody pushes to `main` directly.
- **Lanes**: change only the folders your task card owns ([docs/STATUS.md](docs/STATUS.md#how-to-split-the-remaining-work)).
- **Upstream code** is imported unchanged in its own commit `import: upstream <repo>@<commit> (<licence>)`, with the
  upstream licence file, before any team change; the change follows in a separate commit, so `git log -p` shows
  the team's diff. Extract with `git -c core.autocrlf=false archive <commit> <path>` or `git cat-file blob`, never
  by copying working-tree files (Git for Windows rewrites line endings). Record provenance in the folder's README.
- **No secrets in git**: keys and passwords are made at run time in `$HARNESS_RUN_DIR`. Never commit `env.local`,
  `*.p12`, `*.jks`, `*.keystore`, suite configurations with keys, or raw suite exports (they contain the private
  keys of the suite configuration). Upstream test fixtures that carry such material are listed in
  `.gitguardian.yaml` with a reason. `bash scripts/check.sh secrets` must pass.
- **Licences**: OSI-approved licences only. Team code is MIT ([LICENSE](LICENSE)); imported code keeps its own
  (suite scripts MIT, Inji testrigs and configuration Apache-2.0). Check the licence before adding a dependency or
  an image.
- **Line endings**: LF everywhere (`.editorconfig`), checked by `bash scripts/check.sh eol`.
- **Runtime output** never goes into the repository; `git status --porcelain` must be empty after a run.
- **Docs claim only what was run**, with the date, the command and the result. Anything not run is written as a
  plan or left out.

## Picking up a task card

1. Open [docs/STATUS.md](docs/STATUS.md), pick a TODO or PARTIAL task whose "Depends on" tasks are DONE (or a part
   the card marks "can start now"), and tell the team in the team chat, so two people do not take the same lane.
2. Branch from the latest `main`:

   ```bash
   git switch main && git pull
   git switch -c feat/<short-task-name>
   ```

   For WP-08, take the unfinished files from `wip/2026-10-04-stop` as the card describes.
3. Read the card's goal, owned folders, acceptance check and notes, and the README of each folder you will touch.
4. Work in small commits (`git commit -s`), with unit tests next to the code. Run `bash scripts/check.sh all`
   before every push.
5. Run the card's acceptance check exactly as written. Paste the command, the date and the output into the pull
   request description.
6. In the same pull request: update the lane README and any doc your change affects, and update your task's row
   and card in [docs/STATUS.md](docs/STATUS.md) (status, commit ids, what was measured, what is left).
7. Push and open the pull request (`git push -u origin HEAD`, then the GitHub page or `gh pr create`). Ask a
   teammate for review; merge after approval.

If you do not have push access to the repository, ask the owner to add you as a collaborator, or fork it and open
the pull request from your fork.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Filename too long` during clone or checkout (Windows) | Long paths in the imported testrigs. Clone with `git -c core.longpaths=true clone ...` and run `git config core.longpaths true`. |
| `check.sh eol` fails on a file you wrote | The editor saved CRLF. Use an editor that honours `.editorconfig`, or convert the file to LF. |
| An imported upstream file no longer matches upstream | It was copied from a working tree that Git for Windows converted to CRLF. Re-extract with `git -c core.autocrlf=false archive` or `git cat-file blob`. |
| A check prints `SKIP ... not found` | The tool is missing. Install it or put it in `$HARNESS_TOOLS_DIR/bin`. With `CI=true` or `--strict` it is a FAIL. |
| `python3` opens the Microsoft Store or prints a hint (Windows) | The Store placeholder. Install Python from python.org and turn off the App execution aliases for `python.exe` and `python3.exe` in Windows settings. |
| `inji-conformance.exe`: "Permission denied" right after install (Windows with Smart App Control) | Reinstall the launcher: `"$HARNESS_RUN_DIR/venv/Scripts/python" -m pip install --force-reinstall --no-deps --editable ./runner`. This fixed it on 2026-10-04. |
| `VERIFY_DB_PASSWORD` error from `docker compose` | Compose was called directly. Use `bash scripts/dc.sh`. |
| A run uses an old stack, or `precheck FAIL containers of ps01-harness already exist` | A stack is still running. `bash scripts/dc.sh --profile '*' down -v`. |
| `ports FAIL in use on 127.0.0.1: ...` | Another program uses a harness port. Find it with `netstat -ano` (Windows) or `ss -ltnp` (Linux) and stop it. |
| `up --wait` fails because a one-shot container exited | Compose (5.5.1, measured) fails `--wait` when a one-shot container that nothing depends on has exited. That is why `pki-init` is only in the `verify`, `certify` and `tools` profiles and MinIO's bucket is created by a `post_start` hook; keep new one-shot steps the same way. |
| `localhost.emobix.co.uk` does not resolve | The name is public DNS for 127.0.0.1. Offline, add `127.0.0.1 localhost.emobix.co.uk` to the hosts file. |
| `verify.inji.test` or `certify.inji.test` does not resolve on the host | Expected: those names exist only inside the Compose network. Use the `probe` or `runner` container. |
| `suite-server` never healthy; its log says "A non-https request has been received" | Something called the server without `X-Forwarded-Proto: https`. Go through `https://localhost.emobix.co.uk:18443`. |
| Inji Certify not healthy within the start limit | It needs about 2 minutes on a loaded machine. Read `bash scripts/dc.sh --profile certify logs certify`; raise `SMOKE_START_TIMEOUT` if it is only slow. |
| Inji Certify fails to start or sign after `env.local` or one volume was deleted | Its keystore volume, its database volume and `env.local` belong together: `bash scripts/dc.sh --profile '*' down -v` and start again. |
| Inji Certify returns HTTP 200 but nothing happened | Its admin APIs report errors as HTTP 200 with an `errors` list in the body. Read the body. |
| `pull access denied` for `minio/minio` or `minio/mc` | Those images are no longer published; the defaults use the `pgsty` builds. |
| `inji-conformance run` exits 3 | The suite or the Inji component did not answer within 120 s, or a key from `pki-init` is missing. Start the stack with `up -d --wait` first. |
| `inji-conformance run` exits 4 | The whole run hit `--timeout-minutes` (default 30); `results.json` is still written. Free Docker resources or raise the limit. |
| Verifier modules fail at the wallet's response with HTTP 500 from Inji Verify | Known open problem: `compose/verify/init.sql` lacks the column `vp_submission.response_code`. See [docs/STATUS.md](docs/STATUS.md). |
| Changes to `conformance/plans/` have no effect in a run | The runner image copies `conformance/`. Rebuild it: `bash scripts/dc.sh --profile tools build runner`. |
| First Maven build of a testrig takes 8-15 minutes | Downloads, and the rig pom declares a snapshots repository that Maven probes for every artifact. Keep `~/.m2`; pass a mirror through `MAVEN_ARGS` if you have one. |
| A rig report lands in the wrong place or is missing (Windows) | TestNG's output folder is relative to the working directory: keep `conformance.report.dir` on the same drive as the working directory. |
| A rig report has no conformance rows | `EmailableReport` leaves out suites whose name contains "Master Suite"; the rows must be in the child suite. |
