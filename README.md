# Inji conformance harness

Automated OpenID conformance testing of [Inji Certify](https://github.com/inji/inji-certify) (credential issuer)
and [Inji Verify](https://github.com/inji/inji-verify) (verifier) against the
[OpenID Foundation conformance suite](https://gitlab.com/openid/conformance-suite).

MOSIP Decode 2026, problem statement 01, team Badmosip.

## Status

| Date | What works |
|---|---|
| 2026-10-04 | Repository layout and the repository checks (`scripts/check.sh`). Nothing else runs yet. |
| 2026-10-04 | Compose v1: the conformance suite (release-v5.3.1) and Inji Verify 1.0.x behind a TLS proxy, with keys made at run time. `bash compose/smoke.sh verify` passes; see [`compose/README.md`](compose/README.md). |
| 2026-10-04 | Compose v2: Inji Certify (commit `d6635da`) as its own authorization server behind the TLS proxy, issuing from pre-authorized offers, and MinIO with the `automationtests` bucket. `bash compose/smoke.sh certify reports` passes (metadata, offer, token, path-style S3 upload). |

This table lists only what has been run. The next section is the plan, not a result.

## What the harness will do

- Start one Docker Compose project with Inji Certify, Inji Verify, the conformance suite (server, MongoDB, nginx)
  and MinIO, with every host port in the range 18000-18999.
- Run the suite's OpenID4VCI 1.0 issuer test plan against Inji Certify and its OpenID4VP 1.0 verifier test plan
  against Inji Verify, through a Python runner built on the suite's own `run-test-plan.py`.
  - The runner creates, configures, starts, polls and exports each plan.
  - It also performs every step that normally needs a person in the suite's web page, for example asking Inji
    Verify for an authorization request and handing it to the suite's wallet.
- Add an `OpenIDConformanceTest` TestNG class to the Inji Certify and Inji Verify api-testrigs: one TestNG result
  per conformance test module in the testrig report, the report uploaded to S3 (MinIO locally), and a gate that
  fails on any result not listed in a benchmark of expected failures with written reasons.
- Provide `run-conformance.sh --component certify|verify|--combined` and `run-full-stack-conformance.sh`, an HTML
  summary with links to the suite logs, a badge, a diff between two runs, and a GitHub Actions workflow.

## Quick start

Not available yet. The goal is one command from a clean clone to a report: `./run-full-stack-conformance.sh`.

## Repository checks

```bash
bash scripts/check.sh all          # or one or more of: eol secrets shell runner testrigs workflows docs
```

Each check prints one line: `PASS`, `FAIL` or `SKIP`, its name and a reason. The exit status is 1 when any check
failed. Output on 2026-10-04 (Windows 11, Git Bash, shellcheck 0.11.0):

```text
PASS  eol        17 text files use LF (0 byte-identical upstream CRLF files exempted)
PASS  secrets    17 text files scanned, no findings (0 files skipped as fixtures listed in .gitguardian.yaml)
PASS  shell      3 scripts clean under shellcheck 0.11.0, 1 shell test scripts passed
SKIP  runner     no runner/pyproject.toml
SKIP  testrigs   no testrigs/pom.xml
SKIP  workflows  no workflow files
SKIP  docs       no docs/tools/check_docs.py
checks: 3 passed, 0 failed, 4 skipped
```

| Check | What it does | Needs |
|---|---|---|
| `eol` | Team files use LF line endings. Upstream files stored with CRLF upstream pass only while byte-identical to the blob listed in `scripts/eol-exempt.txt`. | git |
| `secrets` | No private keys, access tokens or credential assignments in files git would commit. Upstream test fixtures listed in `.gitguardian.yaml` are skipped. Findings name the file and line, never the value. | git |
| `shell` | shellcheck on every `*.sh` file, then the tests in `scripts/tests/`. | shellcheck |
| `runner` | ruff, pytest and schema-example validation of the Python runner, in a virtual environment under `$HARNESS_RUN_DIR/venv`. | Python 3.12+ |
| `testrigs` | Maven `verify` of the testrig bridge library. | Maven 3.9, JDK 21 |
| `workflows` | actionlint on the GitHub Actions workflows. | actionlint |
| `docs` | Runs `docs/tools/check_docs.py`. | Python 3.12+ |

- A check whose files do not exist yet prints `SKIP`.
- A check whose tool is missing prints `SKIP` with the reason; with `--strict`, `CI=true` (set by GitHub Actions)
  or `HARNESS_CHECK_STRICT=1` it prints `FAIL` instead, so CI never passes by skipping.
- Scripts need bash 4.4 or newer (Linux, Git Bash on Windows, or bash from Homebrew on macOS).

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `HARNESS_RUN_DIR` | `<repo>/run` (ignored by git) | Runtime state: downloads, logs, generated keys, the Python virtual environment. |
| `HARNESS_COMPOSE_PROJECT` | `ps01-harness` | Docker Compose project name. |
| `HARNESS_TOOLS_DIR` | `$HARNESS_RUN_DIR/tools` | Extra tool folder: `<dir>/bin` is searched after `PATH` for shellcheck, actionlint and Maven. |
| `HARNESS_CHECK_STRICT` | `0` | `1` makes a missing tool a check failure. |

## Repository layout

| Path | Contents | Lane |
|---|---|---|
| [`compose/`](compose/README.md) | Docker Compose assets: suite, Inji Certify, Inji Verify, TLS proxy, run-time key generation, MinIO | platform |
| [`runner/`](runner/README.md) | Python package `inji_conformance` and its command `inji-conformance` | runner |
| [`conformance/`](conformance/README.md) | Test plan templates, benchmark of expected failures, JSON Schemas | runner |
| [`third_party/`](third_party/README.md) | Upstream code imported unchanged: the conformance suite's Python scripts | runner |
| [`testrigs/`](testrigs/README.md) | Inji api-testrigs and the TestNG bridge library | testrig |
| [`docs/`](docs/README.md) | Documentation | delivery |
| [`demo/`](demo/README.md) | Demo script and demo-only configuration | delivery |
| `scripts/` | `check.sh`, shared shell library `lib/common.sh`, tests in `tests/` | platform |
| `.gitguardian.yaml` | Upstream test fixtures with key or credential material, skipped by secret scanners | platform |

A lane is one of the team's four work streams; each path has one owning lane, so parallel work does not collide.
platform: Compose, scripts, CI, root configuration. runner: the Python runner, plans, benchmark, vendored suite
scripts. testrig: the Java testrigs. delivery: documentation, report, demo.

## Rules for contributors

- Upstream code is imported unchanged in its own commit, `import: upstream <repo>@<commit> (<licence>)`, before
  any team change to it, so the team's changes stay visible as their own diff.
- Files use LF line endings (`.editorconfig`); `bash scripts/check.sh eol` enforces it.
- No keys or passwords in git. The harness generates its keys and passwords at run time in `$HARNESS_RUN_DIR`.
  Upstream test fixtures that carry such material are listed in `.gitguardian.yaml` with the reason.
- Runtime output never goes into the repository; `/run/` is ignored.
- Docs state only what was run, with the date.

## Licence

Team code is under the MIT licence ([LICENSE](LICENSE)). Imported upstream code keeps its own licence and licence
files: the conformance suite's scripts (MIT) in `third_party/`, the Inji api-testrigs and Inji Certify
configuration (Apache-2.0) in `testrigs/` and `compose/`.
