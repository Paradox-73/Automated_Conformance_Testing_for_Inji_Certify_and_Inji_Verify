# CI/CD

`.github/workflows/full-stack-conformance.yml` runs the harness on GitHub Actions; `scripts/ci-local.sh` runs the
same steps on a developer machine.

## Triggers

| Event | Jobs |
|---|---|
| push, pull request | checks, conformance (certify and verify), combined |
| release published, weekly schedule (Monday 03:17 UTC), `workflow_dispatch` | the same, plus full-stack |
| `workflow_call` from an Inji repository | the same as dispatch, with that repository's image |

`workflow_dispatch` and `workflow_call` take `component` (both, certify, verify), `track` (gate, haip), `strict`
(stale benchmark entries fail; off adds `--allow-stale`), `certify_image` and `verify_image` (image overrides, for
example a new digest). Runs of one ref cancel each other (`concurrency`).

## Jobs

| Job | Does | Fails when |
|---|---|---|
| `checks` | `bash scripts/check.sh all` with `CI=true` (a missing tool fails) | any check fails |
| `conformance` (matrix certify, verify) | image cache (`docker save`/`load`, keyed on the image list), `./run-full-stack-conformance.sh --prepare-only`, `./run-conformance.sh --component <c>` (runner, testrig, MinIO upload, report), `summary.md` into the job summary, artifact `conformance-<c>` (`suite-scripts/` and `exports/` removed first: the suite's exports, the extracted HTML pages included, hold the run's private keys) | the component's gate fails |
| `combined` | consolidated report and badge of both artifacts (`inji-conformance report --combined`), diff against the artifacts of the last successful run on `main` | no component results |
| `full-stack` | `./run-full-stack-conformance.sh` from scratch | the gate fails |

Artifacts are uploaded with `if: always()`, so a failed gate still leaves its report.

## Inji release pipelines

[.github/examples/inji-release-caller.yml](../.github/examples/inji-release-caller.yml) is the workflow an Inji
repository adds: after its release build it calls this workflow (`uses: ...full-stack-conformance.yml@main`) with the
image it just pushed, so a release that regresses fails in the Inji repository's own checks.

## Locally

<!-- run 2026-10-14 -->
```bash
bash scripts/ci-local.sh verify
```

Writes `$HARNESS_RUN_DIR/ci-local/conformance-verify/` (the artifact layout) and `summary-verify.md`; exit code of
the first failing step. Result on 2026-10-14: see [test-report.md](test-report.md).

## Status of the real runs

- `actionlint` 1.7.12 on the workflow and the example: no output, exit 0 (2026-10-14).
- The first push of the workflow (2026-10-14, run
  [38476075682](https://github.com/Paradox-73/Automated_Conformance_Testing_for_Inji_Certify_and_Inji_Verify/actions/runs/38476075682))
  was refused by GitHub before any job started: "The job was not started because recent account payments have
  failed or your spending limit needs to be increased". The repository is private, so hosted runners bill the
  owner's account. Fixing the billing or making the repository public (public repositories run on free hosted
  runners with 4 vCPU and 16 GB) lets the next push run it; nothing in the workflow has to change.
