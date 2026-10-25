"""summary.html and diff.html: snapshots of the fixture runs, and the rules of docs/design/README.md that a test
can check (self-contained, status as word plus icon, contrast, no suite configuration, safe links)."""

from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from importlib import resources
from pathlib import Path

import pytest

from inji_conformance import __version__
from inji_conformance.model import Verdict
from inji_conformance.report import html
from inji_conformance.report.diff import diff_runs
from inji_conformance.report.runs import load_run

from .conftest import SNAPSHOTS, UPDATE_ENV
from .contrast import contrast_ratio

BEGIN = "-----BEGIN " + "PRIVATE KEY-----"
END = "-----END " + "PRIVATE KEY-----"
KEY_BODY = "MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg" * 2


def _summary(run_dir: Path, out: Path, compare: Path | None = None) -> str:
    run = load_run(run_dir)
    diff = diff_runs(load_run(compare), run) if compare else None
    return html.render_summary(run, out, html.generated_now(f"inji-conformance {__version__}"), diff)


def _check_snapshot(name: str, text: str) -> None:
    """Compare with snapshots/<name>; the runner version is normalised so a version bump alone needs no update."""
    text = text.replace(f"inji-conformance {__version__}", "inji-conformance VERSION")
    path = SNAPSHOTS / name
    if os.environ.get(UPDATE_ENV) == "1" or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        if os.environ.get(UPDATE_ENV) != "1":
            pytest.fail(f"snapshot {name} did not exist and was written; review it and run the tests again")
    assert text == path.read_text(encoding="utf-8"), f"{name} differs from the snapshot; set {UPDATE_ENV}=1 to update"


class _Collector(HTMLParser):
    """Collects the attributes a test needs: ids, hrefs, srcs and the tags used."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.hrefs: list[str] = []
        self.srcs: list[str] = []
        self.tags: set[str] = set()

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        values = dict(attrs)
        if "id" in values:
            self.ids.append(values["id"])
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"])
        if values.get("src"):
            self.srcs.append(values["src"])


def _collect(text: str) -> _Collector:
    collector = _Collector()
    collector.feed(text)
    return collector


# ---------------------------------------------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------------------------------------------


def test_summary_snapshot(copied_runs, tmp_path, fixed_time):
    page = _summary(copied_runs / "run-a", tmp_path / "out", copied_runs / "run-b")
    _check_snapshot("summary.html", page)


def test_diff_snapshot(copied_runs, fixed_time):
    result = diff_runs(load_run(copied_runs / "run-a"), load_run(copied_runs / "run-b"))
    _check_snapshot("diff.html", html.render_diff(result, html.generated_now(f"inji-conformance {__version__}")))


def test_rendering_is_deterministic(run_a, tmp_path, fixed_time):
    assert _summary(run_a, tmp_path) == _summary(run_a, tmp_path)


# ---------------------------------------------------------------------------------------------------------------
# Content rules
# ---------------------------------------------------------------------------------------------------------------


def test_page_is_self_contained(run_a, tmp_path):
    page = _summary(run_a, tmp_path)
    found = _collect(page)
    assert "link" not in found.tags
    assert found.srcs == ["badge.svg"]  # the badge written next to the page; nothing from the network
    assert "<style>" in page and "<script>" in page and "@import" not in page


def test_every_module_has_a_row_with_word_and_icon(run_a, tmp_path):
    page = _summary(run_a, tmp_path)
    run = load_run(run_a)
    for item, module in run.modules():
        assert f'id="m-{item.component.value}-{module.name}"' in page
    for verdict, style in html.VERDICTS.items():
        assert f'<use href="#i-{style.css}"/></svg>{style.label}</span>' in page, verdict
        assert f'<symbol id="i-{style.css}"' in page


def test_regressions_sort_first(run_b, tmp_path):
    page = _summary(run_b, tmp_path)
    rows = re.findall(r'<tbody class="module" id="[^"]+" data-component="[^"]+" data-verdict="([a-z_]+)"', page)
    assert rows[:2] == [Verdict.REGRESSION.value] * 2
    assert len(rows) == 25


def test_ids_are_unique(run_a, run_b, tmp_path):
    ids = _collect(_summary(run_a, tmp_path, run_b)).ids
    assert len(ids) == len(set(ids))


def test_links_to_exports_are_relative_and_exist(copied_runs, tmp_path):
    out = tmp_path / "out"
    found = _collect(_summary(copied_runs / "run-a", out))
    exports = [href for href in found.hrefs if href.endswith(".html") and "exports/" in href]
    assert len(exports) == 4
    for href in exports:
        assert not Path(href).is_absolute() and (out / href).resolve().is_file()


def test_live_suite_log_is_text_not_a_link(run_a, tmp_path):
    # The suite's log page is gone once the stack is torn down, so a link would always be dead in a saved report.
    page = _summary(run_a, tmp_path)
    assert not [href for href in _collect(page).hrefs if "log-detail.html" in href]
    shown = re.findall(r"Suite log, only valid while the suite runs: <code>(https://[^<]+)</code>", page)
    assert len(shown) == 26 and all(url.startswith("https://localhost.emobix.co.uk:18443/") for url in shown)


def test_missing_exports_are_text_not_links(copied_runs, tmp_path):
    # As in a copy of the run folder that left out exports/ (the GitHub Pages evidence keeps only the report).
    run_dir = copied_runs / "run-a"
    before = _summary(run_dir, tmp_path / "out").count("HTML export not in this folder")
    for page in (run_dir / "verify" / "exports").iterdir():
        page.unlink()
    page = _summary(run_dir, tmp_path / "out")
    exports = [href for href in _collect(page).hrefs if "exports/" in href]
    assert len(exports) == 2 and all("certify/exports/" in href for href in exports)
    assert page.count("HTML export not in this folder") == before + 2


def test_no_link_without_a_relative_path(run_a, tmp_path, monkeypatch):
    # Another drive on Windows: an absolute file: link would break as soon as the folder is copied.
    def no_relative_path(*_args):
        raise ValueError("path is on mount 'E:', start on mount 'C:'")

    monkeypatch.setattr(html.os.path, "relpath", no_relative_path)
    hrefs = _collect(_summary(run_a, tmp_path)).hrefs
    assert not [href for href in hrefs if "exports/" in href or href.startswith("file:")]


def test_workaround_is_shown_next_to_the_gate(run_a, tmp_path):
    page = _summary(run_a, tmp_path)
    assert 'gate-passed gate">' in page and "Gate passed with 1 workaround</span>" in page
    section = page[page.index('<section aria-labelledby="workarounds-heading"') :]
    assert page.index("workarounds-heading") < page.index('id="run-heading"')  # first thing under the header
    assert "Workarounds applied: 1" in section
    assert "<code>docs/findings/certify-as-metadata-authorization-endpoint.md</code>" in section
    assert "<code>CERTIFY_AS_METADATA=as-is</code>" in section


def test_no_workaround_section_without_workarounds(run_b, tmp_path):
    page = _summary(run_b, tmp_path)
    assert "workarounds-heading" not in page and "Gate failed</span>" in page and "with 0" not in page


def test_never_shows_the_suite_configuration(run_a, tmp_path):
    page = _summary(run_a, tmp_path)
    assert "config/" not in page and "verify.oid4vp-1final-verifier.json" not in page


def test_key_material_in_results_text_is_redacted(copied_runs, edit_json, tmp_path):
    results = copied_runs / "run-a" / "verify" / "results.json"

    def leak(data):
        module = next(m for m in data["modules"] if m["failures"])
        module["failures"][0]["message"] = f"suite quoted {BEGIN}\n{KEY_BODY}\n{END}"
        module["handoffs"][0]["detail"] = "POST client" + "_secret=hunter2hunter2"

    edit_json(results, leak)
    page = _summary(copied_runs / "run-a", tmp_path)
    assert KEY_BODY not in page and "hunter2" not in page
    assert "[redacted]" in page


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://localhost.emobix.co.uk:18443/log-detail.html?log=x", True),
        ("http://suite:8080/log-detail.html", True),
        ("javascript:alert(1)", False),
        ("data:text/html,hi", False),
        ("https:///no-host", False),
        ("", False),
        (None, False),
    ],
)
def test_only_http_links_are_linked(value, expected):
    # The schema already rejects other suite_log values; this guard also covers issue URLs and future fields.
    assert (html.safe_url(value) is not None) is expected


def test_html_in_results_text_is_escaped(copied_runs, edit_json, tmp_path):
    results = copied_runs / "run-a" / "verify" / "results.json"
    edit_json(results, lambda data: data["modules"][0].update(description="<script>alert(1)</script>"))
    page = _summary(copied_runs / "run-a", tmp_path)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_filters_and_theme_button_are_hidden_without_script(run_a, tmp_path):
    page = _summary(run_a, tmp_path)
    assert '<fieldset id="filters" class="filters" hidden>' in page
    assert '<button type="button" id="theme-toggle" hidden>' in page
    # Without script every detail row is visible: no detail row carries the hidden attribute in the markup.
    assert re.search(r'<tr class="detail-row"[^>]*hidden', page) is None


def test_component_report_has_one_card(run_a, tmp_path):
    page = _summary(run_a / "certify", tmp_path)
    assert "Inji Certify (issuer)" in page and "Inji Verify (verifier)" not in page
    assert "Component run" in page


def test_comparison_box(run_a, run_b, tmp_path):
    page = _summary(run_a, tmp_path, run_b)
    assert "Changes since run <code>20261003T101500Z-9f8e7d6</code>" in page
    assert '<a href="diff.html">' in page
    assert "0 new regressions · 2 fixed" in page


def test_diff_page_of_identical_runs(run_a, fixed_time):
    page = html.render_diff(diff_runs(load_run(run_a), load_run(run_a)), html.generated_now("x"))
    assert "Same verdicts" in page and "Every module has the same verdict" in page


# ---------------------------------------------------------------------------------------------------------------
# Colours: WCAG 2.1 AA contrast of every text token, in both themes
# ---------------------------------------------------------------------------------------------------------------

TEXT_TOKENS = ("text", "muted", "link", "conforms", "gap", "regression", "na", "stale")
BACKGROUNDS = ("bg", "surface")


def _themes() -> dict[str, dict[str, str]]:
    css = resources.files("inji_conformance.report").joinpath("assets", "report.css").read_text(encoding="utf-8")
    blocks = {
        "light": re.search(r"^:root \{(.*?)^\}", css, re.S | re.M),
        "dark (system)": re.search(r':root:not\(\[data-theme="light"\]\) \{(.*?)\}', css, re.S),
        "dark (button)": re.search(r':root\[data-theme="dark"\] \{(.*?)\}', css, re.S),
    }
    return {
        name: dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{3,6})", match.group(1))) for name, match in blocks.items()
    }


def test_both_dark_blocks_define_the_same_colours():
    themes = _themes()
    assert themes["dark (system)"] == themes["dark (button)"]
    assert set(themes["light"]) == set(themes["dark (system)"])


@pytest.mark.parametrize("theme", ["light", "dark (system)"])
@pytest.mark.parametrize("token", TEXT_TOKENS)
def test_text_tokens_meet_wcag_aa(theme, token):
    colours = _themes()[theme]
    for background in BACKGROUNDS:
        ratio = contrast_ratio(colours[token], colours[background])
        assert ratio >= 4.5, f"{theme}: --{token} on --{background} is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", ["light", "dark (system)"])
def test_code_text_meets_wcag_aa(theme):
    colours = _themes()[theme]
    assert contrast_ratio(colours["text"], colours["code-bg"]) >= 4.5
