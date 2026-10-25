"""Inter text metrics and label wrapping for the build (design note v4, section C)."""

from __future__ import annotations

import math
from typing import Any, Optional

from buildzr.site.fonts.metrics import FONT_FAMILY, LINE_HEIGHT, advance, measure, wrap_words

__all__ = ["FONT_FAMILY", "LINE_HEIGHT", "advance", "measure", "wrap_words", "wrap", "text_height",
           "widest", "leaf_size", "icon_inline_w", "ELEM_W", "PAD", "MIN_H", "ICON", "ICON_GAP"]

ELEM_W = 240  # leaf box width, px
PAD = 16  # label padding inside a box, px
MIN_H = 120  # minimum leaf box height, px
ICON = 40  # height of the icon above the label of a leaf box, px
ICON_GAP = 6  # between that icon and the label, px

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


def icon_inline_w(font_size: float = 16) -> float:
    """Width in px that the icon of a frame or boundary takes before its name: a square one line high, and a gap."""
    return font_size * LINE_HEIGHT + 4


def leaf_size(lines: list[Line], font_size: float = 16, width: Optional[float] = None,
              icon: str = "") -> tuple[float, int, list[Line]]:
    """Size a leaf box as the spike's ``size_and_label``: fixed width, height from the wrapped label.

    ``icon`` is ``"block"`` for an :data:`ICON` above the label (the box is that much higher), ``"inline"`` for one
    before the name (the label wraps that much narrower), or ``""``. Returns ``(width, height, wrapped_lines)``;
    the height is rounded up to whole px.
    """
    w = float(ELEM_W if width is None else width)
    wrapped = wrap(lines, w - 2 * PAD - (icon_inline_w(font_size) if icon == "inline" else 0), font_size)
    h = 2 * PAD + text_height(wrapped, font_size) + (ICON + ICON_GAP if icon == "block" else 0)
    return w, int(math.ceil(max(MIN_H, h) - 1e-9)), wrapped
