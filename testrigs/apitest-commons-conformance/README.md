# apitest-commons-conformance

A small Java library that puts OpenID Foundation conformance results into a MOSIP api-testrig run: one TestNG row
per conformance test module, in the rig's existing `EmailableReport` HTML report, uploaded to S3/MinIO like any
other rig report. Written as a candidate addition to
[API Test Commons](https://github.com/mosip/mosip-functional-tests/tree/master/apitest-commons) (package
`io.mosip.testrig.apirig.conformance`), so it depends only on what every rig already has.

- Licence: MIT (team code). Java 21. Maven coordinates
  `io.mosip.testrig.apitest.commons:apitest-commons-conformance:0.1.0-SNAPSHOT`.
- `apitest-commons` is a `provided` dependency: each rig keeps its own version (Inji Verify 1.5.0, Inji Certify
  1.6.0). The library uses only API present in both: `TestCaseDTO`, `GlobalConstants`, `ConfigManager`.
- Used by `OpenIDConformanceTest` and `ConformanceRigRunner` in [`../inji-verify-api-test`](../inji-verify-api-test)
  (see [Inji Verify rig integration](#inji-verify-rig-integration) below).

## What it does

```
results.json (written by the inji-conformance runner, schema conformance/schema/results.schema.json v1)
   |  ResultsReader          checks schema_version, component, plan, and each module's name, status and verdict
   v
ConformanceResults -> OutcomeMapper   one Outcome per module: PASS, FAIL, KNOWN_ISSUE, IGNORED or SKIP
   |  ConformanceCaseLoader         adds ids and names; turns every runner or file problem into a failing row
   v
ConformanceTestSupport   testCases(): TestCaseDTO[] for the rig's data provider
                         check(dto):  Reporter.log(details), then return / AssertionError / SkipException
   v
EmailableReport (unchanged)   mosip-<env.user>-injiverify-conformance-<date>-full-report_T-.._P-.._S-.._F-.._I-.._KI-...html
```

| Package | Classes | Job |
|---|---|---|
| `results` | `ResultsReader`, `ConformanceResults`, `ModuleResult`, `Verdict`, `ResultsFormatException` | Read `results.json` v1. Unknown extra fields are ignored, so a newer runner does not break older rigs. Errors name the file and the JSON path, for example `$.modules[3].verdict has unknown value "passed"`. |
| (root) | `OutcomeMapper`, `Outcome` | Map the runner's `verdict` field to a TestNG result (table below). Never re-classifies the suite outcome. |
| `runner` | `ConformanceSettings`, `RunnerInvoker` | Read the `conformance.*` settings; start the runner as a child process with a time limit (invoke mode). |
| `testng` | `ConformanceTestSupport`, `ConformanceCaseLoader`, `ConformanceCase`, `ReportText` | Rows for the data provider and the per-row check. |
| `rig` | `RigRun`, `TestNgResults` | Shared part of a rig's `ConformanceRigRunner`: report folder, TestNG output folder, exit code from `testng-results.xml`. |

## Settings

Each key is read as a JVM system property (`-Dkey=value`), then as an environment variable with the same name (the
apitest-commons `ConfigManager` convention), then as an upper-case environment variable (`CONFORMANCE_RESULTS_FILE`).

| Key | Default | Meaning |
|---|---|---|
| `conformance.results.file` | unset | Consume mode: read this `results.json`. Wins over the command. |
| `conformance.runner.command` | unset | Invoke mode: command line of the runner, with placeholders `{component}`, `{target}`, `{out}`. Example: `inji-conformance run --component {component} --target {target} --out {out}`. The runner must write `{out}/{component}/results.json`. |
| `conformance.target` | `env.endpoint` | Base URL of the system under test, passed as `{target}`. |
| `conformance.runner.out` | `${HARNESS_RUN_DIR}/testrig/runner`, else `<working dir>/testng-report/runner` | Folder for the runner's output and its log `runner.log`. |
| `conformance.runner.timeout.minutes` | `90` | Time limit; on timeout the runner and every process it started are killed and the run gets a failing row. |
| `conformance.report.dir` | `${HARNESS_RUN_DIR}/testrig/<module>`, else `<working dir>/testng-report/conformance` | `ConformanceRigRunner` only: TestNG output and report folder. Must be on the same drive as the working directory (Windows). |

With neither `conformance.results.file` nor `conformance.runner.command` the rig reports a single **Ignored** row,
`feature not supported: conformance runner not configured (...)`. The stock `InjiTestRunner` runs every file in
`testNgXmlFiles/` whose name contains `mastertestsuite`, so the conformance suite file joins every existing rig
run; this row keeps such runs green when no conformance runner is set up.

The command is split into arguments like a POSIX shell would split it (quotes group words; a backslash escapes only
a quote, a backslash or a space, so Windows paths work), and it is started without a shell: a target URL cannot
inject a command.

## Verdict mapping

The runner computes each module's `verdict` once (from the suite result and the benchmark of expected failures and
skips); the gate, the HTML summary and this library all read that field, so they always agree.

| `verdict` | TestNG result | `EmailableReport` column | Message starts with |
|---|---|---|---|
| `conforms` | pass | P | (none; details list the suite log link, handoffs, review evidence) |
| `known_gap` | `SkipException` | KI (Known Issues) | `known issue. Hence skipping the testcase: <condition>: <comment> (owner, spec, issue)` |
| `not_applicable` | `SkipException` | I (Ignored) | `feature not supported: the suite skipped this module and the benchmark expects that: ...` |
| `regression` | `AssertionError` | F | `regression: <verdict_reason>` |
| `stale_benchmark` | `AssertionError`; pass with a warning line when the run used `--allow-stale` | F (or P) | `stale benchmark entry: ...; remove the benchmark entry or update it ...` |
| any failure in a file with `gating: false` (HAIP readiness track) | `SkipException` | S | `not gating (haip track), would fail: ...` |

- KI messages start with the whole `GlobalConstants.KNOWN_ISSUES` text: `EmailableReport` files a skip under KI when
  its message contains `known issue`, but also counts it as a plain skip unless it contains the whole constant.
- Rows that are not modules (id `TC_OIDF_<COMPONENT>_00`) fail with the reason when the results cannot be read, are
  for the other component, list no modules, or the runner could not start, timed out, exited without results, or
  exited with a code other than 0 or 1 (2 usage, 3 environment not ready, 4 whole-run timeout).
- A gating results file whose gate failed always yields at least one failing row (a `Gate` row is added if no
  module failed), so the rig exit code matches the conformance gate.

## Row ids and names

| Field | Value | Example |
|---|---|---|
| `uniqueIdentifier` | `TC_OIDF_<COMPONENT>_<nn>`, `nn` = position in the plan | `TC_OIDF_VERIFY_03` |
| `testCaseName` | `<RigPrefix>_OpenIDConformance_<module>` (variant values appended when a module repeats) | `InjiVerify_OpenIDConformance_oid4vp-1final-verifier-request-uri-method-post` |
| `description` | the suite's module summary plus the plan name | `The suite acts as a wallet ... [oid4vp-1final-verifier-test-plan]` |
| `endPoint` | the target base URL from the results | `https://verify.inji.test:18451/v1/verify` |

The test case name works with the rig's `testCaseSkippedList.txt`, like every other rig test.

## Building and testing

From the repository root, with JDK 21 and Maven 3.9:

```bash
mvn -B -f testrigs/pom.xml -pl apitest-commons-conformance verify
```

The JUnit 5 tests read the repository's results examples in `conformance/schema/examples/` (the same files the
Python runner's tests validate) and this module's fixtures in `src/test/resources/fixtures/`. Invoke-mode tests
start `FakeRunner.java` with the JDK's source launcher, so they need neither Python nor a shell.

## Inji Verify rig integration

Files added to the imported rig [`../inji-verify-api-test`](../inji-verify-api-test) (all MIT, new files except
one line in `pom.xml`):

| File | Purpose |
|---|---|
| `pom.xml` | One dependency line on this library. |
| `src/main/java/.../testscripts/OpenIDConformanceTest.java` | The TestNG class: same shape as `SimplePost` (`ITest`, `testcaselist` data provider, `@AfterMethod` sets the `TestCaseName` attribute that `EmailableReport` shows); sets the report name `injiverify-conformance`. |
| `src/main/java/.../testrunner/ConformanceRigRunner.java` | Runs only the conformance suite: stock start-up without health checker, API suites and DB cleanup; report in `conformance.report.dir`; exit code 0, 1 or 2. |
| `testNgXmlFiles/injiverifyConformanceMasterTestSuite.xml` | Master suite with the `EmailableReport` listener. Its name contains `Master Suite`, which `EmailableReport` leaves out of the report, so the rows sit in the child suite. |
| `testNgXmlFiles/injiverifyConformanceSuite.xml` | Child suite with the one `<test>`. |

Run it from `testrigs/inji-verify-api-test` after the build (the jar path is the rig's shaded jar):

```bash
export HARNESS_RUN_DIR=/e/Projects/MOSIP/PS01/run/harness
java -Dmodules=injiverify -Denv.user=ps01 -Denv.endpoint=https://verify.inji.test:18451 \
     -Denv.testLevel=smokeAndRegression \
     -Dconformance.results.file=../../conformance/schema/examples/results-verify.example.json \
     -Dconformance.report.dir=$HARNESS_RUN_DIR/wp11 \
     -cp target/apitest-injiverify-1.0.0-alpha.2-SNAPSHOT-jar-with-dependencies.jar \
     io.inji.testrig.apirig.injiverify.testrunner.ConformanceRigRunner
echo "exit $?"
```

- Exit code: 0 no failing row, 1 at least one failing row (or failed configuration method), 2 the run could not
  start or TestNG wrote no `testng-results.xml`. The stock `InjiTestRunner` always exits 0.
- Output in `conformance.report.dir`: `mosip-<env.user>-injiverify-conformance-<yyyy-MM-dd_HH-mm>-full-report_T-<n>_P-.._S-.._F-.._I-.._KI-...html`,
  an `error-report` copy when anything failed or was skipped, and TestNG's own files (`testng-results.xml`, ...).
- S3/MinIO upload: the stock `EmailableReport` settings, as environment variables (`push-reports-to-s3=yes`,
  `s3-host`, `s3-account`, `s3-region`, `s3-user-key`, `s3-user-secret`). With upload off, `ConformanceRigRunner`
  sets `mountPathForReport` to the report folder so the copy step writes nowhere else (an environment variable of
  that name still wins).
- The report header lists server component versions by calling actuator URLs under `env.endpoint`; with an
  unreachable endpoint that part stays empty and the run continues.

## Measured results

Run on 2026-10-04 on the team laptop (Windows 11, JDK 21.0.12, Maven 3.9.9), from a clean working tree:

| Check | Result |
|---|---|
| `mvn -B -f testrigs/pom.xml -pl apitest-commons-conformance,inji-verify-api-test -am package -Dgpg.skip=true -Dmaven.gitcommitid.skip=true` | BUILD SUCCESS in 8 min 23 s; 51 JUnit tests, 0 failures |
| `ConformanceRigRunner` with `results-verify.example.json` | exit 0; `mosip-ps01-injiverify-conformance-2026-10-04_16-40-full-report_T-11_P-10_S-0_F-0_I-0_KI-1.html`, rows `TC_OIDF_VERIFY_01` to `_11` |
| `ConformanceRigRunner` with `results-verify-regression.example.json` | exit 1; `...-full-report_T-11_P-9_S-0_F-1_I-0_KI-1.html` and `...-error-report_T-2_S-0_F-1_I-0_KI-1.html` |
| `ConformanceRigRunner` with no `conformance.*` setting | exit 0; `...-full-report_T-1_P-0_S-0_F-0_I-1_KI-0.html` (one Ignored row) |

- Each rig run took 5 to 7 minutes, almost all of it the stock resource extraction from the 405 MB shaded jar;
  the TestNG part took under 5 seconds.
- Invoke mode is covered by the JUnit tests (a stand-in runner), not yet by a run of the real `inji-conformance run`
  against a live suite.
