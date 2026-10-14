# Test report

What was run, when, on which commit and with what result. Every run id below has its evidence (manifest, results,
report, badge) in `docs/evidence/<date>-<run id>/`; dates in run ids and folder names are UTC, the runs took place on
2026-10-14 IST. Test case definitions: [test-cases.md](test-cases.md).

## Machines

- macOS 15.6.1 (Apple silicon), Docker Desktop (Engine 28.3.0, Compose 2.38.1) with a 4 GiB VM, GNU bash 5.3.20,
  Python 3.12.15, Maven 3.9.11 on JDK 25 (host build of the testrigs), shellcheck 0.11.0, actionlint 1.7.12. Runs
  dated 2026-10-13 in their run ids.
- Windows 11 (10.0.26200), Git Bash (GNU bash 5.3.15), Docker Desktop 29.7.2 (Compose 5.5.1, 7792 MiB and 12 CPUs
  for Docker, shared with another team's Inji stack), Python 3.12.10, Temurin 21.0.12 and Maven 3.9.9 for
  `scripts/check.sh` only, shellcheck 0.11.0, actionlint 1.7.12. Runs dated 2026-10-14 in their run ids.
- GitHub's hosted `ubuntu-24.04` runner (4 vCPU, 16 GB, 86 GB of free disk) for the workflow runs.

Images as pinned in `docker-compose.yml` at the time of each run; each manifest lists every image and digest. Until
2026-10-14 the Inji Certify default was `develop@sha256:b5022884...` (commit `d6635da`); since then it is
`1.0.x@sha256:2c72a78c...` (commit `bbd913e`, see [Build comparison](#build-comparison)). Inji Verify is
`1.0.x@sha256:a9b81fd4...`, the suite release-v5.3.1.

## Unit and component tests

| Suite | Language | Tests | Result (2026-10-14) |
|---|---|---|---|
| `runner/tests` (pytest) | Python | 462 | all passed |
| `compose/pki/test_generate.py` (unittest) | Python | 19 | all passed |
| `docs/tools/test_check_docs.py` (unittest) | Python | 11 | all passed |
| `testrigs/apitest-commons-conformance` (JUnit 5, `mvn verify`) | Java | 52 | 0 failures, 0 errors |
| `scripts/tests/test-*.sh` (TAP) | bash | 88 cases in 5 scripts, plus the PKI script | all ok |

`bash scripts/check.sh all` result: see [Repository checks and local CI](#repository-checks-and-local-ci).

## End-to-end runs

Duration is the whole command (stack start, plans, report, teardown). Peak memory of the stack, measured with
`bash compose/smoke.sh certify verify reports` (docker stats every 3 s, 2026-10-14): 1619 MiB in total (Inji Certify
567, suite server 463, Inji Verify 278, MongoDB 114, MinIO 110, the rest under 50 MiB), healthy 65 s after `up`;
the runner and testrig containers come on top.

| Test case | Command | Run id | Duration | Exit | Gate |
|---|---|---|---|---|---|
| TC-01 | `./run-conformance.sh --component verify --runner-only` | `20261013T211945Z-82f205` | 80 s | 0 | 11 conforms |
| TC-02 | `./run-conformance.sh --component certify --runner-only` | `20261013T212108Z-6bdc7f` | 89 s | 0 | 0 regressions, 9 known gaps, 0 stale, 3 not applicable |
| TC-03 | `./run-full-stack-conformance.sh --no-prepare --runner-only` (twice) | `20261013T212258Z-3eb7f6`, `20261013T212759Z-0a2ad5` | 285 s, 443 s | 0, 0 | both components as above |
| TC-04 (R1) | `inji-conformance diff` of the two TC-03 runs | | | 0 | 26 modules unchanged |
| TC-05 (R5) | `./run-conformance.sh --combined --runner-only --serial`, then `diff` against TC-19 | `20261013T223353Z-14700b` | 166 s | 0; diff 0 | same verdicts as parallel |
| TC-06 (R2) | Inji Verify stopped after the first handoff, `--timeout-minutes 5` | `20261013T221457Z-54242c` | 341 s | 4 | 11 regressions ("handoff not delivered", "never started"); no container left |
| TC-07 (R3) | suite server restarted during the issuer plan | `20261013T222050Z-26ba8a` | 108 s | 0 | same as TC-02; 13 failed responder polls in `notes` |
| TC-08 (R4) | `HARNESS_COMPOSE_FILES=demo/regression.compose.yml`, Certify | `20261013T221238Z-b9fc52` | 83 s | 1 | 3 regressions, named with their conditions |
| TC-09 (R6) | port 18451 held by another program | (stops in preflight, no run) | - | 3 | "ports in use on 127.0.0.1: 18451 (Inji Verify over TLS (tls-proxy))" |
| TC-13 | `CERTIFY_AS_METADATA=as-is`, Certify, `--no-gate` | `20261013T222630Z-e4420c` | 51 s | 0 | 13 of 15 modules stop at `CheckServerConfiguration` |
| TC-14 | verifier x509_san_dns template | `20261013T222732Z-0cc34f` | 86 s | 0 | 0 regressions, 10 known gaps, 0 stale, 1 not applicable |
| TC-15 | `--combined --runner-only --track haip` | `20261013T222452Z-1865df` | 86 s | 0 | not gating; 63 + 11 modules, all regressions ([readiness](certification-readiness.md)) |
| TC-19 | `./run-full-stack-conformance.sh --no-prepare` from a fresh clone, Windows 11 (with testrigs and MinIO) | `20261014T133851Z-c99cce` | 728 s | 0 | both gates passed; rig reports `T-15_P-3_S-0_F-0_I-3_KI-9` and `T-11_P-11_S-0_F-0_I-0_KI-0` uploaded to `automationtests/injicertify/` and `automationtests/injiverify/` ([timings](evidence/2026-10-14-20261014T133851Z-c99cce/fresh-clone.txt)) |
| TC-19 (final) | `./run-full-stack-conformance.sh` (prepare with the images present, then the run) at `073479b` with the `1.0.x` Certify image, Windows 11 with the Docker VM idle | `20261014T141827Z-5e24aa` | 392 s | 0 | the same verdicts and rig reports ([evidence](evidence/2026-10-14-20261014T141827Z-5e24aa/)) |
| TC-19 (macOS) | the same in the working clone | `20261013T222910Z-f08c5b` | not recorded | 0 | both gates passed; rig reports `T-15_P-3_S-0_F-0_I-3_KI-9` and `T-11_P-11_S-0_F-0_I-0_KI-0` uploaded to `automationtests/injicertify/` and `automationtests/injiverify/` |
| TC-20 | `bash demo/demo.sh --regression --runner-only` | `20261013T223652Z-34a7ff` (before), `20261013T223845Z-e3ac63` (regression) | 99 s + 97 s | 0 | before 0, regression 1, diff 16 with 3 changed modules, "demo ok" |

Parallel against serial: on this 4 GiB VM the parallel runner-only runs (TC-03) took longer than the serial one
(TC-05), because both plans and both Inji components compete for two cores and 4 GiB; the plans themselves ran
114 s and 130 s side by side. The CI runners and machines with more memory are expected to gain from `--combined`;
that has not been measured yet.

The issuer plan with `sender_constrain=mtls` (TC-12) reached the same conditions as `dpop`; both stop at the
credential endpoint before any sender-constraint check, so the gate keeps `dpop` (`conformance/README.md`).

## Testrigs

| Test case | Command | Exit | Report |
|---|---|---|---|
| TC-16 | `bash testrigs/run-testrig.sh certify --invoke` | 0 | `mosip-ps01-injicertify-conformance-2026-10-13_21-54-full-report_T-15_P-3_S-0_F-0_I-3_KI-9.html`, listed in MinIO `automationtests/injicertify/` |
| TC-17 | `bash testrigs/run-testrig.sh verify --invoke` | 0 | `mosip-ps01-injiverify-conformance-2026-10-13_21-57-full-report_T-11_P-11_S-0_F-0_I-0_KI-0.html`, listed in MinIO `automationtests/injiverify/` |
| TC-16, TC-17 (rerun) | the same two commands on the Windows machine, 2026-10-14, after invoke mode began passing `--target {target}` (`env.endpoint`) and the rig began running as the compose services' user | 0, 0 | `..._T-15_P-3_S-0_F-0_I-3_KI-9.html` and `..._T-11_P-11_S-0_F-0_I-0_KI-0.html`, both in MinIO; runner targets `https://certify.inji.test:18450` and `https://verify.inji.test:18451/v1/verify` ([evidence](evidence/2026-10-14-testrig-invoke/)). The first attempt, before the user fix, failed in both rigs with `Permission denied: /pki/suite-signing.jwk.json` |
| TC-18 | `git apply --check --directory=api-test` of `testrigs/upstream-patches/` on inji-certify `203b143` and inji-verify `6a6ab3b` | 0 | all three patches apply |

The rig reports of TC-19 are in [evidence](evidence/2026-10-14-20261014T133851Z-c99cce/testrig/).

## Build comparison

The issuer plan against three Inji Certify images, Windows machine, 2026-10-14, each with
`CERTIFY_IMAGE=<image> ./run-conformance.sh --component certify --runner-only`, compared with `inji-conformance diff`
against the certify results of the fresh-clone run `20261014T133851Z-c99cce` (develop image):

| Image | Commit (label) | Run id | Exit | Gate | Difference from develop |
|---|---|---|---|---|---|
| `injistackqa/inji-certify-with-plugins:develop@sha256:b5022884...` | `d6635da`, 2026-09-09 | `20261014T133851Z-c99cce` | 0 | 0 regressions, 9 known gaps, 3 not applicable | (reference) |
| `injistackqa/inji-certify-with-plugins:1.0.x@sha256:2c72a78c...` | `bbd913e` on `release-1.0.x`, 2026-10-09 | `20261014T140148Z-9643eb` | 0 | 0 regressions, 9 known gaps, 3 not applicable | none: 15 modules unchanged |
| `injistack/inji-certify-with-plugins:1.0.0-alpha.1@sha256:1579b244...` | `8fdf716`, 2026-07-30 (the only 1.0 release image) | `20261014T135637Z-9de2b7` | 1 | 1 regression, 8 known gaps, 3 not applicable | `fail-unknown-credential-identifier`: the credential endpoint answers an unknown credential identifier with a status other than 400 (`EnsureHttpStatusCodeIs400`) and the error code `unknown_error` instead of `invalid_request` |

The first attempt of the `1.0.x` run stopped before the plan with exit 3: the suite's MongoDB container did not
become healthy while the other stack used the machine's CPUs. The rerun above passed. Exit 3 is the code for that
case, so it did not read as a regression.

Since 2026-10-14 the default image is `1.0.x`: the QA build of the `release-1.0.x` branch, which contains `d6635da`
and gives the same verdicts. No Inji Certify 1.0 release image with DPoP support exists yet; `1.0.0-alpha.1` has no
DPoP code, and its one difference above is a credential-endpoint error status. Evidence:
[1.0.x](evidence/2026-10-14-20261014T140148Z-9643eb/), [1.0.0-alpha.1](evidence/2026-10-14-20261014T135637Z-9de2b7/).

## Repository checks and local CI

`bash scripts/check.sh --strict all` on the Windows machine, 2026-10-14, 326 s, exit 0:

```text
PASS  eol        1166 text files use LF (7 byte-identical upstream CRLF files exempted)
PASS  secrets    1166 text files scanned, no findings (11 files skipped as fixtures listed in .gitguardian.yaml)
PASS  shell      21 scripts clean under shellcheck 0.11.0, 6 shell test scripts passed
PASS  runner     ruff clean, pytest passed, 9 examples valid, 3 invalid examples rejected
PASS  testrigs   Maven verify passed (bridge module, JDK 21)
PASS  workflows  2 workflow files clean under actionlint 1.7.12
PASS  docs       docs/tools/check_docs.py and its tests passed
checks: 7 passed, 0 failed, 0 skipped
```

`bash scripts/ci-local.sh verify` ran on the macOS machine on 2026-10-14. Its first step is the same command in strict
mode, and all seven checks passed; that output was not saved, so the block above replaces it.

Then the prepare step and `./run-conformance.sh --component verify` with the testrig and MinIO (run
`20261013T225035Z-c26c8f`, 183 s, exit 0, rig report `T-11_P-11_S-0_F-0_I-0_KI-0` uploaded); exit code 0, artifact in
`$HARNESS_RUN_DIR/ci-local/conformance-verify/`. That check found that the extracted HTML export holds the suite
configuration's private keys; the workflow and `ci-local.sh` now drop the whole `exports/` folder from artifacts.

## GitHub Actions

Hosted runs of `.github/workflows/full-stack-conformance.yml` on branch `ps01-finish`, all on 2026-10-14
([ci.md](ci.md#status-of-the-real-runs) has the history before these):

| Run | Commit | Jobs | Result |
|---|---|---|---|
| [38567545466](https://github.com/Paradox-73/Automated_Conformance_Testing_for_Inji_Certify_and_Inji_Verify/actions/runs/38567545466) | `bfbf62c` | checks, conformance (certify, verify), combined | all green; the first green hosted run |
| [38572816013](https://github.com/Paradox-73/Automated_Conformance_Testing_for_Inji_Certify_and_Inji_Verify/actions/runs/38572816013) | `b10f4b2` | the same, with the testrig jars built in the image and the explicit harness checkout | all green; prepare 231 s and 239 s with no image cache, verify run 126 s |
| [38574676932](https://github.com/Paradox-73/Automated_Conformance_Testing_for_Inji_Certify_and_Inji_Verify/actions/runs/38574676932) | `fd3a38b` | the same plus full-stack (enabled on push for this one run) | all green; full-stack prepare 238 s, run 190 s, exit 0 |

Both gates passed in every run: certify `0 regressions, 9 known gaps, 0 stale, 3 not applicable`, verify
`0 regressions, 0 known gaps, 0 stale`. The `workflow_call` path has not run from an Inji repository yet
([manual-test-checklist.md](manual-test-checklist.md), MT-12).

## Fresh clone and newcomer walkthrough

| Date | OS | Docker | What | Duration | Outcome |
|---|---|---|---|---|---|
| 2026-10-04 | Windows 11, Git Bash | Docker Desktop 29.7.2 | the team's setup per CONTRIBUTING.md | | checks and the verifier happy-flow module ran |
| 2026-10-14 | macOS 15.6.1 | Docker Desktop 28.3.0, 4 GiB | clone of `nikunj/ps01-finish` at `e85a9fb`, `--prepare-only`, `--no-prepare`, `demo.sh --regression` | 3 min | not completed: the laptop's disk filled up while the clone built its own 2.1 GB testrig image (`--prepare-only` exit 3, "Out of diskspace"); the later steps found no healthy stack. Not a harness defect; the next row is the rerun |
| 2026-10-14 | Windows 11, Git Bash, no JDK | Docker Desktop 29.7.2, 7792 MiB, shared with another stack | clone of `ps01-finish` at `5ec802c`, `--prepare-only`, `--no-prepare` | 250 s + 728 s | passed, exit 0; images were already pulled ([evidence](evidence/2026-10-14-20261014T133851Z-c99cce/fresh-clone.txt)) |

The same commands passed in the working clone on 2026-10-14 (TC-03, TC-19, TC-20). A fresh clone on Linux and macOS,
and one with no images pulled, are in [manual-test-checklist.md](manual-test-checklist.md) (MT-01 to MT-03).
