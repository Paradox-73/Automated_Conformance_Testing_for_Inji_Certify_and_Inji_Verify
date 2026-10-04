# testrigs

The Inji api-testrigs (MOSIP's TestNG API test projects for Inji Certify and Inji Verify) and a bridge library
that turns conformance results into TestNG results inside them.

Lane: testrig. Status on 2026-10-04: both api-testrigs imported; the bridge library, the aggregator `pom.xml` and the
Inji Verify rig integration are in place (see [apitest-commons-conformance/README.md](apitest-commons-conformance/README.md));
the Inji Certify rig integration, the testrig image and the S3 upload check come next.

## Contents

| Path | Purpose | Licence | Status |
|---|---|---|---|
| `inji-certify-api-test/` | MOSIP's TestNG API tests for Inji Certify (Maven project `apitest-injicertify`, Java 21, apitest-commons 1.6.0) | Apache-2.0 | imported, unchanged |
| `inji-verify-api-test/` | MOSIP's TestNG API tests for Inji Verify (Maven project `apitest-injiverify`, Java 21, apitest-commons 1.5.0) | Apache-2.0; team files MIT | imported; plus `OpenIDConformanceTest`, `ConformanceRigRunner`, two suite XMLs and one `pom.xml` line |
| `apitest-commons-conformance/` | Bridge library: reads the runner's results, runs the runner, maps each conformance test module to a TestNG result | MIT | done |
| `pom.xml` | Maven aggregator for the three projects | MIT | done |
| `Dockerfile`, `build.sh`, `run-testrig.sh` | Testrig image and entry points | MIT | planned |
| `upstream-patches/` | The few changes made to upstream files, as patches | MIT | planned |

## Provenance of the imported testrigs

Each folder is the `api-test/` folder of one upstream commit, byte for byte, plus that repository's root `LICENSE`
(Apache License 2.0). Each arrived in its own commit whose message starts with `import: upstream inji/`, so every
later team change to these files shows up as an ordinary diff against that commit.

| Folder | Upstream repository | Branch | Commit | Upstream tree `api-test/` | Files | Import commit |
|---|---|---|---|---|---|---|
| `inji-certify-api-test/` | [inji/inji-certify](https://github.com/inji/inji-certify) | release-1.0.x | `203b143ddaa6d1b01406bdb3d247a57161830a77` (2026-10-01) | `1f5d7961dd99` | 659 + `LICENSE` | `9d07328` `import: upstream inji/inji-certify@203b143 (Apache-2.0)` |
| `inji-verify-api-test/` | [inji/inji-verify](https://github.com/inji/inji-verify) | release-1.0.x | `6a6ab3bf6cb1bcdbfbacc9dfe16b7e87cb56a5af` (2026-10-01) | `65af30405661` | 250 + `LICENSE` | `f307a88` `import: upstream inji/inji-verify@6a6ab3b (Apache-2.0)` |

Not imported: the rest of each upstream repository, and Inji Verify's root `licenses/` folder (licence texts of the
Verify UI's third-party packages, which the testrig does not ship).

### How the folders were made

```bash
git -C <inji-certify clone> -c core.autocrlf=false archive 203b143:api-test | tar -x -C testrigs/inji-certify-api-test
git -C <inji-certify clone> -c core.autocrlf=false archive 203b143 LICENSE  | tar -x -C testrigs/inji-certify-api-test
git -C <inji-verify clone>  -c core.autocrlf=false archive 6a6ab3b:api-test | tar -x -C testrigs/inji-verify-api-test
git -C <inji-verify clone>  -c core.autocrlf=false archive 6a6ab3b LICENSE  | tar -x -C testrigs/inji-verify-api-test
```

- `core.autocrlf=false` matters: with the Git for Windows default (`true`), `git archive` rewrites LF to CRLF and
  the files no longer match upstream ([third_party/README.md](../third_party/README.md)).
- The repository's `.gitattributes` sets `-text` on every file, so git stores the bytes exactly as extracted.
- No file in either tree is excluded by a `.gitignore` rule; all 909 upstream files are committed.

### How to check that the folders still match upstream

In clones of the two upstream repositories, compare every file's blob id (a hash of its exact bytes) with the
committed one. No output means identical:

```bash
# blob_ids GIT-ARGS...: runs git with a "ls-tree -r" command; prints "<mode> <blob id> <path>" per file, minus LICENSE.
blob_ids() { git "$@" | grep -v $'\tLICENSE$' | awk '{print $1, $3, $4}'; }

diff <(blob_ids -C <inji-certify clone> ls-tree -r 203b143:api-test) \
     <(blob_ids ls-tree -r HEAD:testrigs/inji-certify-api-test)
diff <(blob_ids -C <inji-verify clone> ls-tree -r 6a6ab3b:api-test) \
     <(blob_ids ls-tree -r HEAD:testrigs/inji-verify-api-test)
```

Run on 2026-10-04 right after the import commits: both printed nothing. Once team patches land, use the import
commit instead of `HEAD` for this comparison, and `git diff <import commit> -- testrigs/inji-*-api-test` to see
the team's changes.

### Line endings and test credentials in the imported files

- Seven Verify testrig files under `src/main/resources/injiverify/` contain CRLF line endings upstream (four mix
  CRLF and LF; the three `VcSubmission/*.hbs` files are CRLF throughout). They are listed with their upstream blob
  ids in `scripts/eol-exempt.txt`, so `bash scripts/check.sh eol` accepts them only while they stay identical to
  upstream. The Certify testrig has no CRLF files.
- Ten imported files hold test-only key or credential material that upstream publishes for its test environments
  (a private Ed25519 JWK in a request template, test user passwords, a test client secret, `AUTH_SECRET_KEY`).
  They are listed, with the reason for each, in `.gitguardian.yaml`. The harness does not use these values.
- Result on 2026-10-04 after the import: `bash scripts/check.sh eol secrets` printed PASS for both checks
  (7 upstream CRLF files exempted, 10 listed fixtures skipped).
- Build: the Inji Verify rig (with the bridge) builds through the aggregator `pom.xml` (BUILD SUCCESS on
  2026-10-04, 8 min 23 s under a shared Maven cache, shaded jar 404,728,104 bytes). The Inji Certify rig has not
  been built through the aggregator yet.

## Conformance rows in the rigs

`OpenIDConformanceTest` adds one TestNG row per OpenID conformance test module (`TC_OIDF_VERIFY_nn`) to the rig's
`EmailableReport`; `ConformanceRigRunner` runs only those rows and exits 1 when one fails. Settings, verdict mapping,
the files added to the Verify rig and the run command are in
[apitest-commons-conformance/README.md](apitest-commons-conformance/README.md). The team's changes to the imported
Verify rig: `git diff f307a88 -- testrigs/inji-verify-api-test`.

Build the bridge and the Inji Verify rig (JDK 21, Maven 3.9):

```bash
mvn -B -f testrigs/pom.xml -pl apitest-commons-conformance,inji-verify-api-test -am package     -Dgpg.skip=true -Dmaven.gitcommitid.skip=true
```

## Checks

`bash scripts/check.sh testrigs` runs `mvn verify` on the bridge library (and the modules it needs) once
`testrigs/pom.xml` exists. It needs JDK 21 and Maven 3.9; extra Maven options can come from the `MAVEN_ARGS`
environment variable. On a machine where other builds share the Maven repository, run it under the shared lock.
