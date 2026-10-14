# demo

The live demo and the material for the demo video.

| Path | Purpose |
|---|---|
| `demo.sh` | The demo: a full run of both components; with `--regression`, a passing Inji Certify run, the same with an injected regression (the gate fails and names the modules), and the diff |
| `regression.compose.yml` | Compose override that gives Inji Certify a wrong issuer identifier: a configuration-only regression, nothing in Inji's code changes |
| [../docs/demo/video-storyboard.md](../docs/demo/video-storyboard.md) | Shots, timings and narration of the video (under 5 minutes) |
| [../docs/demo/deck-outline.md](../docs/demo/deck-outline.md) | The slides |
| [../docs/demo/screenshots/](../docs/demo/screenshots/) | The HTML report of the full-stack run, the report and diff of the injected regression (2026-10-14) |

```text
bash demo/demo.sh                              both components, runner, testrig, MinIO; prints the report path
bash demo/demo.sh --regression --runner-only   gate passes, then fails on the injected regression, diff names it
```

Measured result: TC-20 in [docs/test-report.md](../docs/test-report.md#end-to-end-runs).
