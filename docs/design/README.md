# Design

Design material for the harness's user-facing output. Lane: delivery.

| File | What it shows |
|---|---|
| [`report-wireframe.svg`](report-wireframe.svg) | Layout of the consolidated report `summary.html`, the badge `badge.svg` and the run diff `diff.html`, with numbered notes. Drawn before the report code (2026-10-04); the implementation in `runner/src/inji_conformance/report/` follows it. |

Review comments from the team go into a pull request or an issue that names the note number in the wireframe.

## Report design rules

These rules hold for `summary.html`, `diff.html` and `badge.svg`, and the report tests check the ones a test can
check (`runner/tests/report/`).

- One self-contained file per page: styles, script and icons are inline, nothing is fetched from the network, so
  the page opens offline, from a CI artifact and from a zip.
- Status is never colour alone. Every verdict is an icon with a distinct shape plus the word:

  | Verdict in `results.json` | Shown as | Icon shape |
  |---|---|---|
  | `conforms` | Conforms | circle with a check mark |
  | `known_gap` | Known gap | triangle with an exclamation mark |
  | `regression` | Regression | circle with a cross |
  | `not_applicable` | Not applicable | circle with a bar |
  | `stale_benchmark` | Stale benchmark | rounded square with a clock hand |

- Contrast meets WCAG 2.1 AA (4.5:1 for text) in both themes. The colours are CSS custom properties with a light
  set and a dark set; the page follows the system setting, and the theme button switches between automatic, light
  and dark (the choice is kept in the browser's local storage when the browser allows it).
- The module table works with a keyboard and a screen reader: native `select`, checkbox and search inputs with
  labels, `details` elements for the expandable rows, a live region that announces how many rows are shown.
- Without script, every row is visible and every detail can still be opened; the filters only hide rows.
- Two links per module: the live suite log (works while the suite runs) and the extracted HTML export inside the
  run folder (works after the containers are gone).
- The report never reads or embeds the rendered suite configuration, which holds private keys. Free text taken from
  results files passes through a filter that removes PEM private keys and private JSON Web Key members.
