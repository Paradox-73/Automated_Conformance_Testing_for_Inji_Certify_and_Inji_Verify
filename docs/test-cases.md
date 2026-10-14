# Test cases

The harness's own test cases: what each checks, how to run it and what is expected. What happened, with run ids,
durations and evidence: [test-report.md](test-report.md).

| Id | Purpose | Steps | Expected |
|---|---|---|---|
| TC-01 | Inji Verify, one command | `./run-conformance.sh --component verify --runner-only` | exit 0, 11 modules, report and badge, stack removed |
| TC-02 | Inji Certify, one command | `./run-conformance.sh --component certify --runner-only` | exit 0, gate with the benchmark |
| TC-03 | Both components in parallel | `./run-full-stack-conformance.sh --no-prepare --runner-only` | exit 0, both results, manifest with wall time per plan |
| TC-04 | Same verdicts on a rerun (R1) | `inji-conformance diff <TC-03 run 1> <TC-03 run 2>` | exit 0 |
| TC-05 | Serial and parallel agree (R5) | `./run-conformance.sh --combined --runner-only --serial`, then `diff` against TC-19 | exit 0, diff exit 0 |
| TC-06 | Inji Verify stopped mid-run (R2) | stop `verify-service` after the first handoff | the remaining modules are regressions ("handoff not delivered", "never started"), time limit exit 4, stack removed |
| TC-07 | Suite restarted mid-run (R3) | `docker restart ps01-harness-suite-server-1` during the issuer plan | the run recovers or fails clearly |
| TC-08 | Configuration regression (R4) | `HARNESS_COMPOSE_FILES=demo/regression.compose.yml ./run-conformance.sh --component certify --runner-only` | exit 1, the gate names the module |
| TC-09 | A harness port in use (R6) | hold 127.0.0.1:18451, then `./run-conformance.sh --component verify --runner-only` | preflight stops with the port, its service and how to find the holder |
| TC-10 | Benchmark entry removed | `inji-conformance gate --run <TC-02>/certify --benchmark-dir <copy without one entry>` | exit 1, names module and condition |
| TC-11 | Gate agrees with the suite's script | every run without `--no-gate` | the runner's cross-check finds no disagreement |
| TC-12 | Issuer plan, mTLS variant | `inji-conformance run --component certify --variant sender_constrain=mtls --no-gate` | the conditions each variant reaches |
| TC-13 | Certify metadata as served (finding) | `CERTIFY_AS_METADATA=as-is ./run-conformance.sh --component certify --runner-only --no-gate` | the suite stops at `CheckServerConfiguration` |
| TC-14 | Verifier x509_san_dns configuration | `./run-conformance.sh --component verify --runner-only --template verify.oid4vp-1final-verifier-x509-san-dns` | gate with the benchmark |
| TC-15 | HAIP readiness track | `./run-conformance.sh --combined --runner-only --track haip` | results with `gating: false`, exit 0 |
| TC-16 | Testrig rows and MinIO upload, Certify | `bash testrigs/run-testrig.sh certify --invoke` with the certify and reports profiles | exit 0, report in `automationtests/injicertify/` |
| TC-17 | Testrig rows and MinIO upload, Verify | `bash testrigs/run-testrig.sh verify --invoke` | exit 0, report in `automationtests/injiverify/` |
| TC-18 | Upstream patches apply | `git apply --check --directory=api-test` on clean upstream checkouts | succeeds |
| TC-19 | Full stack with testrigs | `./run-full-stack-conformance.sh --no-prepare` | exit 0, both rig reports, MinIO keys |
| TC-20 | Demo with regression | `bash demo/demo.sh --regression --runner-only` | gate 0, then 1, diff 16, "demo ok" |
| TC-21 | Repository checks and local CI | `bash scripts/ci-local.sh verify` | every check PASS, run exit 0 |
