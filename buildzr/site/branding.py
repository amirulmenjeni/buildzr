"""Structurizr themes and workspace branding for the viewer.

Three things of ``views.configuration`` reach the viewer:

* ``themes``: each URL is matched, by the folder name before ``/theme.json``, against the themes buildzr ships in
  :mod:`buildzr.themes` (e.g. ``.../amazon-web-services-2023.01.31/theme.json``). Their element and relationship
  styles come before the workspace's own styles (see :class:`buildzr.site.styles.Styles`). Nothing is downloaded:
  a theme buildzr does not ship is reported and left out.
* element style ``icon`` and ``branding.logo``: the built workspace carries every image it shows (:class:`Images`), so
  the viewer shows it online and offline alike and loads nothing from other sites. A ``data:`` URI is copied. The URL
  of an icon of a theme buildzr ships (:mod:`buildzr.themes`, pinned to one structurizr/themes commit) is fetched
  from that commit at build time, or read from the cache (:func:`buildzr.themes.assets.fetch_icon`). Any other
  ``http(s)`` URL is reported and not shown.
* ``branding.font``: the name becomes the CSS font family of the diagram text; its URL is reported and not loaded.

Every problem is a diagnostic (a line for ``build.json`` ``warnings``) and a fallback, never an error.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from typing import Any, Optional
from urllib.parse import urlsplit

from buildzr.themes import assets

Json = dict[str, Any]

BRANDING_SCHEMA = "buildzr.branding/1"
#: The largest image (decoded) copied into a built workspace.
MAX_IMAGE_BYTES = 512 * 1024
#: At most this many remote or unreadable images are named one by one; the rest are counted.
MAX_NAMED = 10
IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml")
GENERIC_FAMILIES = ("serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-serif",
                    "ui-sans-serif", "ui-monospace", "ui-rounded")
_DATA_URI = re.compile(r"data:([a-z0-9.+/-]+);base64,(.*)", re.S | re.I)
_FAMILY = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}")

_bundled: Optional[dict[str, Json]] = None


def theme_key(url: str) -> Optional[str]:
    """The folder name before ``/theme.json`` (lower case), which names a Structurizr theme and its version."""
    path = urlsplit(url.strip()).path if "://" in url else url.strip()
    segs = [s for s in path.split("/") if s]
    if len(segs) >= 2 and segs[-1].lower() == "theme.json":
        return segs[-2].lower()
    return None


def bundled_themes() -> dict[str, Json]:
    """``theme key -> {"name", "elements"}`` of every theme of :mod:`buildzr.themes`, in each theme's order."""
    global _bundled
    if _bundled is None:
        import importlib
        import pkgutil

        from buildzr.themes import generated
        from buildzr.themes.base import ThemeElement

        found: dict[str, Json] = {}
        classes = []
        for mod in sorted(m.name for m in pkgutil.iter_modules(generated.__path__)):
            module = importlib.import_module(f"{generated.__name__}.{mod}")
            classes += [v for v in vars(module).values() if isinstance(v, type) and hasattr(v, "THEME_URL")]
        for cls in classes:
            key = theme_key(str(getattr(cls, "THEME_URL")))
            if key is None or key in found:
                continue
            elements = []
            for v in vars(cls).values():
                if isinstance(v, ThemeElement):
                    st = {"tag": v.tag, "stroke": v.stroke, "color": v.color, "icon": v.icon_url}
                    elements.append({k: x for k, x in st.items() if x})
            found[key] = {"name": getattr(cls, "THEME_NAME", key), "elements": elements}
        _bundled = found
    return _bundled


def resolve_themes(urls: Any) -> tuple[list[Json], list[Json], list[str]]:
    """``(element styles, relationship styles, diagnostics)`` of the themes ``urls``, in their order."""
    elements: list[Json] = []
    relationships: list[Json] = []
    problems: list[str] = []
    known = bundled_themes()
    for url in urls or []:
        key = theme_key(url) if isinstance(url, str) else None
        theme = known.get(key) if key else None
        if theme is None:
            problems.append(f"theme {_short(str(url))}: not a theme buildzr ships, so its styles are not applied "
                            "(buildzr does not download themes). Use one from buildzr.themes, or add the styles "
                            "you need with StyleElements and StyleRelationships")
            continue
        elements.extend(theme["elements"])
        relationships.extend(theme.get("relationships", []))
    return elements, relationships, problems


def _short(s: str, n: int = 120) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


class Images:
    """The images a built workspace carries: ``sha256:<hex> -> data URI`` (base64 re-encoded, so the same image
    always gives the same bytes), and the diagnostics of the ones left out.

    ``network`` false fetches no icon: a theme icon then comes from the cache only. After the first icon whose host
    cannot be reached, the others come from the cache only too, so a build without network does not wait for every
    icon in turn. :attr:`incomplete` says that an icon could not be fetched, so the next build tries again.
    """

    def __init__(self, network: bool = True) -> None:
        self.images: dict[str, str] = {}
        self.problems: list[str] = []
        self.network = network
        self._seen: dict[str, Optional[str]] = {}
        self._remote: list[str] = []
        self._unfetched: list[str] = []
        self._down = ""  # why the network is no longer used: the first icon whose host could not be reached

    @property
    def incomplete(self) -> bool:
        """Whether a theme icon is left out because it could not be fetched (not because of the workspace)."""
        return bool(self._unfetched)

    def add(self, value: Any, what: str) -> Optional[str]:
        """The id of the image ``value`` (``what`` names it in a diagnostic), or ``None`` when it is not shown."""
        if not isinstance(value, str) or not value.strip():
            return None
        if value in self._seen:
            return self._seen[value]
        img = self._read(value.strip(), what)
        self._seen[value] = img
        return img

    def _read(self, value: str, what: str) -> Optional[str]:
        if re.match(r"https?://", value, re.I):
            pinned = assets.pinned_url(value)
            if pinned is None:
                self._remote.append(f"{what} {_short(value, 240)}")
                return None
            try:
                value = assets.fetch_icon(pinned, network=self.network and not self._down)
            except assets.IconFetchError as e:
                why = e.reason
                if e.network and self._down:
                    why = f"it is not in the cache ({assets.cache_dir()}) and {self._down}"
                elif e.network and self.network:
                    self._down = f"{_short(pinned, 240)} could not be fetched either"
                self._unfetched.append(f"{what} {_short(pinned, 240)}: not shown, {why}")
                return None
        m = _DATA_URI.fullmatch(value)
        mime = m.group(1).lower() if m else ""
        if not m or mime not in IMAGE_TYPES:
            self.problems.append(f"{what} {_short(value, 60)}: not shown; an image must be a data URI "
                                 "(data:image/png;base64,...) of a PNG, JPEG, GIF, WebP or SVG image")
            return None
        try:
            data = base64.b64decode(re.sub(r"\s+", "", m.group(2)), validate=True)
        except (binascii.Error, ValueError):
            self.problems.append(f"{what} {_short(value, 60)}: not shown; its base64 data cannot be decoded")
            return None
        if not data or len(data) > MAX_IMAGE_BYTES:
            self.problems.append(f"{what} {_short(value, 60)}: not shown; the image is {len(data)} bytes, "
                                 f"buildzr copies images of 1 to {MAX_IMAGE_BYTES} bytes")
            return None
        uri = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        img = "sha256:" + hashlib.sha256(uri.encode("ascii")).hexdigest()
        self.images[img] = uri
        return img

    def diagnostics(self) -> list[str]:
        out = list(self.problems)
        unfetched = sorted(set(self._unfetched))
        for u in unfetched[:MAX_NAMED]:
            out.append(f"{u}. The next build tries again")
        if len(unfetched) > MAX_NAMED:
            out.append(f"and {len(unfetched) - MAX_NAMED} more theme icons not fetched either")
        remote = sorted(set(self._remote))
        for r in remote[:MAX_NAMED]:
            out.append(f"{r}: not shown, the image is on another site and the viewer loads nothing from other sites "
                       "(buildzr fetches only the icons of the themes it ships). Embed it instead: a data URI")
        if len(remote) > MAX_NAMED:
            out.append(f"and {len(remote) - MAX_NAMED} more images on other sites, not shown either")
        return out


def font_family(name: str) -> tuple[Optional[str], list[str]]:
    """The CSS font family list of a branding font ``name`` (``"Georgia, serif"`` -> ``'"Georgia", serif'``), with
    ``Inter, sans-serif`` after it unless the list ends in a generic family; and the diagnostics."""
    families: list[str] = []
    problems: list[str] = []
    for part in name.split(","):
        f = part.strip().strip("'\"").strip()
        if not f:
            continue
        if not _FAMILY.fullmatch(f):
            problems.append(f"branding font {_short(f, 60)!r}: not used; a font family name has letters, digits, "
                            "spaces, '.', '_' and '-' only")
            continue
        families.append(f if f.lower() in GENERIC_FAMILIES else f'"{f}"')
    if not families:
        return None, problems
    if families[-1].lower() not in GENERIC_FAMILIES:
        families += [x for x in ('"Inter"', "sans-serif") if x not in families]
    return ", ".join(families), problems


def branding(ws: Json, images: Images) -> tuple[Json, list[str]]:
    """The ``branding`` of the built workspace (``font`` and ``logo``, each only when set) and its diagnostics."""
    b = (ws.get("views", {}).get("configuration", {}) or {}).get("branding") or {}
    out: Json = {}
    problems: list[str] = []
    logo = images.add(b.get("logo"), "branding logo")
    if logo:
        out["logo"] = logo
    font = b.get("font") or {}
    name = font.get("name") if isinstance(font.get("name"), str) else ""
    if name.strip():
        family, problems = font_family(name)
        if family:
            out["font"] = {"name": name.strip(), "family": family}
    if isinstance(font.get("url"), str) and font["url"].strip():
        shown = f"the first of {out['font']['family']} that the reader's computer has" if out.get("font") else "Inter"
        problems.append(f"branding font URL {_short(font['url'].strip())}: not loaded (the viewer loads fonts only "
                        f"from the built workspace); the diagrams use {shown}")
    return out, problems
