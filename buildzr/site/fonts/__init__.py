"""Inter text metrics and label wrapping for the site build (design note v4, section C)."""

from __future__ import annotations

import math
from typing import Any, Optional

from buildzr.site.fonts.metrics import FONT_FAMILY, LINE_HEIGHT, advance, measure, wrap_words

__all__ = ["FONT_FAMILY", "LINE_HEIGHT", "advance", "measure", "wrap_words", "wrap", "text_height",
           "widest", "leaf_size", "ELEM_W", "PAD", "MIN_H"]

ELEM_W = 240  # leaf box width, px
PAD = 16  # label padding inside a box, px
MIN_H = 120  # minimum leaf box height, px

Line = dict[str, Any]


def wrap(lines: list[Line], width: float, font_size: float = 16) -> list[Line]:
    """Wrap each unwrapped label line to ``width`` px, keeping its tier, weight, size and italic.

    ``lines`` are ``{"text", "tier", ["weight"], ["size"], ["italic"]}``. A line that fits stays one
    line; a longer one becomes several lines carrying the same keys. Measurement uses the line's own
    ``size`` (default ``font_size``) and ``weight``. Empty text produces no line.
    """
    out: list[Line] = []
    for ln in lines:
        size = float(ln.get("size", font_size))
        weight = ln.get("weight", "normal")
        for piece in wrap_words(ln["text"], size, width, weight):
            out.append({**ln, "text": piece})
    return out


def text_height(lines: list[Line], font_size: float = 16) -> float:
    """Height in px of already wrapped lines (one line box each)."""
    return sum(float(ln.get("size", font_size)) * LINE_HEIGHT for ln in lines)


def widest(lines: list[Line], font_size: float = 16) -> float:
    """Width in px of the widest of ``lines``."""
    return max((measure(ln["text"], float(ln.get("size", font_size)), ln.get("weight", "normal"))
                for ln in lines), default=0.0)


def leaf_size(lines: list[Line], font_size: float = 16, width: Optional[float] = None) -> tuple[float, int, list[Line]]:
    """Size a leaf box as the spike's ``size_and_label``: fixed width, height from the wrapped label.

    Returns ``(width, height, wrapped_lines)``; the height is rounded up to whole px.
    """
    w = float(ELEM_W if width is None else width)
    wrapped = wrap(lines, w - 2 * PAD, font_size)
    h = 2 * PAD + text_height(wrapped, font_size)
    return w, int(math.ceil(max(MIN_H, h) - 1e-9)), wrapped
