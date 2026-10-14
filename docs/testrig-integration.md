# Testrig integration

How conformance results become TestNG rows in the Inji api-testrigs (MOSIP's TestNG API test projects), in their
stock `EmailableReport`, uploaded to MinIO like any other rig report. Library details:
[testrigs/apitest-commons-conformance/README.md](../testrigs/apitest-commons-conformance/README.md).

## What is added to each rig

| Rig | Added | Row ids |
|---|---|---|
| Inji Certify (`testrigs/inji-certify-api-test`, upstream `203b143`) | `OpenIDConformanceTest`, `ConformanceRigRunner`, `injicertifyConformanceMasterTestSuite.xml`, `injicertifyConformanceSuite.xml`, one `pom.xml` dependency line (and the duplicate javadoc plugin merged) | `TC_OIDF_CERTIFY_01` to `_15` |
| Inji Verify (`testrigs/inji-verify-api-test`, upstream `6a6ab3b`) | the same four files and line (WP-11), and the upload settings call | `TC_OIDF_VERIFY_01` to `_11` |

`OpenIDConformanceTest` has the shape of the rigs' other scripts (`ITest`, a `testcaselist` data provider,
`@AfterMethod` naming each row). It reads `env.endpoint` like every rig test. Rows come from a `results.json`
(consume mode, `-Dconformance.results.file=`) or from the runner the rig starts itself (invoke mode,
`-Dconformance.runner.command=`). The stock `InjiTestRunner` also runs the conformance suite file and reports one
Ignored row when neither is set, so normal rig runs stay green.

In invoke mode the runner tests the system the rig is configured for: `run-testrig.sh` passes the command
`inji-conformance run --component {component} --target {target}... --out {out}`, and the bridge fills `{target}` with
the rig's `env.endpoint` (`ConformanceSettings`). Inji Verify's API is below `/v1/verify`, so the Verify command
appends that path. `TESTRIG_ENDPOINT` sets `env.endpoint`; the default is the compose service
(`https://certify.inji.test:18450`, `https://verify.inji.test:18451`). `./run-conformance.sh` uses consume mode,
because its runner step has already run the plan; invoke mode would run the same plan a second time.

`ConformanceRigRunner` runs only the conformance suite and exits 0, 1 (a failing row) or 2 (the rig could not run).
The Certify runner leaves out what the stock runner does before any test and that needs a full MOSIP deployment:
health checker, Keycloak users, OTP listener and setup, partner setup, database cleanup.

## Verdict to TestNG result

| Verdict | Row | Report column |
|---|---|---|
| `conforms` | pass | P |
| `known_gap` | skip with the `KNOWN_ISSUES` text, the condition and the benchmark comment | KI |
| `not_applicable` | skip, feature not supported | I |
| `regression`, `stale_benchmark` | failure with the reason | F |
| any failure on the haip track | skip, "not gating" | S |

## Build, image, run

<!-- run 2026-10-14 -->
```bash
bash testrigs/build.sh --image
bash scripts/dc.sh --profile certify --profile reports up -d --wait
bash testrigs/run-testrig.sh certify --invoke
bash scripts/dc.sh run --rm minio-mc ls local/automationtests/injicertify/
bash scripts/dc.sh --profile '*' down -v
```

- `testrigs/build.sh --image` builds `ps01-harness/testrig:local` from `testrigs/Dockerfile` in two stages. The
  first stage (`maven:3.9.11-eclipse-temurin-21`) compiles both shaded jars (about 390 MB each) from the sources in
  the build context, with the Maven repository in a BuildKit cache mount. The second stage (Temurin 21 JRE, Python 3
  with the runner, both jars and suite files; 2.1 GB) is the image. Only Docker is needed on the host, on any OS.
- `testrigs/build.sh` without `--image` builds the jars on the host instead: with the host's Maven on JDK 21 or
  newer, else in the Maven image with the checkout bind-mounted, which is slow on Windows and macOS.
- `testrigs/run-testrig.sh certify|verify --results FILE | --invoke` runs the rig in that image on the compose
  network as the calling user; with MinIO running it uploads to `automationtests/<module>/`.
- `./run-conformance.sh` (without `--runner-only`) runs the consume mode for each component after the runner and
  copies the report to `<run>/testrig/<component>/`.

Image build measured 2026-10-14 on Windows 11 without a host JDK (Docker Desktop, 8 GB VM, 12 CPUs, shared with
another team's Inji stack): first build 648 s, of which Maven 541 s; a rebuild with `--no-cache` and the Maven cache
mount kept took 926 s while that stack's three Java services used about 6 CPUs, so the time is bounded by CPU in
the Docker VM (compiling and shading two 390 MB jars), not by downloads. Before the jars moved into the image, the
bind-mounted Maven container on the same machine was still in the Certify rig's `jar` step after 60 minutes.

Measured 2026-10-14 (host Maven, warm cache): jars in 95 s; Certify rig in invoke mode exit 0,
`mosip-ps01-injicertify-conformance-2026-10-13_21-54-full-report_T-15_P-3_S-0_F-0_I-3_KI-9.html`, listed in MinIO under
`automationtests/injicertify/`; Verify rig exit 0, `..._T-11_P-11_S-0_F-0_I-0_KI-0.html` under
`automationtests/injiverify/`. A rig run takes 1 to 3 minutes in the image, most of it the stock resource
extraction from the jar.

## Report upload

`EmailableReport` uploads when apitest-commons' `push-reports-to-s3` is `yes`. apitest-commons lets an environment
variable replace only keys its property files already contain, and the rigs' files have none of the `s3-*` keys,
so `ConformanceRigRunner` copies them in (`RigRun.applyUploadSettings`) from system properties or environment
variables (`PUSH_REPORTS_TO_S3`, `S3_HOST`, `S3_ACCOUNT`, `S3_REGION`, `S3_USER_KEY`, `S3_USER_SECRET`).
`run-testrig.sh` sets them for the harness's MinIO, with the password from `$HARNESS_RUN_DIR/env.local`.

## Upstream patches

`testrigs/upstream-patches/` holds the team's rig changes as `git format-patch` series; on 2026-10-14
`git apply --check --directory=api-test` succeeded on clean checkouts of both upstream commits
([testrigs/upstream-patches/README.md](../testrigs/upstream-patches/README.md)).
