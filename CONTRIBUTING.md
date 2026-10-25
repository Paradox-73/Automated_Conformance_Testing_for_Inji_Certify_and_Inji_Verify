# Contributing

How to set up a computer to work on the harness, test a change, and get it merged. Running the harness as a user:
[docs/README.md](docs/README.md). Tools and versions: [docs/README.md](docs/README.md#1-prerequisites). Settings,
ports and images: [docs/configuration.md](docs/configuration.md). Problems: [docs/troubleshooting.md](docs/troubleshooting.md).

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

   Expected: `PASS` for all seven checks when shellcheck, actionlint, JDK 21 and Maven are installed. Without one
   of those tools, its check prints `SKIP` with the reason (`FAIL` with `--strict`). Tools that are not on `PATH`
   can go in `$HARNESS_TOOLS_DIR/bin` (default `$HARNESS_RUN_DIR/tools/bin`).

5. Pull the images and build the runner and testrig images once: `./run-full-stack-conformance.sh --prepare-only`.

## Build and test

| Command | What it checks | Needs |
|---|---|---|
| `bash scripts/check.sh all` | every check below that has inputs | see each line |
| `bash scripts/check.sh eol secrets` | LF line endings; no keys or passwords in files git would commit | git |
| `bash scripts/check.sh shell` | shellcheck on every script, then `scripts/tests/test-*.sh` | shellcheck |
| `bash scripts/check.sh runner` | ruff, pytest (`runner/tests`), validation of `conformance/schema/examples/*.json` | Python 3.12 |
| `bash scripts/check.sh testrigs` | `mvn verify` of the bridge library `testrigs/apitest-commons-conformance` | JDK 21, Maven 3.9 |
| `bash scripts/check.sh workflows docs` | actionlint on `.github/`; `docs/tools/check_docs.py` and its tests | actionlint, Python 3.12 |
| `bash third_party/reimport.sh check` | the vendored suite scripts still match their import | bash |

The runner's virtual environment can also be used directly:

```bash
"$HARNESS_RUN_DIR/venv/Scripts/python" -m pytest -q runner/tests     # Linux and macOS: venv/bin/python
"$HARNESS_RUN_DIR/venv/Scripts/inji-conformance" --help              # Linux and macOS: venv/bin/inji-conformance
```

## The local stack

Always call Compose through `scripts/dc.sh`. It adds the project name, the root `docker-compose.yml`, the
generated `env.local`, and on Windows turns off Git Bash path rewriting. A plain `docker compose` fails with a
missing `VERIFY_DB_PASSWORD`. Profiles and services: [compose/README.md](compose/README.md#profiles-and-services).

```bash
bash scripts/dc.sh --profile verify up -d --wait                 # suite + Inji Verify + TLS proxy
bash scripts/dc.sh --profile certify --profile reports up -d --wait   # suite + Inji Certify + TLS proxy + MinIO
bash scripts/dc.sh --profile '*' down -v                          # stop everything and delete the volumes
bash compose/smoke.sh verify                                      # start, check, measure, remove
```

Always stop with `--profile '*'`: a plain `down` leaves profiled services running.

Pieces on their own, for development:

- The runner alone against a running stack:
  `bash scripts/dc.sh --profile verify up -d --wait`, then
  `bash scripts/dc.sh run --rm runner inji-conformance run --component verify --modules oid4vp-1final-verifier-happy-flow --out /reports/try1`,
  then `bash scripts/dc.sh --profile '*' down -v`. Rebuild the runner image after changing `runner/` or
  `conformance/`: `bash scripts/dc.sh --profile tools build runner`.
- Re-gate a recorded run without a stack: `"$HARNESS_RUN_DIR/venv/bin/inji-conformance" gate --run <run>/<component>` (Windows: `venv/Scripts/inji-conformance`).
- Report and diff on the recorded fixtures: `inji-conformance report --run runner/tests/report/fixtures/run-a --out "$HARNESS_RUN_DIR/report-try"`
  and `inji-conformance diff runner/tests/report/fixtures/run-a runner/tests/report/fixtures/run-b` (exit 16: they differ).
- A testrig on a results file: `bash testrigs/run-testrig.sh verify --results <run>/verify/results.json` (needs
  `bash testrigs/build.sh --image` once and a running stack network).

## Conventions

- **Commit messages**: Conventional Commits (<https://www.conventionalcommits.org>), as in `git log`: `feat:`,
  `fix:`, `docs:`, `test:`, `chore:`, and `import:` for upstream code. One logical change per commit.
- **Sign-off**: every commit is signed off from your own GitHub account: `git commit -s` adds
  `Signed-off-by: Your Name <you@example.com>`. Forgot it on the last commit: `git commit --amend -s --no-edit`.
- **Pull requests**: small, from a branch named after the change, for example `feat/issuer-path`. Run
  `bash scripts/check.sh all` before every push, paste the command, date and output of any live run into the pull
  request description, and update the docs that describe the changed parts in the same pull request. A teammate
  reviews and approves before merge. Nobody pushes to `main` directly.
- **Upstream code** is imported unchanged in its own commit `import: upstream <repo>@<commit> (<licence>)`, with the
  upstream licence file, before any team change; the change follows in a separate commit, so `git log -p` shows
  the team's diff. Extract with `git -c core.autocrlf=false archive <commit> <path>` or `git cat-file blob`, never
  by copying working-tree files (Git for Windows rewrites line endings). Record provenance in the folder's README.
- **No secrets in git**: keys and passwords are made at run time in `$HARNESS_RUN_DIR`. Never commit `env.local`,
  `*.p12`, `*.jks`, `*.keystore`, suite configurations with keys, or raw suite exports (they contain the private
  keys of the suite configuration). Upstream test fixtures that carry such material are listed in
  `.gitguardian.yaml` with a reason. `bash scripts/check.sh secrets` must pass.
- **Licences**: OSI-approved licences only. Team code is MPL-2.0 ([LICENSE](LICENSE)); new team source files start
  with `SPDX-License-Identifier: MPL-2.0`; imported code keeps its own
  (suite scripts MIT, Inji testrigs and configuration Apache-2.0). Check the licence before adding a dependency or
  an image.
- **Line endings**: LF everywhere (`.editorconfig`), checked by `bash scripts/check.sh eol`.
- **Runtime output** never goes into the repository; `git status --porcelain` must be empty after a run.
- **Docs claim only what was run**, with the date, the command and the result. Anything not run is written as a
  plan or left out. Measured results live in [docs/test-report.md](docs/test-report.md); other documents link to
  it instead of repeating the numbers.

If you do not have push access to the repository, ask the owner to add you as a collaborator, or fork it and open
the pull request from your fork.
