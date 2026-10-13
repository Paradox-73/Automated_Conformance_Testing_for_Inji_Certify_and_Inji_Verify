# Upstream patch series

The team's changes to the two imported api-testrigs, as `git format-patch` series that apply to the upstream
repositories, so they can be offered to Inji as pull requests. One folder per rig; each patch is one team commit
that touched the rig, with its message and author.

| Folder | Applies to | Patches |
|---|---|---|
| `inji-certify-api-test/` | [inji/inji-certify](https://github.com/inji/inji-certify) `203b143`, folder `api-test/` | Certify rig integration (`OpenIDConformanceTest`, `ConformanceRigRunner`, two suite files, one `pom.xml` line) |
| `inji-verify-api-test/` | [inji/inji-verify](https://github.com/inji/inji-verify) `6a6ab3b`, folder `api-test/` | Verify rig integration (WP-11), then the report upload settings call (WP-12) |

The rigs depend on `apitest-commons-conformance` (`../apitest-commons-conformance`), which belongs in API Test
Commons upstream; until then it is installed with `mvn -f testrigs/pom.xml -pl apitest-commons-conformance install`.

## Make them again

From the repository root, after a commit that changes a rig (`9d07328` and `f307a88` are the import commits):

```bash
rm -rf testrigs/upstream-patches/inji-*-api-test
git format-patch --no-signature --relative=testrigs/inji-certify-api-test \
  -o testrigs/upstream-patches/inji-certify-api-test 9d07328..HEAD -- testrigs/inji-certify-api-test
git format-patch --no-signature --relative=testrigs/inji-verify-api-test \
  -o testrigs/upstream-patches/inji-verify-api-test f307a88..HEAD -- testrigs/inji-verify-api-test
```

## Check them

In a clean checkout of the upstream commit (`git -c core.autocrlf=false` keeps upstream's bytes):

```bash
git -C <inji-certify clone> checkout 203b143
git -C <inji-certify clone> apply --check --directory=api-test <this repo>/testrigs/upstream-patches/inji-certify-api-test/*.patch
```

Measured on 2026-10-14: `git apply --check --directory=api-test` succeeded for the one Certify patch on `203b143`
and for both Verify patches, applied in order, on `6a6ab3b`.
