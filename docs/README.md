# docs

Documentation of the harness. Status on 2026-10-04: no documents yet. This file will become the step-by-step
install and run guide for Windows, Linux and macOS.

Lane: delivery.

## Planned documents

| Document | Reader | Contents |
|---|---|---|
| `architecture.md` | judge, maintainer | Components, network, sequence diagrams, design decisions |
| `api-automation.md` | maintainer | Every suite REST call and Inji API the runner uses, and how `run-test-plan.py` is reused |
| `handoffs.md` | maintainer, Inji team | What the suite waits for in each test and how the harness answers it |
| `testrig-integration.md` | Inji QA team | TestNG bridge, report mapping, S3 upload, upstream patches |
| `benchmark.md` | release manager | Expected-failure file format and gate rules |
| `self-certification.md` | Inji team | How to submit results for OpenID certification |
| `troubleshooting.md` | user | Symptom, cause, fix |
| `ci.md`, `configuration.md`, `reference/` | maintainer, integrator | Workflow jobs, settings, command reference, results file fields |

## What `bash scripts/check.sh docs` expects

Once `docs/tools/check_docs.py` exists, the check runs it from the repository root with the runner's Python
(`$HARNESS_RUN_DIR/venv`) when present, otherwise the system Python 3.12+. Exit status 0 means PASS; anything else
is FAIL. The script prints its own findings.
