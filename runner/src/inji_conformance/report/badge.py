"""The status badge (``badge.svg``): a two-part label in the common "label | message" shape.

The message lists each component with its counts, for example ``certify 10 ok, 1 gap | verify 9 ok, 1 fail``:

- ``ok``: modules that conform; ``gap``: known gaps (listed in the benchmark); ``fail``: regressions;
  ``stale``: stale benchmark entries. Zero counts other than ``ok`` are left out to keep the badge short.
- ``patched``: the run applied a workaround to what the component publishes (``workarounds`` in results.json).

The colour follows the gate: green when the gate passed with no known gaps or stale entries, amber when it passed
with them, red when it failed, grey when no gate was applied. White text on each colour has a contrast ratio of at
least 4.5:1 (WCAG AA); ``runner/tests/report/test_badge.py`` checks it. The full sentence is also in the SVG's
``title`` and ``aria-label``, so a screen reader does not have to read the abbreviations.

Text width: badges are drawn in 11 px Verdana, and SVG cannot measure text before it is shown. The widths below
are Verdana's advance widths at 11 px; ``textLength`` then makes the browser fit the text into exactly the computed
width, so the badge looks the same whether or not Verdana is installed.
"""

from __future__ import annotations

import dataclasses
from xml.sax.saxutils import escape, quoteattr

from inji_conformance.model import Verdict
from inji_conformance.report.runs import Run

LABEL = "conformance"
GREEN = "#1a7f37"  # 5.1:1 with white
AMBER = "#8a5300"  # 6.4:1 with white
RED = "#c4261d"  # 5.6:1 with white
GREY = "#555555"  # 7.5:1 with white; also the label background

# Advance widths of Verdana at 11 px, rounded to 0.1 px, for printable ASCII. Other characters use the "m" width,
# the widest lower-case letter, so text is never cut off.
# fmt: off
_WIDTHS = dict(
    zip(
        " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
        (
            3.9, 4.3, 5.1, 9.0, 7.0, 11.9, 8.0, 3.0, 5.0, 5.0, 7.0, 9.0, 4.0, 5.0, 4.0, 5.0,
            7.0, 7.0, 7.0, 7.0, 7.0, 7.0, 7.0, 7.0, 7.0, 7.0, 5.0, 5.0, 9.0, 9.0, 9.0, 6.0,
            11.0, 7.5, 7.6, 7.7, 8.5, 7.0, 6.3, 8.5, 8.3, 4.6, 5.0, 7.6, 6.1, 9.4, 8.2, 8.7,
            6.6, 8.7, 7.7, 7.5, 6.8, 8.1, 7.5, 11.0, 7.5, 6.8, 7.5, 5.0, 5.0, 5.0, 9.0, 7.0,
            7.0, 6.6, 6.8, 5.7, 6.8, 6.6, 3.9, 6.8, 7.0, 3.0, 3.8, 6.5, 3.0, 10.7, 7.0, 6.7,
            6.8, 6.8, 4.7, 5.7, 4.3, 7.0, 6.5, 9.0, 6.5, 6.5, 5.8, 7.0, 5.0, 7.0, 9.0,
        ),
        strict=True,
    )
)
# fmt: on
_FALLBACK_WIDTH = _WIDTHS["m"]
_PADDING = 6  # px on each side of a text


def text_width(text: str) -> float:
    """Width of ``text`` in 11 px Verdana, in px, rounded to 0.1."""
    return round(sum(_WIDTHS.get(char, _FALLBACK_WIDTH) for char in text), 1)


@dataclasses.dataclass(frozen=True)
class Badge:
    label: str
    message: str
    colour: str
    description: str  # full sentence for title and aria-label


_SHORT = (
    (Verdict.KNOWN_GAP, "gap", "known gap", "known gaps"),
    (Verdict.REGRESSION, "fail", "regression", "regressions"),
    (Verdict.STALE_BENCHMARK, "stale", "stale benchmark entry", "stale benchmark entries"),
)


def badge_for(run: Run) -> Badge:
    """The badge of a run: per-component counts, colour from the gate."""
    parts, sentences = [], []
    for item in run.components:
        summary = item.summary
        counts = [f"{summary.conforms} ok"]
        words = [f"{summary.conforms} conform"]
        for verdict, short, singular, plural in _SHORT:
            count = getattr(summary, verdict.value)
            if count:
                counts.append(f"{count} {short}")
            words.append(f"{count} {singular if count == 1 else plural}")
        words.append(f"{summary.not_applicable} not applicable")
        if item.results.workarounds:  # the harness changed what the component publishes (results.json workarounds)
            counts.append("patched")
            n = len(item.results.workarounds)
            words.append(f"{n} harness workaround{'' if n == 1 else 's'} applied")
        parts.append(f"{item.component.value} {', '.join(counts)}")
        sentences.append(f"{item.component.value}: {', '.join(words)}")

    gate = run.gate_passed
    attention = run.count(Verdict.KNOWN_GAP) + run.count(Verdict.STALE_BENCHMARK)
    if gate is None:
        colour, gate_text = GREY, "no gate applied"
    elif not gate:
        colour, gate_text = RED, "gate failed"
    else:
        colour, gate_text = (AMBER if attention else GREEN), "gate passed"
    message = " | ".join(parts) or "no results"
    description = f"OpenID conformance of Inji, run {run.run_id}: {'; '.join(sentences) or 'no results'}; {gate_text}"
    return Badge(LABEL, message, colour, description)


def render_badge(badge: Badge) -> str:
    """The badge as a standalone SVG document."""
    label_width = round(text_width(badge.label) + 2 * _PADDING)
    message_width = round(text_width(badge.message) + 2 * _PADDING)
    width = label_width + message_width
    label_text = text_width(badge.label)
    message_text = text_width(badge.message)
    # Text is drawn at 10x scale and scaled down, the usual trick for crisp sub-pixel placement in badges.
    label_x = label_width * 5
    message_x = (label_width + message_width / 2) * 10
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" viewBox="0 0 {width} 20" '
        f'role="img" aria-label={quoteattr(badge.description)}>\n'
        f"  <title>{escape(badge.description)}</title>\n"
        f'  <clipPath id="r"><rect width="{width}" height="20" rx="3" fill="#fff"/></clipPath>\n'
        f'  <g clip-path="url(#r)">\n'
        f'    <rect width="{label_width}" height="20" fill="{GREY}"/>\n'
        f'    <rect x="{label_width}" width="{message_width}" height="20" fill="{badge.colour}"/>\n'
        f"  </g>\n"
        f'  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" '
        f'text-rendering="geometricPrecision" font-size="110">\n'
        f'    <text x="{label_x}" y="140" transform="scale(.1)" textLength="{round(label_text * 10)}">'
        f"{escape(badge.label)}</text>\n"
        f'    <text x="{round(message_x)}" y="140" transform="scale(.1)" textLength="{round(message_text * 10)}">'
        f"{escape(badge.message)}</text>\n"
        f"  </g>\n"
        f"</svg>\n"
    )
