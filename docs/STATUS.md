# Project status

Status of the harness on **2026-10-14**, branch `nikunj/ps01-finish` (from `main` `ae2de5a`). Deadline:
**2026-10-26 23:59 IST**.

| Item | Value |
|---|---|
| Repository | <https://github.com/Paradox-73/Automated_Conformance_Testing_for_Inji_Certify_and_Inji_Verify> |
| `main` | `ae2de5a`: WP-01 to WP-07, WP-11, WP-13, WP-08's code, the two platform fixes |
| This branch | WP-08 to WP-18 finished as far as one machine allows; open items below |
| Open | the first hosted GitHub Actions run (refused by GitHub for the owner account's billing), the video and slides (team) |

How to work on a task: [CONTRIBUTING.md](../CONTRIBUTING.md). The words used below:

- **Suite**: the OpenID Foundation conformance suite (Java server, MongoDB, nginx). It plays the wallet against
  both Inji components.
- **Plan, module, variant**: a plan is a named list of tests; a module is one test; variants select the protocol
  flavour (for example `sender_constrain=dpop`).
- **WAITING, handoff, responder**: a module is WAITING when the suite waits for the system under test (an offer, an
  authorization request, a screenshot). A handoff is what lets it continue. The handoff responder is the runner's
  thread that does every handoff without a person.
- **Benchmark**: the list of expected failures and skips, each with a written reason. The gate fails on anything
  not on the list.
- **Lane**: one of four work streams (platform, runner, testrig, delivery). Every folder has one owning lane, so
  two people never edit the same files. Table in [How to split the remaining work](#how-to-split-the-remaining-work).
- **`DC`** in older notes means `bash scripts/dc.sh`, the only way to call Docker Compose here.

## All tasks

DONE means the task's acceptance check was run and passed on the date in its commits. PARTIAL means work exists
but part of the acceptance check could not be run.

| Id | Lane | Title | Depends on | Status | Commits |
|---|---|---|---|---|---|
| WP-01 | platform | Scaffold: layout, lane READMEs, `scripts/check.sh` | - | DONE | `9a4fee1`, `f999769` |
| WP-02 | runner | Import the suite's automation scripts unchanged (release-v5.3.1, MIT) | WP-01 | DONE | `1f7018a`, `8f11a33` |
| WP-03 | testrig | Import the Inji Certify and Inji Verify api-test trees unchanged (Apache-2.0) | WP-01 | DONE | `9d07328`, `f307a88`, `fcecc46` |
| WP-04 | runner | Results and benchmark contract (JSON Schemas, examples, `inji_conformance.model`, CLI skeleton) | WP-01 | DONE | `eb60413`, `a4f601a` |
| WP-05 | platform | Compose v1: suite, Inji Verify, TLS proxy, run-time keys | WP-01 | DONE | `eaac172`, `7d931ba`, `478b318`, `2694161` |
| WP-06 | runner | Walking skeleton: `inji-conformance run --component verify` with the handoff responder | WP-02, WP-04, WP-05 | DONE | `be987eb`, `f1f83e1`, `a707012`, `345ab93` (compose build change inside `7eb88b4`) |
| WP-07 | platform | Compose v2: Inji Certify and MinIO | WP-05 | DONE | `bcd8521`, `7eb88b4`, `2dd30a8` |
| WP-08 | runner | Issuer path: Certify seeding and credential offer handoff | WP-06, WP-07 | DONE | `158e917`, `177474c`; live: `a63ac08`, `cf813fa` |
| WP-09 | runner | Results parser, benchmark gate, checked REVIEW evidence | WP-06, WP-08 | DONE | `cf813fa`, `e2a5bfe`, `ebd137e`, `bc79037` |
| WP-10 | platform | One-command scripts `run-conformance.sh` and `run-full-stack-conformance.sh` | WP-09, WP-13 | DONE | `3ae4510`, `9fd4fcb` |
| WP-11 | testrig | TestNG bridge library and the Inji Verify rig integration | WP-03, WP-04 | DONE | `511baf9` |
| WP-12 | testrig | Inji Certify rig integration, MinIO upload, testrig image | WP-09, WP-11 | DONE | `1ff1a86`, `e0aba8c` |
| WP-13 | delivery | Consolidated HTML report, badge and run diff | WP-04 | DONE | `faad42c`, `fb772ae` |
| WP-14 | runner | Parallel execution and HAIP readiness track | WP-10 | DONE | `ebd137e`, `3ae4510` |
| WP-15 | platform | GitHub Actions workflow `full-stack-conformance.yml` | WP-10, WP-12, WP-13 | PARTIAL | `b50de8b`; the hosted run is open |
| WP-16 | delivery | Documentation set | WP-10, WP-11 | DONE | `cc5a25e`, `058a51f` |
| WP-17 | delivery | Test report, test data and Inji findings | WP-09, WP-12, WP-14, WP-16 | DONE | `cc5a25e`, `058a51f`, `50d1836`; build comparison dropped |
| WP-18 | delivery | Demo script, video and deck material, final README | WP-13, WP-15, WP-16, WP-17 | DONE | `f05b4d0`, `058a51f`; video and slides by the team |

Also on this branch: `ae5dc91` (the scripts and their tests on macOS), `861a04b` and `f05b4d0` (secrets and eol
fixes found by the checks).

### What the tasks proved (2026-10-14)

Every run with its run id, duration and evidence is in [test-report.md](test-report.md). In short:

- Inji Verify: 11 of 11 modules of the verifier plan conform with the default configuration (7 REVIEW with an image
  of Inji Verify's verdict uploaded, 4 PASSED). The x509_san_dns configuration: 10 known gaps, 1 not applicable.
- Inji Certify: all 15 modules of the issuer plan complete; 3 PASSED, 9 known gaps, 3 not applicable; `dpop` and
  `mtls` reach the same conditions.
- One command for each component and both, parallel and serial, with the same verdicts on reruns; the full stack
  with both testrigs and the MinIO upload in 250 s, peak memory 1619 MiB.
- Robustness cases R1 to R6 as planned in the WP-17 card ([test-cases.md](test-cases.md)).
- Ten Inji gaps written up as issue drafts ([findings/README.md](findings/README.md)); HAIP gaps ranked
  ([certification-readiness.md](certification-readiness.md)).

## Done notes

### WP-08 Issuer path

- First live run (2026-10-14) stopped every flow module at `CheckServerConfiguration`: Inji Certify's OAuth metadata
  has no `authorization_endpoint`. The TLS proxy now adds a placeholder by default (`CERTIFY_AS_METADATA`), marked
  in `results.json`; `as-is` reproduces the finding.
- `run-test-plan.py` stops a plan after three modules in a row that did not reach FINISHED; Inji Certify's failures
  interrupt modules, so the runner raises the limit and judges INTERRUPTED-with-FAILED modules on their conditions.
- Seeding: `created`, then `already present`. Every module that exposed `credential_offer_endpoint` got an offer
  (HTTP 200) and a transaction code. Gate variant: `dpop` ([conformance/README.md](../conformance/README.md)).

### WP-09 Results, benchmark gate, REVIEW evidence

- `inji_conformance.benchmark`: verdict table, gate, JUnit XML, `inji-conformance gate`; `run-test-plan.py` gets the
  same benchmark files and the two gates are cross-checked (no disagreement in any run).
- REVIEW evidence: the responder uploads an image of Inji Verify's verdict (`GET /vp-result`) into the suite's
  placeholder; the temporary scripted-browser block is gone. The default verifier configuration is now
  `redirect_uri`; x509_san_dns is an alternative template.
- HTML export downloaded and linked per module. Benchmarks: Certify 13 failures and 3 skips, Verify 20 failures
  and 1 skip (x509_san_dns only). With one entry removed, `gate` exits 1 naming module and condition.

### WP-10 One-command scripts

- `run-conformance.sh`, `run-full-stack-conformance.sh`, `scripts/lib/stack.sh`, `HARNESS_COMPOSE_FILES` in
  `scripts/dc.sh`; preflight (Docker, Compose, existing stack, ports with their service, memory); manifest with
  image digests and wall times; teardown in a trap. Every acceptance command exited 0; no container left.

### WP-12 Certify rig, MinIO upload, testrig image

- Certify rig integration, `testrigs/build.sh`, `testrigs/Dockerfile`, `testrigs/run-testrig.sh`,
  `testrigs/upstream-patches/`. The S3 upload never worked before: apitest-commons ignores environment variables
  for keys its property files lack; `RigRun.applyUploadSettings` fixes it. Both rigs exit 0 in invoke mode and their
  reports are listed in MinIO.

### WP-14 Parallel execution and HAIP readiness

- `--combined` parallel and `--serial`; diff of the two exits 0. HAIP templates for both components; results carry
  `gating: false`. Left for later: a client attestation key and trust anchors in the Certify HAIP template, so the
  plan reaches Certify's endpoints in every module ([certification-readiness.md](certification-readiness.md)).

### WP-15 GitHub Actions

- Workflow, example caller and `scripts/ci-local.sh` written; actionlint clean; `bash scripts/ci-local.sh verify`
  result in [test-report.md](test-report.md).
- What remains: the first hosted run. GitHub refused run 38476075682 before any job started because of the
  repository owner's billing. After the billing is fixed (or the repository is public), push once and put the run
  URL in [test-report.md](test-report.md) and [ci.md](ci.md); set WP-15 to DONE if it is green.

### WP-16 Documentation

- The documents listed in [README.md](README.md); `docs/tools/check_docs.py` (markdownlint subset, links and
  anchors, dated command blocks `<!-- run YYYY-MM-DD -->`, evidence, finding headings, benchmark issue paths) with
  its own tests. This file, `CONTRIBUTING.md` and the lane READMEs hold commands for work in progress and are not
  held to the dated-block rule.

### WP-17 Test report, data, findings

- [test-report.md](test-report.md), [test-cases.md](test-cases.md), [test-data.md](test-data.md),
  [findings/](findings/README.md), [certification-readiness.md](certification-readiness.md), `docs/evidence/`,
  `demo/regression.compose.yml`. Dropped: the build comparison with `inji-certify-with-plugins:1.0.0-alpha.1`
  (optional; the command is in the test report).

### WP-18 Demo and final README

- `demo/demo.sh` (`--regression` exits 0 after the gate failed as intended), video storyboard, deck outline, final
  README with the recorded badge, [submission-checklist.md](submission-checklist.md). The fresh-clone check is in
  [test-report.md](test-report.md). Video and slides: the team.

### Open problems found by the tasks

| Lane | Problem | State |
|---|---|---|
| platform | Inji Verify's `vp_submission` response code columns; `dc.sh down` without profiles | fixed on `main` (2026-10-07) |
| runner, delivery | Inji Verify's bundled request signing keystore is self-signed | the harness gives Verify a CA-issued key; finding written |
| runner | Full verifier plan hit 20 minutes on a busy VM | a full plan now takes under 2 minutes; the limit stays 30 |
| runner | Did the verifier plan have 11 modules? | yes: 11 created for both configurations (2026-10-14) |

## How to split the remaining work

| Lane | Owns (only this lane edits these) | Remaining tasks, in order | Can start today |
|---|---|---|---|
| platform | `docker-compose.yml`, `compose/`, `scripts/`, root scripts, `.github/`, `.gitignore`, `.gitattributes`, `.gitguardian.yaml`, `.editorconfig` | open problems (Verify `init.sql`, `dc.sh down`), WP-10, WP-15 | yes: the two open problems, then the WP-10 skeleton and preflight |
| runner | `runner/` except `runner/src/inji_conformance/report/` and `runner/tests/report/`; `conformance/`; `third_party/` | WP-08, WP-09, WP-14 | yes: finish WP-08 from the branch |
| testrig | `testrigs/` | WP-12 | yes: Certify rig in consume mode, `build.sh`, `Dockerfile` |
| delivery | `docs/`, `demo/`, `README.md`, `CONTRIBUTING.md`, `runner/src/inji_conformance/report/`, `runner/tests/report/` | WP-16, WP-17, WP-18 | yes: `docs/tools/check_docs.py` and docs of finished parts |

- One person per lane at a time. With two people: one takes runner (the longest chain), the other takes platform
  and testrig, which share no folder; delivery goes to whoever is free first.
- Fixed seams, so no lane edits another lane's file: `runner/src/inji_conformance/cli.py` (runner) already
  registers `report` and `diff`, which live in the report package (delivery); `runner/pyproject.toml` (runner)
  declares the report's dependencies; `bash scripts/check.sh docs` (platform) runs `docs/tools/check_docs.py`
  (delivery); `run-conformance.sh` (platform) passes runner flags through unchanged.
- If a task truly needs a change in another lane's folder, ask that lane's owner to make it in their own pull
  request.
- This file belongs to delivery for its structure, but every pull request that finishes or advances a task edits
  that task's row and card here. Edit only your own task's row to avoid merge conflicts.

## Definition of done

A task is DONE only when all of these hold, in one pull request:

1. The tests pass: `bash scripts/check.sh all` prints no FAIL (and the lane's own test command, for example `mvn`
   for testrigs).
2. The task's acceptance check above was run on the date written in the pull request, with its output pasted into
   the pull request description.
3. The docs that describe the changed parts are updated (the lane README, and `docs/` once WP-16 exists). They
   state only what was run, with the date.
4. This file is updated in the same pull request: status set to DONE with the commit ids, the card replaced by
   "done" notes (what was measured, what is left for later tasks).
5. A teammate reviewed and approved the pull request.
6. `git status --porcelain` is empty after the run: no runtime output was written into the repository.
