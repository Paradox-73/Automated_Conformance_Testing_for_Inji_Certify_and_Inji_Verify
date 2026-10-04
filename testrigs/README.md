# testrigs

The Inji api-testrigs (MOSIP's TestNG API test projects for Inji Certify and Inji Verify) and a bridge library
that turns conformance results into TestNG results inside them.

Lane: testrig. Status on 2026-10-04: empty.

## Planned contents

| Path | Purpose | Licence |
|---|---|---|
| `inji-certify-api-test/` | `api-test/` of [inji/inji-certify](https://github.com/inji/inji-certify) at `203b143` (branch release-1.0.x), imported unchanged first | Apache-2.0 |
| `inji-verify-api-test/` | `api-test/` of [inji/inji-verify](https://github.com/inji/inji-verify) at `6a6ab3b` (branch release-1.0.x), imported unchanged first | Apache-2.0 |
| `apitest-commons-conformance/` | Bridge library: reads the runner's results, runs the runner, maps each conformance test module to a TestNG result | MIT |
| `pom.xml` | Maven aggregator for the three projects | MIT |
| `Dockerfile`, `build.sh`, `run-testrig.sh` | Testrig image and entry points | MIT |
| `upstream-patches/` | The few changes made to upstream files, as patches | MIT |

## Notes for the imports

- Extract with `git -c core.autocrlf=false archive`; [third_party/README.md](../third_party/README.md) explains why.
- Seven Verify testrig files under `src/main/resources/injiverify/` contain CRLF line endings upstream (four mix
  CRLF and LF). They are listed with their upstream blob ids in `scripts/eol-exempt.txt`, so
  `bash scripts/check.sh eol` accepts them only while they stay identical to upstream.
- Upstream test fixtures with key or credential material (a private JWK, test passwords, `AUTH_SECRET_KEY`) are
  already listed in `.gitguardian.yaml`.

## Checks

`bash scripts/check.sh testrigs` runs `mvn verify` on the bridge library (and the modules it needs) once
`testrigs/pom.xml` exists. It needs JDK 21 and Maven 3.9; extra Maven options can come from the `MAVEN_ARGS`
environment variable. On a machine where other builds share the Maven repository, run it under the shared lock.
