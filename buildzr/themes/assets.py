"""The structurizr/themes commit buildzr pins, and fetching the icons of its themes.

Every theme of :mod:`buildzr.themes` and every icon URL in it names one commit of
https://github.com/structurizr/themes, :data:`THEMES_COMMIT`. A commit is immutable: the same URL gives the same bytes
for ever, so an icon fetched once is cached for good (:func:`cache_dir`). buildzr ships the theme styles, not the
icons (about 17 MB); the build fetches the icons a workspace uses (:func:`fetch_icon`) and puts them into the built
workspace, so the viewer never loads anything from another site.

To move the pin, change :data:`THEMES_COMMIT` and the ``@ref`` line of ``buildzr/themes/themes.txt`` to the new full
commit SHA and regenerate the modules (``python -m buildzr.themes.generate --urls-file buildzr/themes/themes.txt``);
``tests/test_themes.py`` checks that the two and every generated URL agree.
"""

from __future__ import annotations

import base64
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

#: The GitHub repository of the Structurizr themes.
THEMES_REPO = "structurizr/themes"
#: The full SHA of the structurizr/themes commit that every theme and icon URL of buildzr names.
THEMES_COMMIT = "67da2b503abc708f941e5aa2ea35dd553f742c3a"
#: Every pinned URL starts with this.
PINNED_BASE = f"https://raw.githubusercontent.com/{THEMES_REPO}/{THEMES_COMMIT}/"
#: The largest icon fetched (the largest image a built workspace carries, :data:`buildzr.site.branding.MAX_IMAGE_BYTES`).
MAX_ICON_BYTES = 512 * 1024
#: Seconds to wait for the upstream host.
TIMEOUT = 15.0
#: ``BUILDZR_OFFLINE=1``: no network; icons come from the cache only.
OFFLINE_ENV = "BUILDZR_OFFLINE"
#: ``BUILDZR_CACHE_DIR``: the folder of buildzr's cache, instead of ``$XDG_CACHE_HOME/buildzr``.
CACHE_ENV = "BUILDZR_CACHE_DIR"

_SHA = re.compile(r"[0-9a-f]{40}")
_FOLDER_FILE = re.compile(r"[A-Za-z0-9._-]+")
_known: Optional[frozenset[str]] = None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Follows no redirect: the pinned URL is the file, and a redirect would lead away from the pinned commit."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        raise urllib.error.HTTPError(req.full_url, code, f"{msg}, a redirect to {newurl} (not followed)", headers, fp)


#: Opens a request; tests replace it to fake the upstream host.
_urlopen: Callable[..., Any] = urllib.request.build_opener(_NoRedirect).open


class IconFetchError(Exception):
    """The icon at ``url`` could not be fetched or is not a usable image, because of ``reason``. ``network`` is true
    when the host could not be reached (so trying the next icon would only wait for the same timeout)."""

    def __init__(self, url: str, reason: str, network: bool = False) -> None:
        super().__init__(f"{url}: {reason}")
        self.url, self.reason, self.network = url, reason, network


def is_full_sha(ref: str) -> bool:
    """Whether ``ref`` is a full (40 hex digit, lower case) commit SHA, not a branch, a tag or a short SHA."""
    return bool(_SHA.fullmatch(ref))


def offline() -> bool:
    """Whether ``BUILDZR_OFFLINE`` asks for no network."""
    return os.environ.get(OFFLINE_ENV, "").strip().lower() not in ("", "0", "false", "no")


def known_icons() -> frozenset[str]:
    """The pinned URL of every icon of the themes of :mod:`buildzr.themes`."""
    global _known
    if _known is None:
        import importlib
        import pkgutil

        from buildzr.themes import generated
        from buildzr.themes.base import ThemeElement

        urls: set[str] = set()
        for mod in pkgutil.iter_modules(generated.__path__):
            module = importlib.import_module(f"{generated.__name__}.{mod.name}")
            for cls in vars(module).values():
                if isinstance(cls, type) and hasattr(cls, "THEME_URL"):
                    urls.update(v.icon_url for v in vars(cls).values() if isinstance(v, ThemeElement) and v.icon_url)
        _known = frozenset(u for u in urls if u.startswith(PINNED_BASE))
    return _known


def pinned_url(url: str) -> Optional[str]:
    """The pinned URL of ``url`` when it names an icon of a theme buildzr ships, else ``None``.

    The pinned URL itself, the same file at another ref of the GitHub repository
    (``https://raw.githubusercontent.com/structurizr/themes/{branch}/<theme>/<file>``) and the Structurizr CDN
    (``https://static.structurizr.com/themes/<theme>/<file>``) all give the pinned URL: the file of that theme at
    :data:`THEMES_COMMIT`. Any other URL, and a file the pinned themes do not use, gives ``None``.
    """
    parts = urlsplit(url.strip())
    if parts.scheme.lower() != "https" or parts.query or parts.fragment:
        return None
    host = (parts.hostname or "").lower()
    segs = parts.path.split("/")[1:]
    if host == "raw.githubusercontent.com" and len(segs) == 5 and "/".join(segs[:2]).lower() == THEMES_REPO:
        folder, name = segs[3], segs[4]
    elif host == "static.structurizr.com" and len(segs) == 3 and segs[0] == "themes":
        folder, name = segs[1], segs[2]
    else:
        return None
    if not (_FOLDER_FILE.fullmatch(folder) and _FOLDER_FILE.fullmatch(name)):
        return None
    pinned = f"{PINNED_BASE}{folder}/{name}"
    return pinned if pinned in known_icons() else None


def cache_dir() -> str:
    """Where fetched icons are kept: ``<cache>/themes-<commit>``, with ``<cache>`` the ``BUILDZR_CACHE_DIR``, else
    ``$XDG_CACHE_HOME/buildzr`` (``~/.cache/buildzr`` by default). A new pin starts a new, empty folder."""
    base = os.environ.get(CACHE_ENV) or os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache"), "buildzr")
    return os.path.join(base, f"themes-{THEMES_COMMIT}")


def image_type(data: bytes) -> Optional[str]:
    """The media type of the image ``data`` by its first bytes (PNG, JPEG, GIF, WebP, SVG), or ``None``."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    head = data[:1024].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if (head.startswith(b"<?xml") or head.startswith(b"<svg")) and b"<svg" in head:
        return "image/svg+xml"
    return None


def _check(data: bytes, url: str) -> str:
    if not data or len(data) > MAX_ICON_BYTES:
        raise IconFetchError(url, f"it is {len(data)} bytes; an icon is 1 to {MAX_ICON_BYTES} bytes")
    mime = image_type(data)
    if mime is None:
        raise IconFetchError(url, "it is not a PNG, JPEG, GIF, WebP or SVG image")
    return mime


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "buildzr"})
    try:
        with _urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - a pinned https URL (pinned_url / known_icons)
            final = r.geturl() if hasattr(r, "geturl") else url
            if final != url:
                raise IconFetchError(url, f"it redirected to {final} (not followed)")
            data: bytes = r.read(MAX_ICON_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise IconFetchError(url, f"the host answered HTTP {e.code} {e.reason}") from e
    except (urllib.error.URLError, OSError) as e:  # no network, DNS, TLS, timeout
        reason = getattr(e, "reason", e)
        raise IconFetchError(url, f"could not reach the host ({reason})", network=True) from e
    return data


def fetch_icon(url: str, network: bool = True) -> str:
    """The ``data:`` URI of the icon at ``url``.

    A pinned URL (:func:`pinned_url`) is read from the cache, else downloaded (unless ``network`` is false or
    ``BUILDZR_OFFLINE`` is set) and cached. Any other URL is downloaded every time and not cached. Either way the
    download waits :data:`TIMEOUT` seconds at most, follows no redirect, and the bytes must be a PNG, JPEG, GIF, WebP
    or SVG image of at most :data:`MAX_ICON_BYTES`.

    Raises:
        IconFetchError: When the icon is not cached and cannot be downloaded, or is not such an image.
    """
    pinned = pinned_url(url)
    if pinned is not None:
        path = os.path.join(cache_dir(), *pinned[len(PINNED_BASE):].split("/"))
        try:
            with open(path, "rb") as f:
                data = f.read(MAX_ICON_BYTES + 1)
            return f"data:{_check(data, pinned)};base64,{base64.b64encode(data).decode('ascii')}"
        except (OSError, IconFetchError):
            pass  # not cached yet, or a damaged file: download it again
        if not network or offline():
            why = f"{OFFLINE_ENV} is set" if offline() else "the network is not used"
            raise IconFetchError(pinned, f"it is not in the cache ({cache_dir()}) and {why}", network=True)
        data = _download(pinned)
        mime = _check(data, pinned)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    if not network or offline():
        raise IconFetchError(url, "not fetched: " + (f"{OFFLINE_ENV} is set" if offline() else "the network is not used"),
                             network=True)
    data = _download(url)
    return f"data:{_check(data, url)};base64,{base64.b64encode(data).decode('ascii')}"
