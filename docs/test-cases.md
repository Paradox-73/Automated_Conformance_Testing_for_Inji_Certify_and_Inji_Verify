# Test cases

The harness's own test cases: what each checks, how to run it, what is expected and what happened. Run results
with ids and evidence are in [test-report.md](test-report.md). All dates 2026-10-14 (IST); run ids are UTC.

| Id | Purpose | Steps | Expected | Actual |
|---|---|---|---|---|
| TC-01 | Inji Verify, one command | `./run-conformance.sh --component verify --runner-only` | exit 0, 11 modules, report and badge, stack removed | exit 0, 11 conform (7 REVIEW with evidence, 4 PASSED), 80 s |
| TC-02 | Inji Certify, one command | `./run-conformance.sh --component certify --runner-only` | exit 0, gate with the benchmark | exit 0, 0 regressions, 9 known gaps, 3 not applicable, 89 s |
| TC-03 | Both components in parallel | `./run-full-stack-conformance.sh --no-prepare --runner-only` | exit 0, both results, manifest with wall time per plan | exit 0 twice (285 s, 443 s); plans 114 s and 130 s side by side |
| TC-04 | Same verdicts on a rerun (R1) | `inji-conformance diff <TC-03 run 1> <TC-03 run 2>` | exit 0 | exit 0, 26 unchanged |
| TC-05 | Serial and parallel agree (R5) | `./run-conformance.sh --combined --runner-only --serial`, then `diff` against TC-19 | exit 0, diff exit 0 | exit 0 (166 s), diff exit 0, 26 unchanged |
| TC-06 | Inji Verify stopped mid-run (R2) | stop `verify-service` after the first handoff | the remaining modules are regressions ("handoff not delivered", "never started"), time limit exit 4, stack removed | exit 4 after 341 s with `--timeout-minutes 5`, 11 regressions, no container left |
| TC-07 | Suite restarted mid-run (R3) | `docker restart ps01-harness-suite-server-1` during the issuer plan | the run recovers or fails clearly | recovered: exit 0, same verdicts as TC-02, 13 failed responder polls (HTTP 502) recorded in `notes` |
| TC-08 | Configuration regression (R4) | `HARNESS_COMPOSE_FILES=demo/regression.compose.yml ./run-conformance.sh --component certify --runner-only` | exit 1, the gate names the module | exit 1, 3 regressions named with their conditions |
| TC-09 | A harness port in use (R6) | hold 127.0.0.1:18451, then `./run-conformance.sh --component verify --runner-only` | preflight stops with the port, its service and how to find the holder | exit 3, "ports in use on 127.0.0.1: 18451 (Inji Verify over TLS (tls-proxy))" |
| TC-10 | Benchmark entry removed | `inji-conformance gate --run <TC-02>/certify --benchmark-dir <copy without one entry>` | exit 1, names module and condition | exit 1, `regression: oid4vci-1_0-issuer-fail-unknown-credential-identifier: ... VCIValidateCredentialErrorResponse` |
| TC-11 | Gate agrees with the suite's script | every run without `--no-gate` | the runner's cross-check finds no disagreement | no disagreement in any run; `run-test-plan.py` exited 0 with the benchmark |
| TC-12 | Issuer plan, mTLS variant | `inji-conformance run --component certify --variant sender_constrain=mtls --no-gate` | the conditions each variant reaches | the same conditions as DPoP; neither reaches credential issuance |
| TC-13 | Certify metadata as served (finding) | `CERTIFY_AS_METADATA=as-is ./run-conformance.sh --component certify --runner-only --no-gate` | the suite stops at `CheckServerConfiguration` | 13 of 15 modules INTERRUPTED there |
| TC-14 | Verifier x509_san_dns configuration | `./run-conformance.sh --component verify --runner-only --template verify.oid4vp-1final-verifier-x509-san-dns` | gate with the benchmark | exit 0, 0 regressions, 10 known gaps, 1 not applicable |
| TC-15 | HAIP readiness track | `./run-conformance.sh --combined --runner-only --track haip` | results with `gating: false`, exit 0 | exit 0; 63 issuer and 11 verifier modules, all regressions, not gating |
| TC-16 | Testrig rows and MinIO upload, Certify | `bash testrigs/run-testrig.sh certify --invoke` with the certify and reports profiles | exit 0, report in `automationtests/injicertify/` | exit 0, `T-15_P-3_S-0_F-0_I-3_KI-9`, listed in MinIO |
| TC-17 | Testrig rows and MinIO upload, Verify | `bash testrigs/run-testrig.sh verify --invoke` | exit 0, report in `automationtests/injiverify/` | exit 0, `T-11_P-11_S-0_F-0_I-0_KI-0`, listed in MinIO |
| TC-18 | Upstream patches apply | `git apply --check --directory=api-test` on clean upstream checkouts | succeeds | succeeds for all three patches |
| TC-19 | Full stack with testrigs | `./run-full-stack-conformance.sh --no-prepare` | exit 0, both rig reports, MinIO keys | exit 0 (728 s from a fresh clone, run `20261014T133851Z-c99cce`), both reports in MinIO |
| TC-20 | Demo with regression | `bash demo/demo.sh --regression --runner-only` | gate 0, then 1, diff 16, "demo ok" | as expected, exit 0 |
| TC-21 | Repository checks and local CI | `bash scripts/ci-local.sh verify` | every check PASS, run exit 0 | 7 PASS, run exit 0 (183 s) |
