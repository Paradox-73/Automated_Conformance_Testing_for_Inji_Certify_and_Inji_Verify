# Submission checklist

Every artefact the problem statement asks for, where it is, who owns it, and its status on 2026-10-14. Deadline
2026-10-26 23:59 IST.

## Mandatory tasks

| Item | Where | Owner | Status |
|---|---|---|---|
| Docker Compose: Inji Certify, Inji Verify, conformance suite (server, MongoDB, nginx) | `docker-compose.yml`, `compose/` | platform | done; full stack peaks at 1.6 GiB |
| Programmatic runner (create, configure, run, poll, fetch results) for both plans, on `run-test-plan.py` | `runner/` | runner | done; both plans live |
| `OpenIDConformanceTest` in the Inji Certify and Inji Verify api-testrigs, `env.endpoint`, TestNG pass/fail/skip in the report, MinIO `automationtests`, gated by a benchmark | `testrigs/` | testrig | done; both rigs upload |
| Combined run with one consolidated report and badge | `run-conformance.sh --combined`, `inji-conformance report` | runner, delivery | done |
| One command per component and combined | `run-conformance.sh --component certify\|verify\|--combined` | platform | done |

## Good-to-have tasks

| Item | Where | Status |
|---|---|---|
| GitHub Actions CI/CD failing the build on regression | `.github/workflows/full-stack-conformance.yml` | written, passes actionlint; the first hosted run was refused by GitHub for the owner account's billing ([ci.md](ci.md)) |
| Selective component and plan execution | `--component`, `--modules`, `--template`, `--track` | done |
| Expected failures with written reasons; gate fails on anything else | `conformance/benchmark/`, [benchmark.md](benchmark.md) | done |
| Result diff between runs | `inji-conformance diff`, report `--compare` | done |
| Documentation | `docs/` | done |

## Bonus

| Item | Where | Status |
|---|---|---|
| Parallel execution | `--combined` (parallel by default, `--serial` to compare) | done; on a 4 GiB VM serial was faster ([test-report.md](test-report.md)) |
| HAIP readiness track | `--track haip`, [certification-readiness.md](certification-readiness.md) | done |

## Deliverables

| Deliverable | Where | Status |
|---|---|---|
| a. Docker Compose configuration | `docker-compose.yml`, `compose/` | done |
| b. JSON plan templates for issuer and verifier, 1.0 variants | `conformance/plans/` | done; gate variant decided ([conformance/README.md](../conformance/README.md)) |
| c. `run-full-stack-conformance.sh` | repository root | done |
| d. `.github/workflows/full-stack-conformance.yml` | `.github/workflows/` | done; hosted run pending billing |
| e. Docs: architecture, API automation, handoffs per component, self-certification, troubleshooting | `docs/` | done |
| Test report, test data, Inji findings with evidence | [test-report.md](test-report.md), [test-data.md](test-data.md), [findings/](findings/README.md), `docs/evidence/` | done |
| Demo script, deck outline, final README, report screenshots | `demo/demo.sh`, [demo/video-storyboard.md](demo/video-storyboard.md), [demo/deck-outline.md](demo/deck-outline.md), `README.md`, the reports in `docs/evidence/` | done |
| Video and slides | | team, after this branch is merged |
| Repository made public | GitHub settings | Kanav |

## Before submitting

1. Merge `nikunj/ps01-finish` into `main`.
2. Fix the GitHub billing (or make the repository public) and push once, so the workflow runs on hosted runners;
   put the run URL in [test-report.md](test-report.md) and [ci.md](ci.md).
3. Run [the fresh-clone check](test-report.md#fresh-clone-and-newcomer-walkthrough) once more on `main`.
4. Record the video from [demo/video-storyboard.md](demo/video-storyboard.md) and build the slides from
   [demo/deck-outline.md](demo/deck-outline.md).
