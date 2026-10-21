# Accessibility of the report

The report is two self-contained HTML pages: `summary.html` (one run) and `diff.html` (two runs compared). Both are
rendered from the templates in `runner/src/inji_conformance/report/templates/` and the style sheet and script in
`runner/src/inji_conformance/report/assets/`. This page records what we checked, with which tools, and what we did not
check. Date of the checks: 2026-10-21.

## Result

Automated check with axe-core 4.14.0: 0 violations and 0 items needing manual review on `summary.html` and `diff.html`,
in the light and the dark theme, with scripts on. Rules run: WCAG 2.0 A and AA, WCAG 2.1 A and AA, WCAG 2.2 AA, and the
axe best-practice rules.

## What we checked

| Check | How | Result |
|---|---|---|
| Rule violations | axe-core 4.14.0 in Chrome 155.0.8059.85, driven with Playwright (`playwright-core`). Pages: `summary.html` of the fixture run with a comparison box, `summary.html` of the other fixture run, `diff.html`, and the real `diff.html` of the 2026-10-13 run in `docs/evidence/`. Every module's details were expanded first. Run once for each system colour scheme (light, dark) and for each setting of the theme button (auto, light, dark). | 0 violations |
| Keyboard | With Playwright, pressed Tab through each page and compared the elements reached with all links, buttons, inputs and selects that are on screen: 62 of 62 on `summary.html`, 1 of 1 on `diff.html`. Read the computed outline of each focused element. | all reachable; every one has a 3 px outline (`:focus-visible` in `report.css`) |
| Colour contrast | axe-core `color-contrast` rule in both themes, plus `runner/tests/report/test_report_html.py`, which reads the colour tokens from `report.css` and requires 4.5:1 for every text colour on the page and card backgrounds. | passes |
| Colour is never the only signal | Each verdict and gate is an icon of its own shape followed by the verdict as a word. The icon's inner mark uses the page background colour, so it keeps the same contrast as the text beside it in both themes. | by design; checked in the markup |
| Text alternatives | The one image (the badge) has `alt="Badge of this run"`. Icons are `aria-hidden` because the verdict word beside them is read. Links to a module's log or export carry the module name in visually hidden text. | passes |
| Structure | `lang="en"`, one `h1`, no skipped heading level, every table has a caption and `scope` on every header cell, a skip link to the module table, a live region for the filter count. | passes |
| Without script | Details, filters and the theme button depend on script. With script off, every row and detail stays visible and the controls stay hidden. | page is complete |

## Problems found and fixed

axe-core reported these on the pages rendered before the fix. All were fixed in the templates and the style sheet, not
in the dated evidence files.

| Rule | Count on `summary.html` | Cause | Fix |
|---|---|---|---|
| `heading-order` | 1 per page | Module details used `h4` directly under the `h2` "Modules". | The detail headings are `h3`. |
| `color-contrast` (needs review) | 24 per page, one per module toggle | The open/closed arrow was a text character, which axe cannot measure. | The arrow is drawn with CSS borders, so it holds no text. |

One more change came from reading the icons: their white inner marks had low contrast on the lighter dark-theme colours
(for example white on `#3fb950`). They now use the page background colour.

## Repeating the check

1. Render the pages from the fixture runs with the test suite: `cd runner && python -m pytest tests/report`. The
   invariants that a plain HTML parse can check (language, one `h1`, no skipped heading level, `scope` on every `th`, an
   `alt` on every image, a name on every link and button, a caption on every table, the skip link) are in
   `runner/tests/report/test_report_accessibility.py` and run with the rest of the suite.
2. For the full axe-core run, install `axe-core` and `playwright-core` with npm, open each page in Chrome, add
   `axe.min.js` to the page and call `axe.run(document)`.

## What we did not check

- A screen-reader pass by a person (NVDA, JAWS or VoiceOver). axe-core cannot judge reading order or whether the
  announcements make sense.
- Browsers other than Chrome, and zoom to 400 percent or narrow phone widths. The layout has a rule for narrow screens
  that we did not measure.
- Reduced-motion and high-contrast operating-system modes. The only animation is a 0.15 s turn of the toggle arrow.
- The pages other tools make: the suite's own HTML export and the api-testrigs' `EmailableReport` are not ours.
