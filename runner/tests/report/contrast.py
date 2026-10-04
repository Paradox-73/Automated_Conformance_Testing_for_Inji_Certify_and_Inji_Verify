"""WCAG 2.1 contrast ratio of two sRGB colours, for the report's colour tests."""

from __future__ import annotations


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(colour: str) -> float:
    """Relative luminance of ``#rrggbb`` or ``#rgb``."""
    digits = colour.lstrip("#")
    if len(digits) == 3:
        digits = "".join(d * 2 for d in digits)
    r, g, b = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(first: str, second: str) -> float:
    """From 1 (same colour) to 21 (black on white)."""
    a, b = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (a + 0.05) / (b + 0.05)
