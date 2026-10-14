# Video storyboard

Under 5 minutes. Recorded by the team from the commands below on a machine where
`./run-full-stack-conformance.sh --prepare-only` already ran (the first pull takes several minutes). Timings come from
the runs of 2026-10-14 ([test-report.md](../test-report.md)); long waits are cut.

| # | Time | Shot | Narration |
|---|---|---|---|
| 1 | 0:00-0:20 | Title slide; the problem statement in one line | "Inji Certify and Inji Verify must pass the OpenID Foundation's conformance tests, and today that takes a person clicking through the suite. We automated all of it." |
| 2 | 0:20-0:50 | `docs/diagrams/components.svg` | "One command starts the suite, both Inji components behind TLS, MinIO, and a runner that answers every step where the suite waits for a person: offers, transaction codes, authorization requests, screenshots." |
| 3 | 0:50-1:50 | Terminal: `./run-full-stack-conformance.sh --no-prepare --keep-stack` (the stack stays up for shots 4 and 5); cut the waits; show the handoff lines and the final summary | "Both plans run in parallel. Each line is a handoff: an Inji Certify offer handed to the suite's wallet, its transaction code, an Inji Verify request built exactly as the Inji Verify SDK builds its QR code." |
| 4 | 1:50-2:40 | Browser: `report/summary.html` of the run; open a known gap and its finding; open an Inji Verify REVIEW module and its evidence image | "Every module has one verdict. Known gaps are listed in a benchmark with the reason, the spec clause and a finding for the Inji team. Where the suite needs a screenshot of the verifier's result, we upload Inji Verify's own verdict, read from its API." |
| 5 | 2:40-3:20 | MinIO console (`http://127.0.0.1:18901`), bucket `automationtests`; the api-testrig report. Off camera afterwards: `bash scripts/dc.sh --profile '*' down -v`, or shot 6 stops at the preflight | "The Inji api-testrigs get one TestNG row per conformance module, in their usual report, uploaded to S3 like every other rig run." |
| 6 | 3:20-4:20 | Terminal: `bash demo/demo.sh --regression --runner-only`; show `gate: 3 regressions`, the named modules, the diff | "Now we break Inji Certify's configuration, nothing in its code. The gate fails, names the three modules and the conditions, and the diff shows exactly what changed. In CI this fails the build of the Inji release." |
| 7 | 4:20-4:50 | `docs/findings/README.md`, `docs/certification-readiness.md` | "The runs found ten gaps in Inji, written up as issue drafts, and a ranked list of what stands between Inji and HAIP certification." |
| 8 | 4:50-5:00 | Closing slide: repository link, badge | "Everything is in the repository, one command from a clean clone." |
