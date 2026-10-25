"""Resolve node and edge styles for the level graphs.

Reads the element and relationship styles of the Structurizr JSON
(``views.configuration.styles``) and falls back to the C4 defaults. Lifted from
the viewer spike (``spike/scene/build_scenes.py``: ``resolve_styles``), with the
WCAG text-colour rule as the default.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from buildzr.site.canonical import rnd

Json = dict[str, Any]

TYPE_TEXT = {
    "Person": "Person", "SoftwareSystem": "Software System", "Container": "Container",
    "Component": "Component", "Group": "Group",
    "DeploymentNode": "Deployment Node", "InfrastructureNode": "Infrastructure Node",
}
TYPE_TAG = TYPE_TEXT

#: C4 defaults: ``type -> (fill, text colour, shape)``.
DEFAULTS = {
    "Person": ("#08427b", "#ffffff", "Person"),
    "SoftwareSystem": ("#1168bd", "#ffffff", "Box"),
    "Container": ("#438dd5", "#ffffff", "Box"),
    "Component": ("#85bbf0", "#000000", "Box"),
    "Element": ("#dddddd", "#000000", "Box"),  # a custom element
    "Group": ("#ffffff", "#444444", "Box"),
    "DeploymentNode": ("#ffffff", "#000000", "Box"),
    "InfrastructureNode": ("#ffffff", "#000000", "Box"),
}
#: Boundaries drawn with a solid border (groups and view boundaries are dashed).
SOLID_BOUNDARIES = ("DeploymentNode",)
SHAPES = {"Box", "RoundedBox", "Person", "Cylinder", "Pipe", "Folder", "Hexagon", "Circle", "Ellipse",
          "Component", "WebBrowser", "MobileDevicePortrait", "MobileDeviceLandscape", "Robot", "Diamond"}

NODE_FONT = 16
BOUNDARY_FONT = 16
EDGE_STROKE = "#707070"
EDGE_WIDTH = 1.5


def color(c: Optional[str]) -> Optional[str]:
    """``#rgb`` / ``#rrggbb`` as lower-case ``#rrggbb``; anything else is None."""
    if not c:
        return None
    c = c.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", c):
        return c
    if re.fullmatch(r"#[0-9a-f]{3}", c):
        return "#" + "".join(ch * 2 for ch in c[1:])
    return None


def luminance(c: str) -> float:
    def ch(v: int) -> float:
        v_ = v / 255
        return v_ / 12.92 if v_ <= 0.03928 else ((v_ + 0.055) / 1.055) ** 2.4
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio of two ``#rrggbb`` colours."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def darken(c: str, f: float = 0.7) -> str:
    return "#" + "".join(f"{int(int(c[i:i + 2], 16) * f):02x}" for i in (1, 3, 5))


class Styles:
    """Style lookup over the element and relationship styles of one workspace."""

    def __init__(self, ws: Json, text_color: str = "wcag",
                 themes: Optional[tuple[list[Json], list[Json]]] = None) -> None:
        """``themes`` are the ``(element, relationship)`` styles of the workspace's Structurizr themes
        (:func:`buildzr.site.branding.resolve_themes`): they come before the workspace's own styles, so for one tag
        the workspace's style wins, and of two themes the later one."""
        if text_color not in ("wcag", "c4"):
            raise ValueError("text_color must be 'wcag' or 'c4'")
        self.text_color = text_color
        styles = ws.get("views", {}).get("configuration", {}).get("styles", {}) or {}
        theme_el, theme_rel = themes or ([], [])
        self.elements: list[Json] = theme_el + (styles.get("elements", []) or [])
        self.relationships: list[Json] = theme_rel + (styles.get("relationships", []) or [])

    def _tag_order(self, tags: list[str], defaults: list[str], styles: list[Json]) -> list[str]:
        """Defaults first, then the other tags in the order the style list first mentions them."""
        first: dict[str, int] = {}
        for i, st in enumerate(styles):
            first.setdefault(st.get("tag", ""), i)
        rest = sorted((t for t in tags if t not in defaults), key=lambda t: (first.get(t, 1 << 30), t))
        return defaults + rest

    def node(self, type_: str, tags: list[str], role: str) -> tuple[Json, str]:
        """Resolved ``(style, shape)`` of an element node or a boundary."""
        fill, fg, shape = DEFAULTS.get(type_, DEFAULTS["Component"])
        fg_explicit = fill_explicit = False
        type_fill = fill
        if role == "boundary":
            fill = "#ffffff"  # boundaries are unfilled unless a style sets a background
        stroke: Optional[str] = None
        fs = float(BOUNDARY_FONT if role == "boundary" else NODE_FONT)
        opacity: Optional[float] = None
        bw: Optional[float] = None
        border: Optional[str] = None
        icon: Optional[str] = None
        for t in self._tag_order(tags, ["Element", TYPE_TAG.get(type_, type_)], self.elements):
            for st in self.elements:
                if st.get("tag") != t:
                    continue
                if color(st.get("background")):
                    fill, fill_explicit = color(st.get("background")) or fill, True
                if color(st.get("color")):
                    fg, fg_explicit = color(st.get("color")) or fg, True
                stroke = color(st.get("stroke")) or stroke
                if st.get("shape") in SHAPES:
                    shape = st["shape"]
                if st.get("fontSize"):
                    fs = float(st["fontSize"])
                if st.get("opacity") is not None:
                    opacity = float(st["opacity"]) / 100
                if st.get("strokeWidth"):
                    bw = float(st["strokeWidth"])
                if st.get("border"):
                    border = str(st["border"]).lower()
                if isinstance(st.get("icon"), str) and st["icon"].strip():
                    icon = st["icon"]
        if self.text_color == "wcag" and not fg_explicit:
            fg = "#000000" if contrast("#000000", fill) >= contrast("#ffffff", fill) else "#ffffff"
        style: Json
        if role == "boundary":
            bstroke = stroke or (type_fill if type_fill != "#ffffff" and not fill_explicit else "#888888")
            if not fg_explicit:  # the corner label takes the border colour when it reads on the fill
                fg = bstroke if contrast(bstroke, fill) >= 4.5 else (
                    "#000000" if contrast("#000000", fill) >= contrast("#ffffff", fill) else "#ffffff")
            style = {"fill": fill, "color": fg, "fontSize": rnd(fs), "dash": [6, 4], "stroke": bstroke}
            if type_ in SOLID_BOUNDARIES and border == "dotted":
                style["dash"] = [2, 3]
            elif type_ in SOLID_BOUNDARIES and border != "dashed":
                del style["dash"]
            shape = "Box"
        else:
            style = {"fill": fill, "stroke": stroke or darken(fill), "color": fg, "fontSize": rnd(fs)}
            if border == "dashed":
                style["dash"] = [6, 4]
            elif border == "dotted":
                style["dash"] = [2, 3]
        if opacity is not None:
            style["opacity"] = opacity
        if bw:
            style["strokeWidth"] = rnd(bw)
        if icon:
            style["icon"] = icon  # the image as the style gives it; the levels replace it with an image id
        return style, shape

    def edge(self, tags: list[str]) -> Json:
        """Resolved style of one relationship (see :meth:`merged_edge` for rolled-up edges)."""
        st_: Json = {"stroke": EDGE_STROKE, "arrow": "end", "width": EDGE_WIDTH}
        for t in self._tag_order(tags, ["Relationship"], self.relationships):
            for st in self.relationships:
                if st.get("tag") != t:
                    continue
                st_["stroke"] = color(st.get("color")) or st_["stroke"]
                if st.get("thickness"):
                    st_["width"] = rnd(float(st["thickness"]))
                if st.get("style") == "Solid" or st.get("dashed") is False:
                    st_.pop("dash", None)
                elif st.get("style") == "Dotted":
                    st_["dash"] = [2, 3]
                elif st.get("style") == "Dashed" or st.get("dashed") is True:
                    st_["dash"] = [5, 5]
                if st.get("fontSize"):
                    st_["fontSize"] = rnd(float(st["fontSize"]))
                if st.get("opacity") is not None:
                    st_["opacity"] = float(st["opacity"]) / 100
        return st_

    def merged_edge(self, tag_lists: list[list[str]]) -> Json:
        """Style of an edge standing for several relationships: theirs if all agree, else the default."""
        resolved = [self.edge(t) for t in tag_lists]
        if resolved and all(r == resolved[0] for r in resolved):
            return resolved[0]
        return self.edge([])
