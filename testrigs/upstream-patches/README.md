# Upstream patches

The team's changes to the two imported api-testrigs, one patch per rig, ready to offer to Inji as pull requests.
Each patch is the whole difference between the rig folder and its upstream import, with a commit message written
for the upstream repository.

| Folder | Applies to | Patch |
|---|---|---|
| `inji-certify-api-test/` | [inji/inji-certify](https://github.com/inji/inji-certify) `203b143`, folder `api-test/` | OpenID conformance TestNG suite for the Inji Certify rig (`OpenIDConformanceTest`, `ConformanceRigRunner`, two suite files, `pom.xml`) |
| `inji-verify-api-test/` | [inji/inji-verify](https://github.com/inji/inji-verify) `6a6ab3b`, folder `api-test/` | the same for the Inji Verify rig |

## Build a patched rig

Both patches add the dependency `io.mosip.testrig.apitest.commons:apitest-commons-conformance:0.1.0-SNAPSHOT`, the
bridge library in [`../apitest-commons-conformance`](../apitest-commons-conformance). It is meant for API Test
Commons (`mosip-functional-tests`) and is in no Maven repository yet, so install it into the local Maven repository
(`~/.m2`) first. It needs JDK 21 and Maven 3.9 and builds on its own (no parent pom):

```bash
git clone https://github.com/Paradox-73/Automated_Conformance_Testing_for_Inji_Certify_and_Inji_Verify.git inji-conformance-harness
mvn -B -f inji-conformance-harness/testrigs/apitest-commons-conformance/pom.xml install

git -C <inji-verify clone> -c core.autocrlf=false checkout 6a6ab3b
git -C <inji-verify clone> apply --directory=api-test \
  "$PWD"/inji-conformance-harness/testrigs/upstream-patches/inji-verify-api-test/*.patch
mvn -B -f <inji-verify clone>/api-test/pom.xml package -Dgpg.skip=true -Dmaven.gitcommitid.skip=true
```

The same steps work for inji-certify at `203b143` with the `inji-certify-api-test` patch. Until the bridge is
published, an upstream merge must come after the bridge lands in API Test Commons (or the 14 bridge classes are
copied into each rig).

## Make them again

After a commit that changes a rig, regenerate the diff below each patch's header. Keep everything above the first
`---` line (the commit message) and replace the rest with the output of (`9d07328` and `f307a88` are the import
commits):

```bash
git diff --stat=72 --relative=testrigs/inji-certify-api-test 9d07328 -- testrigs/inji-certify-api-test
git diff --full-index --relative=testrigs/inji-certify-api-test 9d07328 -- testrigs/inji-certify-api-test
```

and the same with `inji-verify-api-test` and `f307a88`.

## Check them

In a clean checkout of the upstream commit (`git -c core.autocrlf=false` keeps upstream's bytes):

```bash
git -C <inji-certify clone> checkout 203b143
git -C <inji-certify clone> apply --check --directory=api-test <this repo>/testrigs/upstream-patches/inji-certify-api-test/*.patch
```

Measured on 2026-10-25 against the import commits' trees (`git archive 9d07328:testrigs/inji-certify-api-test`, the
same bytes as upstream `203b143:api-test`, and `f307a88` for Verify): both patches apply, and the patched trees equal
`testrigs/inji-*-api-test` file for file.
