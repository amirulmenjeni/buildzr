"""mkdocs hooks of the docs build.

* Refuse to build the docs without the Run Code assets (``docs/runcode/``, see build_docs_assets.py).
* Render the product roadmap, the data file ``roadmap.yml`` in the repository root, into a page. The page is generated
  in memory: there is no ``docs/roadmap.md`` and no generated Markdown in Git.

The docs are versioned, one folder per release (https://buildzr.dev/1.1.1/, /latest/), but the roadmap is not: it is
built from master on its own, with ``mkdocs-roadmap.yml``, and served at https://buildzr.dev/roadmap/. That config sets
``extra.roadmap_site.docs_url`` and builds a site of one page, the roadmap, whose nav links to the pages of the latest
release. The versioned build (``mkdocs.yml``) has no roadmap page, links to /roadmap/, and only validates the file.
"""

from __future__ import annotations

import datetime
import html
import os
import re
from typing import Any
from urllib.parse import urlparse

import yaml
from mkdocs.exceptions import PluginError
from mkdocs.structure.files import File, Files

NEEDED = ("manifest.json", "viewer/index.html", "elk.bundled.js", "browser_elk.js")

ROADMAP_FILE = "roadmap.yml"
ROADMAP_PAGE = "roadmap.md"
COMPATIBILITY_PAGE = "structurizr-compatibility.md"
ROADMAP_VERSION = 1

STATUSES = ("active", "planned", "launched")
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TARGET = re.compile(r"^(\d+\.\d+|Later)$")
RELEASE = re.compile(r"^\d+\.\d+\.\d+(rc\d+)?$")
#: Anchors of the headings of the page: an item id must not take one.
RESERVED_IDS = ("roadmap",)
RESERVED_PREFIXES = ("rm-",)
MAX_TITLE, MAX_DESCRIPTION = 80, 240

TOP_KEYS = {"version", "active", "planned", "launched"}
ITEM_KEYS = {"id", "title", "description", "link"}
TARGET_KEYS = {"target", "items"}
RELEASE_KEYS = {"version", "date", "link", "items"}


def missing_runcode_assets(docs_dir: str) -> list[str]:
    """The files of ``docs/runcode/`` that the Run Code button loads and that are not there."""
    folder = os.path.join(docs_dir, "runcode")
    return [name for name in NEEDED if not os.path.isfile(os.path.join(folder, name))]


class _UniqueKeyLoader(yaml.SafeLoader):
    """A safe loader that refuses a key that is given twice in a mapping, which YAML would silently overwrite."""


def _mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"the key {key!r} is given twice", key_node.start_mark)
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load_roadmap(path: str) -> Any:
    """The parsed ``roadmap.yml``. A missing or malformed file is a ``PluginError``."""
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.load(f, Loader=_UniqueKeyLoader)  # noqa: S506 (a safe loader)
    except OSError as e:
        raise PluginError(f"Cannot read the roadmap {path}: {e.strerror or e}") from e
    except yaml.YAMLError as e:
        raise PluginError(f"{path} is not valid YAML: {e}") from e


def _text(value: Any, where: str, errors: list[str], limit: int) -> bool:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{where}: must be a non-empty text")
    elif value != value.strip() or "\n" in value:
        errors.append(f"{where}: must be one line without leading or trailing spaces")
    elif len(value) > limit:
        errors.append(f"{where}: is {len(value)} characters long, the limit is {limit}")
    else:
        return True
    return False


def _link(value: Any, where: str, errors: list[str]) -> None:
    parsed = urlparse(value) if isinstance(value, str) else None
    if not parsed or parsed.scheme != "https" or not parsed.netloc or re.search(r"\s", value):
        errors.append(f"{where}: must be an absolute https:// URL, got {value!r}")


def _keys(node: dict[Any, Any], known: set[str], required: set[str], where: str, errors: list[str]) -> None:
    for key in sorted(map(str, node.keys() - known)):
        errors.append(f"{where}: unknown key '{key}' (known: {', '.join(sorted(known))})")
    for key in sorted(required - node.keys()):
        errors.append(f"{where}: missing the required key '{key}'")


def _items(value: Any, where: str, errors: list[str], ids: dict[str, str], titles: dict[str, str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{where}: must be a non-empty list of items")
        return
    for i, item in enumerate(value):
        at = f"{where}[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{at}: must be a mapping with {', '.join(sorted(ITEM_KEYS))}")
            continue
        _keys(item, ITEM_KEYS, {"id", "title", "description"}, at, errors)
        item_id = item.get("id")
        if "id" in item:
            if not isinstance(item_id, str) or not KEBAB.match(item_id):
                errors.append(f"{at}.id: must be kebab-case (lowercase letters, digits and single hyphens), "
                              f"got {item_id!r}")
            elif item_id in RESERVED_IDS or item_id.startswith(RESERVED_PREFIXES):
                errors.append(f"{at}.id: '{item_id}' is reserved for the headings of the page")
            elif item_id in ids:
                errors.append(f"{at}.id: '{item_id}' is already used at {ids[item_id]}; an item is placed once, "
                              "move it between statuses instead of copying it")
            else:
                ids[item_id] = at
        if "title" in item and _text(item["title"], f"{at}.title", errors, MAX_TITLE):
            key = item["title"].casefold()
            if key in titles:
                errors.append(f"{at}.title: '{item['title']}' is already the title of {titles[key]}")
            else:
                titles[key] = at
        if "description" in item:
            _text(item["description"], f"{at}.description", errors, MAX_DESCRIPTION)
        if "link" in item:
            _link(item["link"], f"{at}.link", errors)


def validate_roadmap(data: Any) -> list[str]:
    """Every problem of a parsed roadmap, as ``where: what`` lines. Empty when the roadmap is valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["the file must be a mapping with version, planned and, optionally, active and launched"]
    _keys(data, TOP_KEYS, {"version", "planned"}, "roadmap", errors)
    version = data.get("version")
    if "version" in data and (version != ROADMAP_VERSION or isinstance(version, bool)):
        errors.append(f"version: must be {ROADMAP_VERSION}, got {version!r}")
    ids: dict[str, str] = {}
    titles: dict[str, str] = {}

    if "active" in data:
        _items(data["active"], "active", errors, ids, titles)

    if "planned" in data:
        planned = data["planned"]
        if not isinstance(planned, list) or not planned:
            errors.append("planned: must be a non-empty list of targets")
        else:
            seen: set[str] = set()
            for i, group in enumerate(planned):
                at = f"planned[{i}]"
                if not isinstance(group, dict):
                    errors.append(f"{at}: must be a mapping with target and items")
                    continue
                _keys(group, TARGET_KEYS, TARGET_KEYS, at, errors)
                target = group.get("target")
                if "target" in group:
                    if not isinstance(target, str) or not TARGET.match(target):
                        errors.append(f"{at}.target: must be a release like \"1.1\" (quote it) or \"Later\", "
                                      f"got {target!r}; a target is a direction, never a date")
                    elif target in seen:
                        errors.append(f"{at}.target: '{target}' is listed twice, merge the groups")
                    else:
                        seen.add(target)
                if "items" in group:
                    _items(group["items"], f"{at}.items", errors, ids, titles)
            if "Later" in seen and planned[-1].get("target") != "Later":
                errors.append("planned: the 'Later' target must be the last one")

    if "launched" in data:
        launched = data["launched"]
        if not isinstance(launched, list) or not launched:
            errors.append("launched: must be a non-empty list of releases, or left out")
        else:
            seen = set()
            previous: datetime.date | None = None
            for i, release in enumerate(launched):
                at = f"launched[{i}]"
                if not isinstance(release, dict):
                    errors.append(f"{at}: must be a mapping with {', '.join(sorted(RELEASE_KEYS))}")
                    continue
                _keys(release, RELEASE_KEYS, {"version", "date", "items"}, at, errors)
                number = release.get("version")
                if "version" in release:
                    if not isinstance(number, str) or not RELEASE.match(number):
                        errors.append(f"{at}.version: must be a quoted release like \"0.0.35\" or \"1.0.0rc1\", got {number!r}")
                    elif number in seen:
                        errors.append(f"{at}.version: '{number}' is listed twice")
                    else:
                        seen.add(number)
                if "date" in release:
                    day = _date(release["date"])
                    if day is None:
                        errors.append(f"{at}.date: must be a calendar date like 2026-10-16, got {release['date']!r}")
                    else:
                        if previous is not None and day > previous:
                            errors.append(f"{at}.date: {day} is later than the release above it, "
                                          "list the newest release first")
                        previous = day
                if "link" in release:
                    _link(release["link"], f"{at}.link", errors)
                if "items" in release:
                    _items(release["items"], f"{at}.items", errors, ids, titles)
    return errors


def _date(value: Any) -> datetime.date | None:
    if isinstance(value, datetime.datetime):
        return None
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _item_html(item: dict[str, Any]) -> str:
    title = html.escape(item["title"])
    if item.get("link"):
        title = f'<a href="{html.escape(item["link"], quote=True)}">{title}</a>'
    return (f'<li id="{item["id"]}"><strong>{title}</strong>'
            f'<span class="roadmap-description">{html.escape(item["description"])}</span></li>')


def _list(items: list[dict[str, Any]]) -> list[str]:
    return ["", '<ul class="roadmap-items">', *map(_item_html, items), "</ul>", ""]


def render_roadmap(data: dict[str, Any], compatibility: str = COMPATIBILITY_PAGE) -> str:
    """The Markdown of the roadmap page for a valid roadmap. Same data, same text: the output is deterministic.

    ``compatibility`` is the link to the Structurizr compatibility page.
    """
    out = [
        "---", "title: Roadmap", "---", "",
        "# Roadmap", "",
        "What we are working on and what we may do next. Planned work is grouped by a target release, a direction "
        "and not a promise: there are no dates, and an item can move or be dropped. "
        "Which Structurizr features buildzr supports is a separate question; see "
        f"[Structurizr compatibility]({compatibility}), where a missing feature does not mean "
        "it is planned.", "",
    ]
    if data.get("active"):
        out += ["## Active { #rm-active }", "", "Work that is underway now.", *_list(data["active"])]
    out += [
        "## Planned { #rm-planned }", "",
        "Work we intend to do, by the release we are aiming for. A later target is less certain.",
    ]
    for group in data["planned"]:
        target = group["target"]
        heading = target if target == "Later" else f"Aiming for {target}"
        out += ["", f"### {heading} {{ #rm-target-{_slug(target)} }}", *_list(group["items"])]
    launched = data.get("launched")
    if launched:
        out += ["## Launched { #rm-launched }", "", "Recent releases and what they added.", ""]
        for release in launched:
            number = release["version"]
            label = f"[{number}]({release['link']})" if release.get("link") else number
            date = _date(release["date"])
            out += [f"### {label} · {date.day} {date:%B %Y} {{ #rm-release-{_slug(number)} }}", *_list(release["items"])]
    return "\n".join(out).rstrip("\n") + "\n"


def roadmap_path(config: Any) -> str:
    """``roadmap.yml`` sits in the repository root, next to the folder of the docs."""
    return os.path.join(os.path.dirname(os.path.abspath(config["docs_dir"])), ROADMAP_FILE)


def build_roadmap(path: str, compatibility: str = COMPATIBILITY_PAGE) -> str:
    """Load, validate and render ``path``. Any problem is a ``PluginError`` that lists every fault."""
    data = load_roadmap(path)
    errors = validate_roadmap(data)
    if errors:
        raise PluginError(f"{os.path.basename(path)} is not a valid roadmap (schema version {ROADMAP_VERSION}):\n"
                          + "\n".join("  - " + e for e in errors))
    return render_roadmap(data, compatibility)


def roadmap_docs_url(config: Any) -> str | None:
    """The docs the roadmap site links to (``extra.roadmap_site.docs_url``), or None for the versioned docs."""
    site = (config.get("extra") or {}).get("roadmap_site") or {}
    url: str | None = site.get("docs_url")
    return url


def page_url(path: str) -> str:
    """The address of a page relative to the root of its site, like mkdocs gives it: ``a/b.md`` is ``a/b/``."""
    stem = path[:-len(".md")]
    if stem == "index" or stem.endswith("/index"):
        return stem[:-len("index")]
    return stem + "/"


def roadmap_nav(nav: Any, docs_url: str, roadmap_url: str) -> Any:
    """The nav of the roadmap site: the roadmap entry (``roadmap_url``) is its own page, ``index.md``, and every other
    page is the page of the docs at ``docs_url``."""
    if isinstance(nav, list):
        return [roadmap_nav(entry, docs_url, roadmap_url) for entry in nav]
    if isinstance(nav, dict):
        return {title: roadmap_nav(entry, docs_url, roadmap_url) for title, entry in nav.items()}
    if nav == roadmap_url:
        return "index.md"
    if isinstance(nav, str) and nav.endswith(".md"):
        return docs_url + page_url(nav)
    return nav


def on_config(config: Any) -> Any:
    docs_url = roadmap_docs_url(config)
    if docs_url is not None:
        config["nav"] = roadmap_nav(config["nav"], docs_url, config["site_url"])
        config["extra_javascript"] = []  # the Run Code and demo scripts: the roadmap has no code to run
        return config
    missing = missing_runcode_assets(config["docs_dir"])
    if missing:
        raise PluginError(
            "The Run Code assets are missing from docs/runcode/ (" + ", ".join(missing) + "). Build them first: "
            "`cd viewer && npm ci && cd .. && uv run python scripts/build_docs_assets.py` (Node.js 22 needed).")
    return config


def on_files(files: Files, config: Any) -> Files:
    if files.get_file_from_path(ROADMAP_PAGE) is not None:
        raise PluginError(f"docs/{ROADMAP_PAGE} must not exist: the page is generated from {ROADMAP_FILE} at build "
                          "time. Delete the file and edit the data instead.")
    docs_url = roadmap_docs_url(config)
    if docs_url is None:
        build_roadmap(roadmap_path(config))  # validated on every build; published by the roadmap site only
        return files
    # The theme's files and the stylesheets; none of the other files of the docs (pages, images, scripts).
    docs_dir = os.path.abspath(config["docs_dir"])
    pages = Files([f for f in files if f.src_uri.startswith("stylesheets/")
                   or f.abs_src_path is None or not os.path.abspath(f.abs_src_path).startswith(docs_dir + os.sep)])
    content = build_roadmap(roadmap_path(config), docs_url + page_url(COMPATIBILITY_PAGE))
    pages.append(File.generated(config, "index.md", content=content))
    return pages


def on_serve(server: Any, config: Any, builder: Any) -> Any:
    server.watch(roadmap_path(config))
    return server
