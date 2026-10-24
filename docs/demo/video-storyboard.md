# Video storyboard

Target length 4:30, inside the 2 to 5 minutes the submission guidelines ask for. Recorded by the team from the
commands below on a machine where `./run-full-stack-conformance.sh --prepare-only` already ran (the first pull takes
several minutes). Timings come from [test-report.md](../test-report.md); long waits are cut. Slide numbers are those
of the 13-slide deck ([deck-outline.md](deck-outline.md)).

| # | Time | Shot | Narration |
|---|---|---|---|
| 1 | 0:00-0:20 | Slide 1, then slide 2 (the problem) | "We are team Badmosip. Inji Certify and Inji Verify must pass the OpenID Foundation conformance tests. Today a person clicks through the suite's web page, one component at a time, and nothing reaches the Inji test reports or the release pipeline." |
| 2 | 0:20-0:45 | Slide 5 (architecture) | "One Docker Compose project holds the suite, Inji Certify, Inji Verify and MinIO. A runner drives the suite's REST API and answers every step where the suite waits for a person: credential offers, transaction codes, authorization requests and verifier screenshots." |
| 3 | 0:45-1:00 | Terminal: `./run-conformance.sh --help`; stop on the `--component` and `--combined` lines | "One command covers each component, or both together." |
| 4 | 1:00-2:10 | Terminal: `./run-full-stack-conformance.sh --no-prepare --keep-stack`; show the stack starting and a few handoff lines, cut the wait, show the gate lines and `exit code 0` | "Both plans run side by side. Each log line is one answered step. Inji Verify: 11 of 11 modules conform. Inji Certify: all 15 modules complete, 3 conform, 9 are known gaps with written reasons, 3 do not apply. Zero regressions, so the exit code is 0." |
| 5 | 2:10-2:50 | Browser: `run/reports/<run id>/report/summary.html`; open a known gap and its finding, then an Inji Verify module with its evidence image; open the folded "Images" list to show the digests | "Every module gets one verdict. A known gap sits in a benchmark file with its owner, the spec clause and a finding for the Inji team. Where the suite asks for a screenshot of the verifier's result, we upload Inji Verify's own verdict, read from its API. The image digests make the run repeatable." |
| 6 | 2:50-3:20 | Browser: MinIO console `http://127.0.0.1:18901`, bucket `automationtests`, folders `injicertify/` and `injiverify/`; point at `T-15_P-3_S-0_F-0_I-3` and `T-11_P-11` in the file names. Off camera afterwards: `bash scripts/dc.sh --profile '*' down -v`, or shot 7 stops at the preflight | "The results also land in the Inji api-testrigs: one TestNG row per conformance module, in the usual Extent report, uploaded to the same automationtests bucket as every other rig run." |
| 7 | 3:20-4:00 | Terminal: `bash demo/demo.sh --regression --runner-only`; cut to the passing gate, then `gate: 3 regressions` with the module names, the diff and `demo ok` | "Now we break Inji Certify's configuration; its code stays the same. The gate fails with exit code 1 and names the three modules and the reasons. The diff shows which modules changed. In CI this fails the build of an Inji release." |
| 8 | 4:00-4:20 | Slide 8 (measured results), then `docs/findings/README.md` | "From a fresh clone the full stack with both api-testrigs took 728 seconds and peaked at 1.6 gigabytes of memory. The runs found ten gaps in Inji, written up as issue drafts, and a ranked list of what stands between Inji and HAIP certification." |
| 9 | 4:20-4:30 | Slide 13 (team and repository link) | "The GitHub Actions workflow runs the same scripts on every push, every release and every week, and Inji repositories can call it. Everything is one command from a clean clone." |

## Before recording

1. Two Git Bash terminals in the repository root, Docker Desktop with at least 4 GiB (8 GiB is better), a browser,
   and the deck in presentation mode.
2. Stop other Docker stacks. Ports 18443, 18444, 18450, 18451, 18460, 18461, 18900 and 18901 must be free, or the
   preflight exits 3.
3. Pull the images off camera: `./run-full-stack-conformance.sh --prepare-only`.
4. Start clean: `bash scripts/dc.sh --profile '*' down -v`.
5. Keep `run/env.local` off screen; it holds the run's database, keystore and MinIO passwords.
6. Dry-run shots 4 and 7 once and check that shot 7 ends with `demo ok`.

Shorter takes if needed: `./run-conformance.sh --component certify --runner-only` (89 s) and
`--component verify --runner-only` (80 s) in place of shot 4.
