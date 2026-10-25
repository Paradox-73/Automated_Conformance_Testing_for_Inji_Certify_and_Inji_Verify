"""The status badge: text, colour by gate, contrast and SVG structure."""

from __future__ import annotations

import dataclasses
import xml.etree.ElementTree as ET

import pytest

from inji_conformance.report import badge
from inji_conformance.report.runs import Run, load_run

from .contrast import contrast_ratio

SVG = "{http://www.w3.org/2000/svg}"


def test_badge_text_of_a_passing_run_with_known_gaps(run_a):
    result = badge.badge_for(load_run(run_a))
    assert result.label == "conformance"
    # The certify fixture carries the TLS proxy's metadata workaround, so its part says "patched".
    assert result.message == "certify 10 ok, 1 gap, patched | verify 10 ok, 1 gap"
    assert result.colour == badge.AMBER
    assert result.description.endswith("gate passed")
    assert (
        "certify: 10 conform, 1 known gap, 0 regressions, 0 stale benchmark entries, 4 not applicable, "
        "1 harness workaround applied"
    ) in result.description


def test_badge_text_of_a_failing_run(run_b):
    result = badge.badge_for(load_run(run_b))
    assert result.message == "certify 9 ok, 1 fail, 1 stale | verify 8 ok, 1 gap, 1 fail"
    assert result.colour == badge.RED
    assert result.description.endswith("gate failed")


def test_badge_of_one_component(run_a):
    assert badge.badge_for(load_run(run_a / "verify")).message == "verify 10 ok, 1 gap"


def test_green_when_everything_conforms(copied_runs, edit_json):
    results = copied_runs / "run-a" / "certify" / "results.json"

    def only_conforming(data):
        data["modules"] = [m for m in data["modules"] if m["verdict"] == "conforms"]
        data["summary"] = {
            "total": len(data["modules"]),
            "conforms": len(data["modules"]),
            "known_gap": 0,
            "regression": 0,
            "not_applicable": 0,
            "stale_benchmark": 0,
        }

    edit_json(results, only_conforming)
    assert badge.badge_for(load_run(results)).colour == badge.GREEN


def test_grey_when_no_gate_was_applied(run_a):
    # results.json v1 always carries a gate; a run built in code without one (as a future --no-gate run would be)
    # gets the neutral colour.
    item = load_run(run_a / "verify").components[0]
    ungated = dataclasses.replace(item, results=dataclasses.replace(item.results, gate=None))
    result = badge.badge_for(Run((ungated,)))
    assert result.colour == badge.GREY and result.description.endswith("no gate applied")


@pytest.mark.parametrize("colour", [badge.GREEN, badge.AMBER, badge.RED, badge.GREY])
def test_white_text_meets_wcag_aa(colour):
    assert contrast_ratio("#ffffff", colour) >= 4.5


def test_svg_is_well_formed_and_accessible(run_a):
    result = badge.badge_for(load_run(run_a))
    root = ET.fromstring(badge.render_badge(result))
    assert root.tag == f"{SVG}svg" and root.get("role") == "img"
    assert root.get("aria-label") == result.description
    assert root.find(f"{SVG}title").text == result.description
    texts = [element.text for element in root.iter(f"{SVG}text")]
    assert texts == ["conformance", result.message]
    rects = list(root.iter(f"{SVG}rect"))
    label, message = rects[1], rects[2]  # rects[0] is the rounded clip path
    assert int(message.get("x")) == int(label.get("width"))
    assert int(root.get("width")) == int(label.get("width")) + int(message.get("width"))


def test_text_width():
    assert badge.text_width("") == 0
    assert badge.text_width("ok") == pytest.approx(13.2)
    assert badge.text_width("é") == badge.text_width("m")  # unknown characters take the widest letter


def test_badge_escapes_text():
    svg = badge.render_badge(badge.Badge("a<b", "c&d", badge.GREEN, 'say "hi"'))
    ET.fromstring(svg)  # parses: every special character was escaped
    assert "a&lt;b" in svg and "c&amp;d" in svg
