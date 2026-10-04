# third_party

Upstream code imported byte for byte. The team does not edit anything here; a newer upstream version is a new
import commit.

Lane: runner. Status on 2026-10-04: empty.

## Planned contents

| Path | Upstream | Licence |
|---|---|---|
| `oidf-conformance-suite/` | `scripts/conformance.py`, `run-test-plan.py`, `test_plan_parser.py`, `compare-results.py`, `requirements.txt` and `LICENSE.txt` of [openid/conformance-suite](https://gitlab.com/openid/conformance-suite) at tag `release-v5.3.1` | MIT |

Not imported: the suite's `scripts/certs-keys/` folder, which holds upstream test private keys. The harness
generates its own keys at run time.

## How to import

1. Extract from the upstream commit, not from a working tree, with line-ending conversion turned off:
   `git -c core.autocrlf=false archive <commit> <path> | tar -x`.
   With `core.autocrlf=true` (the Git for Windows default) `git archive` rewrites LF to CRLF and the files no
   longer match upstream (observed 2026-10-04).
2. Commit the files unchanged, with the upstream licence file, as `import: upstream <repo>@<commit> (<licence>)`.
3. Record the repository, commit and file list in a provenance table in this README.
