# third_party

Upstream code imported byte for byte. The team does not edit anything here; a newer upstream version is a new
import commit, so `git log -- third_party/` shows every upstream change separately from the team's own work.

Lane: runner.

## oidf-conformance-suite

The automation scripts of the OpenID Foundation conformance suite. The harness runner calls `run-test-plan.py`
to create, configure, run and poll a test plan through the suite's REST API and to export its results.
`run-test-plan.py` imports `conformance.py` (the REST API client) and `test_plan_parser.py` (the plan and variant
argument parser). `compare-results.py` compares two exports. `requirements.txt` lists their Python dependencies
(`httpx`, `pyparsing`).

### Provenance

| Item | Value |
|---|---|
| Repository | [openid/conformance-suite](https://gitlab.com/openid/conformance-suite) |
| Tag | `release-v5.3.1` (lightweight tag) |
| Commit | `440eec8bac7b12b7389d7ca9cbc459b53507a443` (from `git ls-remote`, 2026-10-04) |
| Licence | MIT, `oidf-conformance-suite/LICENSE.txt` (Copyright (c) 2019-2020 OpenID Foundation) |
| Import commit | `import: upstream openid/conformance-suite@440eec8bac7b12b7389d7ca9cbc459b53507a443 (MIT)` |
| Imported on | 2026-10-04 |

| File | Upstream path | Git blob id |
|---|---|---|
| `oidf-conformance-suite/LICENSE.txt` | `LICENSE.txt` | `a25d7ee3d339e80d91714e4427ca5d695287241c` |
| `oidf-conformance-suite/scripts/compare-results.py` | `scripts/compare-results.py` | `3cedbda8d37c71e95daeb41db75a2cabd3918620` |
| `oidf-conformance-suite/scripts/conformance.py` | `scripts/conformance.py` | `b72f7f6d53f3029986e6b98f39f0b96b3dc61201` |
| `oidf-conformance-suite/scripts/requirements.txt` | `scripts/requirements.txt` | `c491c56b29d622544d18387f78a664d42189b6d7` |
| `oidf-conformance-suite/scripts/run-test-plan.py` | `scripts/run-test-plan.py` | `45e82abab5713cd03b9305ae2ed5bbac9c3a7ba2` |
| `oidf-conformance-suite/scripts/test_plan_parser.py` | `scripts/test_plan_parser.py` | `872aff69b61635a147730343bb4184ef304c92ee` |

A git blob id is the hash git computes over a file's exact bytes, so equal ids mean identical files. The ids
above are also kept as the manifest inside `reimport.sh`.

Deliberately not imported:

- `scripts/certs-keys/`: upstream test private keys and certificates. `run-test-plan.py` lists the `certs-keys/`
  folder next to itself on every start (`run-test-plan.py` lines 1181-1189) and stops with `FileNotFoundError`
  when it is missing; each file's content then replaces a `{<file name>}` placeholder in plan configurations
  (lines 164-165). So the scripts cannot run straight from this folder: the runner copies them into the run
  folder (`$HARNESS_RUN_DIR`) and creates `certs-keys/` there holding the keys generated for that run.
- The other files in upstream `scripts/` (integration-test drivers, whitespace checkers, upstream test
  configurations): the harness does not run them.

File modes: upstream marks `compare-results.py` and `run-test-plan.py` executable (git mode `100755`); here all
six files are `100644`, because commits made on Windows (`core.filemode=false`) cannot record the executable bit.
The harness always starts the scripts as `python run-test-plan.py ...`, so the mode has no effect. The content
is unaffected: the blob ids above are identical.

### Checking the import

From the repository root, in Git Bash or any bash 4.4+:

```bash
bash third_party/reimport.sh check    # offline: files match the manifest, nothing extra (such as certs-keys/)
bash third_party/reimport.sh verify   # against upstream: the tag still points at the commit, ids match
```

`verify` uses the clone in `../upstream/conformance-suite` when it exists, otherwise it creates one in
`$HARNESS_RUN_DIR/upstream/conformance-suite` and fetches only the tag it needs. `OIDF_SUITE_CLONE` and
`OIDF_SUITE_URL` override both. `scripts/tests/test-reimport.sh` tests the script against a local stand-in
repository, and `bash scripts/check.sh shell` runs that test.

The same comparison as a one-liner, against the upstream clone (prints nothing when the scripts match):

```bash
diff <(git -C ../upstream/conformance-suite ls-tree --format='%(objectname) %(path)' release-v5.3.1:scripts \
         | grep -E ' (conformance.py|run-test-plan.py|test_plan_parser.py|compare-results.py|requirements.txt)$') \
     <(git ls-tree --format='%(objectname) %(path)' HEAD:third_party/oidf-conformance-suite/scripts)
```

### Moving to a newer suite release

1. `bash third_party/reimport.sh import release-vX.Y.Z` (a tag or a full commit id; branch names are refused so
   every import is pinned). It replaces the folder with the listed files of that release, removes files that are
   no longer listed, rewrites the manifest in `reimport.sh` and prints the rows for the table above.
2. Review `git diff --stat -- third_party/oidf-conformance-suite` and commit that folder alone as
   `import: upstream openid/conformance-suite@<commit> (MIT)`.
3. Update the provenance table above and commit it together with `reimport.sh` in a second commit.
4. Run the harness test suite: a new suite release can change plan names, variants or the export format.

The script copies each file with `git cat-file blob <commit>:<path>`, which writes the stored bytes with no
conversion. `git archive` is not used because it applies upstream `export-subst` and `export-ignore` attributes,
and because with `core.autocrlf=true` (the Git for Windows default) it rewrites LF to CRLF, so the files no
longer match upstream (observed 2026-10-04). The repository's `.gitattributes` (`* -text`) stops git converting
line endings when the files are committed.
