# Submission checklist

Every artefact the problem statement asks for, where it is, who owns it, and its status on 2026-10-22. Deadline
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
| GitHub Actions CI/CD failing the build on regression | `.github/workflows/full-stack-conformance.yml` | done; hosted runs green on 2026-10-14 ([test-report.md](test-report.md#github-actions)) |
| Selective component and plan execution | `--component`, `--modules`, `--template`, `--track` | done |
| Expected failures with written reasons; gate fails on anything else | `conformance/benchmark/`, [benchmark.md](benchmark.md) | done |
| Result diff between runs | `inji-conformance diff`, report `--compare` | done |
| Documentation | `docs/` | done |

## Bonus

| Item | Where | Status |
|---|---|---|
| Parallel execution | `--combined` (parallel by default, `--serial` to compare) | done; with 8 GiB and 12 CPUs the plans run 2.6 times faster in parallel, on a 4 GiB VM serial was faster ([test-report.md](test-report.md#end-to-end-runs)) |
| HAIP readiness track | `--track haip`, [certification-readiness.md](certification-readiness.md) | done |

## Deliverables

| Deliverable | Where | Status |
|---|---|---|
| a. Docker Compose configuration | `docker-compose.yml`, `compose/` | done |
| b. JSON plan templates for issuer and verifier, 1.0 variants | `conformance/plans/` | done; gate variant decided ([conformance/README.md](../conformance/README.md)) |
| c. `run-full-stack-conformance.sh` | repository root | done |
| d. `.github/workflows/full-stack-conformance.yml` | `.github/workflows/` | done; hosted runs green |
| e. Docs: architecture, API automation, handoffs per component, self-certification, troubleshooting | `docs/` | done |
| Test report, test data, Inji findings with evidence | [test-report.md](test-report.md), [test-data.md](test-data.md), [findings/](findings/README.md), `docs/evidence/` | done |
| Demo script, deck outline, final README, report screenshots | `demo/demo.sh`, [demo/video-storyboard.md](demo/video-storyboard.md), [demo/deck-outline.md](demo/deck-outline.md), `README.md`, the reports in `docs/evidence/` | done |
| Repository made public | GitHub settings | done |

## Submission guidelines (MOSIP Decode 2026)

| Item | Where | Status |
|---|---|---|
| Source code | this repository | done |
| Working prototype or demo | `run-full-stack-conformance.sh`, `demo/demo.sh` (TC-20 in [test-report.md](test-report.md)) | done |
| Pitch deck: problem, solution, technology stack, target audience, impact | `PS01-Inji-Conformance-Harness.pptx`, 13 slides, kept with the other artefacts outside the repository; outline in [demo/deck-outline.md](demo/deck-outline.md) | done; the demo-video link on slide 7 is still a placeholder |
| Video demo, 2 to 5 minutes | script in [demo/video-storyboard.md](demo/video-storyboard.md) | team: record and upload |
| Design mockups, wireframes, user flow | [design/report-wireframe.svg](design/report-wireframe.svg), [diagrams/user-flow.svg](diagrams/user-flow.svg), screenshots in `docs/demo/screenshots/` | done |
| Architecture diagram | [diagrams/components.svg](diagrams/components.svg), sequence diagrams in [architecture.md](architecture.md) | done |
| Test data | [test-data.md](test-data.md) | done |
| Test cases and results | [test-cases.md](test-cases.md), [test-report.md](test-report.md) | done |
| Usage and installation instructions | [../README.md](../README.md) (judge's path, quick start), [README.md](README.md) (step by step) | done |
| API documentation | [api.md](api.md) | done |
| Git history with each member's contributions | `git shortlog -s -n` | done |
| College or university ID of each member | uploaded by each member with the submission | team |
| Email to decode@mosip.io: team name, problem statement, links | | team |

## Before submitting

1. Run the manual checks in [manual-test-checklist.md](manual-test-checklist.md) (fresh clone on Linux and macOS,
   report review, video dry run) and record them with
   [manual-test-results-template.md](manual-test-results-template.md).
2. Record the video from [demo/video-storyboard.md](demo/video-storyboard.md), upload it, and put its link on slide 7
   of the deck.
3. Each member uploads a college or university ID; one member emails decode@mosip.io with the team name, the problem
   statement and the links.
