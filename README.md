# Inji conformance harness

![conformance badge of the run of 2026-10-14](docs/evidence/2026-10-13-20261013T222910Z-f08c5b/report/badge.svg)

Automated OpenID conformance testing of [Inji Certify](https://github.com/inji/inji-certify) (credential issuer)
and [Inji Verify](https://github.com/inji/inji-verify) (verifier) against the
[OpenID Foundation conformance suite](https://gitlab.com/openid/conformance-suite), with no person in the loop.
MOSIP Decode 2026, problem statement 01, team Badmosip.

The badge is from the full-stack run of 2026-10-14 (run `20261013T222910Z-f08c5b`, both components with the
api-testrigs; [evidence](docs/evidence/2026-10-13-20261013T222910Z-f08c5b/)).

## Quick start

Docker with Compose v2 (4 GiB for Docker), bash 4.4+, git. From a clean clone:

<!-- run 2026-10-14 -->
```bash
./run-full-stack-conformance.sh --prepare-only
./run-full-stack-conformance.sh --no-prepare
```

The second command starts the stack, runs the OpenID4VCI 1.0 issuer plan against Inji Certify and the OpenID4VP 1.0
verifier plan against Inji Verify in parallel, adds the results to both Inji api-testrigs and uploads their reports to
MinIO, writes the HTML report, stops the stack, and exits with the gate's code (0 on 2026-10-14, in 250 s). One
component: `./run-conformance.sh --component certify|verify`; `--help` lists every option. Full guide:
[docs/README.md](docs/README.md).

## What you get

| Output | Where |
|---|---|
| One verdict per suite module: conforms, known gap (listed in the benchmark with reason and finding), regression, not applicable, stale benchmark | `run/reports/<run id>/<component>/results.json` |
| Consolidated HTML report with the suite's logs and HTML export linked, badge, Markdown summary | `run/reports/<run id>/report/` |
| Run manifest: git commit, image digests, wall time per plan | `run/reports/<run id>/manifest.json` |
| TestNG rows `TC_OIDF_CERTIFY_nn` and `TC_OIDF_VERIFY_nn` in the api-testrigs' `EmailableReport`, uploaded to S3 (MinIO bucket `automationtests`) | `run/reports/<run id>/testrig/` |
| Exit code for CI: 0 passed, 1 regression or stale benchmark entry, 2 configuration, 3 environment (outage, crash, no modules collected), 4 timeout, 5 harness bug | [docs/reference/cli.md](docs/reference/cli.md#exit-codes) |
| Run diff: which modules changed | `inji-conformance diff` |
| GitHub Actions workflow for pushes, releases, a weekly run and Inji release pipelines | `.github/workflows/full-stack-conformance.yml` |

Results on 2026-10-14 ([test report](docs/test-report.md)): Inji Verify 11 of 11 modules conform; Inji Certify all
15 modules complete with 3 passed, 9 known gaps and 3 not applicable; ten Inji gaps written up as
[issue drafts](docs/findings/README.md); HAIP readiness in [docs/certification-readiness.md](docs/certification-readiness.md).

## Documentation

| Document | For |
|---|---|
| [docs/README.md](docs/README.md) | install and run, step by step |
| [docs/architecture.md](docs/architecture.md) | components, network, sequence diagrams, design decisions |
| [docs/handoffs.md](docs/handoffs.md), [docs/api-automation.md](docs/api-automation.md) | how the suite's waiting steps are answered; every API call |
| [docs/benchmark.md](docs/benchmark.md) | expected failures, verdicts and the gate |
| [docs/testrig-integration.md](docs/testrig-integration.md) | the TestNG rows in the Inji api-testrigs and the S3 upload |
| [docs/ci.md](docs/ci.md) | the GitHub Actions workflow and the local CI script |
| [docs/configuration.md](docs/configuration.md), [docs/troubleshooting.md](docs/troubleshooting.md) | settings, images, ports; symptom, cause, fix |
| [docs/self-certification.md](docs/self-certification.md), [docs/certification-readiness.md](docs/certification-readiness.md) | the path to OpenID certification |
| [docs/test-report.md](docs/test-report.md), [docs/test-cases.md](docs/test-cases.md), [docs/test-data.md](docs/test-data.md) | what was run and measured |
| [docs/findings/](docs/findings/README.md), [docs/suite-limitations.md](docs/suite-limitations.md) | Inji gaps found; suite-side limitations |
| [docs/reference/cli.md](docs/reference/cli.md), [docs/reference/results-schema.md](docs/reference/results-schema.md) | commands; results and manifest files |
| [demo/](demo/README.md), [docs/demo/](docs/demo/video-storyboard.md) | demo script, video storyboard, deck outline |
| [docs/STATUS.md](docs/STATUS.md), [CONTRIBUTING.md](CONTRIBUTING.md), [docs/submission-checklist.md](docs/submission-checklist.md) | tasks and their status, how to contribute, the submission |

## Repository checks

<!-- run 2026-10-14 -->
```bash
bash scripts/check.sh all
```

Line endings, secrets, shellcheck and shell tests, runner (ruff, pytest), testrigs (Maven), workflows (actionlint)
and documentation; one `PASS`, `FAIL` or `SKIP` line each, exit 1 on any failure.

## Licences and imported code

Team code is MIT ([LICENSE](LICENSE)). Imported code keeps its licence and is imported unchanged in its own commit:

| Folder | Source | Licence |
|---|---|---|
| `third_party/oidf-conformance-suite/` | the suite's `run-test-plan.py`, `conformance.py`, `test_plan_parser.py`, release-v5.3.1 | MIT ([third_party/README.md](third_party/README.md)) |
| `testrigs/inji-certify-api-test/`, `testrigs/inji-verify-api-test/` | Inji api-testrigs, `inji-certify@203b143`, `inji-verify@6a6ab3b` | Apache-2.0 ([testrigs/README.md](testrigs/README.md)) |
| `compose/certify/`, `compose/verify/` | Inji compose configuration and database scripts | Apache-2.0 |
| `compose/suite/` | the suite's nginx configuration | MIT |

The Inji labels follow each repository's root `LICENSE` at the imported `release-1.0.x` commit, which is Apache-2.0
and is kept byte for byte next to the imported files. Some upstream files carry an MPL-2.0 header or text
(`compose/certify/config/certify-default.properties`, `testrigs/inji-certify-api-test/README.md`), and both
repositories' `master` branches now have an MPL-2.0 `LICENSE`; those files are kept as upstream wrote them. Every
upstream file the team changed carries a change notice at its top: the two rig `pom.xml` files,
`compose/certify/config/certify-default.properties` and `compose/verify/init.sql`.

Images run unmodified: the conformance suite (MIT), Inji Certify and Inji Verify (Apache-2.0 at the imported commits,
MPL-2.0 on their `master` branches; either allows running them unmodified), PostgreSQL, MongoDB, nginx, MinIO
(AGPL-3.0, run as a separate program), Temurin, Python.
