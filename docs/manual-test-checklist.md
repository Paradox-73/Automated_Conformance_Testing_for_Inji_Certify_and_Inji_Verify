# Manual test checklist

These are the checks that need a person: a judgement of how something looks or reads, a machine the automated runs
do not cover, or an account. Everything else is covered by `bash scripts/check.sh all` and the GitHub Actions
workflow.

Record each step in a copy of [manual-test-results-template.md](manual-test-results-template.md). Name every file
you attach `<step id>_<your name>_<os>_<what>.<ext>`, for example `MT-03_asha_windows11_terminal.png`. Send the
filled template and the files to the person who merges the branch.

## Before you start

- Use a machine with Docker running and at least 4 GiB of memory for Docker. Stop other Docker stacks that use
  ports 18443, 18444, 18450, 18451, 18460, 18461, 18900 or 18901, or the preflight stops the run with exit 3.
- Note whether the images are already on the machine: run `docker image ls | wc -l` before the first step. A first
  run pulls about 3 GB of images, so its time is not comparable with a run on a machine that has them.
- Do not show or attach `run/env.local`. It holds the generated database, keystore and MinIO passwords.

## Expected result of a full run

The steps below refer to this result. It is the result of every full run since 2026-10-13.

| Component | Modules | Conforms | Known gap | Not applicable | Regression | Exit code |
|---|---:|---:|---:|---:|---:|---:|
| certify | 15 | 3 | 9 | 3 | 0 | 0 |
| verify | 11 | 11 | 0 | 0 | 0 | 0 |

The api-testrig reports end in `T-15_P-3_S-0_F-0_I-3_KI-9.html` (Inji Certify) and
`T-11_P-11_S-0_F-0_I-0_KI-0.html` (Inji Verify).

## MT-01 to MT-03: fresh clone and one-command run, per operating system

Do these on three machines: MT-01 on Linux, MT-02 on macOS, MT-03 on Windows 11 with Git Bash. The workflow's
full-stack job already runs `./run-full-stack-conformance.sh` from scratch on GitHub's Linux runner (runs 38610806188
and 39225469292 in [test-report.md](test-report.md#github-actions)); MT-01 adds a person's own Linux machine and clone.

1. Clone into an empty folder with
   `git clone -c core.longpaths=true https://github.com/Paradox-73/Automated_Conformance_Testing_for_Inji_Certify_and_Inji_Verify.git harness`,
   then `cd harness`.
2. Run `time ./run-full-stack-conformance.sh --prepare-only` and note the time.
3. Run `time ./run-full-stack-conformance.sh --no-prepare` and note the time.
4. Check the last lines. They must say `exit code 0` and list `results.json` for both components, the report and
   the badge.
5. Compare the module counts in the output with the table in
   [Expected result of a full run](#expected-result-of-a-full-run).
6. Take a screenshot of the last 30 lines of the terminal.

Record: the operating system and version, the CPU (Intel, AMD or Apple silicon), the memory given to Docker, both
times, the exit code, and whether the images were already on the machine. On Apple silicon, Docker runs some images
for x86-64 through emulation; write down if any step was much slower than on the other machines.

Pass: both commands exit 0 and the counts match the table.

## MT-04: one component at a time

1. Run `./run-conformance.sh --component certify` and note the time and the exit code.
2. Run `./run-conformance.sh --component verify` and note the time and the exit code.

Pass: both exit 0, and each run folder holds only its own component's `results.json` and report.

## MT-05: HTML report review

1. Run `./run-conformance.sh --combined --keep-stack`. The stack keeps running, so the links to the suite's logs
   work.
2. Open `run/reports/<run id>/report/summary.html` in a browser. The command prints the full path.
3. Check that every module has one verdict, and that the totals at the top match the table above.
4. Open one known-gap row. Check that it names the failing condition, the benchmark entry and a finding in
   `docs/findings/`.
5. Open one suite log link and one HTML export link. Both must open the matching module.
6. Open an Inji Verify module that shows an evidence image. The image must show Inji Verify's result.
7. Open `badge.svg`.
8. Stop the stack: `bash scripts/dc.sh --profile '*' down -v`.

Record: a screenshot of the top of the report, one of an open known-gap row, and every link that did not open. Write
down anything a reader who has never seen the project would not understand.

Pass: no broken link while the stack runs, and the totals match.

## MT-06: api-testrig report and MinIO upload

1. Run `./run-conformance.sh --combined --keep-stack`.
2. Open the EmailableReport HTML files in `run/reports/<run id>/testrig/certify/` and
   `run/reports/<run id>/testrig/verify/`.
3. Check the rows `TC_OIDF_CERTIFY_01` to `TC_OIDF_CERTIFY_15` and `TC_OIDF_VERIFY_01` to `TC_OIDF_VERIFY_11`.
   A known gap shows as a Known Issue, not applicable as Ignored, conforms as Passed.
4. Open the MinIO console at `http://127.0.0.1:18901`. The user is `harness`. The password is the
   `MINIO_ROOT_PASSWORD` line of `run/env.local`; type it, do not screenshot it.
5. Open the bucket `automationtests`. Both reports must be in `injicertify/` and `injiverify/`.
6. Stop the stack: `bash scripts/dc.sh --profile '*' down -v`.

Record: a screenshot of each EmailableReport and one of the bucket listing.

Pass: the row counts match the file names in [Expected result of a full run](#expected-result-of-a-full-run), and
both files are in the bucket.

## MT-07: regression demo

1. Run `bash demo/demo.sh --regression --runner-only`.
2. Check that the second Inji Certify run prints `gate: 3 regressions` and names the three modules.
3. Check that the diff names the same modules.
4. Check that the demo ends with exit 0, which means the gate failed as intended.

Record: a screenshot of the failing gate and of the diff.

Pass: the gate fails with exit 1 inside the demo, names three modules, and the demo exits 0.

## MT-08: video dry run

The video is a mandatory submission item, 2 to 5 minutes. The script is
[docs/demo/video-storyboard.md](demo/video-storyboard.md).

1. Run `./run-full-stack-conformance.sh --prepare-only` first, so no shot waits for a download.
2. Walk through the eight shots with a stopwatch. Note the time of each shot.
3. Record a 30-second test clip of the terminal and of the report at the resolution you plan to use. Check that the
   text is readable when the clip plays at full screen on a laptop.
4. Check every frame for `run/env.local`, MinIO passwords, tokens and personal folder names.

Record: the time per shot, the total, the test clip file name, and any shot that needs a change in the storyboard.

Pass: the total is under 5 minutes, the text is readable, and no secret is visible.

## MT-09: slide deck review

The deck is a mandatory submission item. The outline is [docs/demo/deck-outline.md](demo/deck-outline.md).

1. Check that the deck covers the problem, the solution, the technology stack, the users and the impact, as the
   submission guidelines ask.
2. Check every number in the deck against [docs/test-report.md](test-report.md).

Record: the deck file name and every number that did not match.

Pass: every number matches the test report.

## MT-10: GitHub Actions after the merge

1. Open the repository's **Actions** tab and the latest `full-stack-conformance` run on `main`.
2. Check that the jobs `checks`, `conformance (certify)`, `conformance (verify)` and `combined` are green.
3. Open the run summary. It must show the consolidated report table.
4. Download the `combined-report` artifact and open `summary.html`.

Record: the run URL and a screenshot of the run summary.

Pass: every job that ran is green and the artifact opens.

## MT-11: README read-through

1. Ask someone who has not worked on the project to follow the README quick start without help.
2. Write down every place where they stopped, asked a question, or guessed.

Record: the list of questions, with the README line each one refers to.

Pass: no step needed help.

## MT-12: release hook in an Inji repository (optional)

This needs a fork of inji-certify or inji-verify in a GitHub account the tester owns.

1. Follow the five steps in [docs/ci.md, Inji release pipelines](ci.md#inji-release-pipelines).
2. Start the workflow with `workflow_dispatch` and a known image digest.
3. Check that the run's jobs check out this harness (the `actions/checkout` step names the harness repository) and
   that the gate result is in the summary.

Record: the fork URL, the run URL, and the result.

Pass: the called jobs check out the harness and the gate runs against the given image.
