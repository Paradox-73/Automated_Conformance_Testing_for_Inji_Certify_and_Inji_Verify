"""Accessibility rules of summary.html and diff.html that a plain HTML parse can check. The full axe-core run and the
keyboard check are described in docs/accessibility.md."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from inji_conformance import __version__
from inji_conformance.report import html
from inji_conformance.report.diff import diff_runs
from inji_conformance.report.runs import load_run

VOID = {"img", "input", "meta", "br", "use", "path", "circle", "rect"}


class _Audit(HTMLParser):
    """Records the facts the tests assert: language, headings, header scopes, image alts, link and button names."""

    def __init__(self) -> None:
        super().__init__()
        self.lang: str | None = None
        self.headings: list[int] = []
        self.th_without_scope: list[str] = []
        self.img_without_alt: list[str] = []
        self.unnamed: list[str] = []
        self._open: list[dict] = []  # open <a>/<button>: {"tag", "name"}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        elif re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))
        elif tag == "th" and a.get("scope") not in ("col", "row"):
            self.th_without_scope.append(self.get_starttag_text() or "th")
        elif tag == "img":
            if not (a.get("alt") or "").strip():
                self.img_without_alt.append(a.get("src", "")[:40])
            for item in self._open:
                item["name"] = True
        elif tag in ("a", "button") and not (tag == "a" and "href" not in a):
            self._open.append({"tag": tag, "name": bool(a.get("aria-label")), "text": self.get_starttag_text()})

    def handle_data(self, data):
        if data.strip():
            for item in self._open:
                item["name"] = True

    def handle_endtag(self, tag):
        if tag in ("a", "button") and self._open and self._open[-1]["tag"] == tag:
            item = self._open.pop()
            if not item["name"]:
                self.unnamed.append(item["text"])


def _audit(page: str) -> _Audit:
    audit = _Audit()
    audit.feed(page)
    return audit


@pytest.fixture
def pages(copied_runs: Path, tmp_path: Path, fixed_time: None) -> dict[str, str]:
    run_a, run_b = load_run(copied_runs / "run-a"), load_run(copied_runs / "run-b")
    diff = diff_runs(run_a, run_b)
    meta = html.generated_now(f"inji-conformance {__version__}")
    return {
        "summary": html.render_summary(run_b, tmp_path / "out", meta, diff),
        "diff": html.render_diff(diff, meta),
    }


@pytest.mark.parametrize("name", ["summary", "diff"])
def test_page_meets_basic_accessibility_rules(pages, name):
    audit = _audit(pages[name])
    assert audit.lang == "en"
    assert audit.headings and audit.headings[0] == 1 and audit.headings.count(1) == 1
    assert all(b - a <= 1 for a, b in zip(audit.headings, audit.headings[1:], strict=False)), audit.headings
    assert audit.th_without_scope == []
    assert audit.img_without_alt == []
    assert audit.unnamed == []


def test_summary_has_a_skip_link_and_every_table_a_caption(pages):
    page = pages["summary"]
    assert re.search(r'<a class="skip-link" href="#modules">', page)
    assert page.count("<table") == page.count("<caption")
