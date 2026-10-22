"""The browser demo (``docs/demo.md``) in Chromium on a built copy of the docs: nothing is loaded before the first run,
the model is built and drawn, a second run keeps the viewer, errors name their line, the time limit and Stop end a run
and the demo recovers, the draft is restored but never run, the layout works on a phone, offline and without a Web
Worker the demo says so, and axe-core finds no WCAG A/AA violation. Skipped (with the reason) where no browser, Node
or network is available."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

import pytest

from tests.docs.browser import browser_problem, build_docs, run_node, serve

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_browser.mjs")

pytestmark = pytest.mark.skipif(browser_problem() is not None, reason=f"demo browser test: {browser_problem()}")

Json = dict[str, Any]


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> Iterator[list[Json]]:
    site = build_docs(tmp_path_factory.mktemp("docs"))
    with serve(site) as url:
        yield run_node("demo", url, [], timeout=900, script=SCRIPT)


def check(lines: list[Json], name: str) -> list[Json]:
    found = [x for x in lines if x.get("check") == name]
    assert found, f"no {name!r} in {lines}"
    return found


def test_nothing_is_loaded_before_the_first_run(demo: list[Json]) -> None:
    before = check(demo, "before the first press")[0]
    assert before["runcode"] == [] and before["cdn"] == 0
    assert before["label"] == "Model (Python)" and before["described"] == "demo-hint"
    assert "Workspace('Shop')" in before["value"], "the first example is in the editor"
    assert before["options"] == ["Choose…", "A shop with containers", "The smallest model", "A shop in production"]
    assert before["status"] == "status" and before["stopDisabled"]


def test_first_run_draws_and_keeps_the_focus_in_the_editor(demo: list[Json]) -> None:
    first = check(demo, "first run")[0]
    assert first["state"] == "drawn" and first["nodes"] and first["status"] == "Diagram ready.", first
    assert first["focus"] == "demo-code", "running does not take the focus away from the editor"
    assert first["frameSrc"].startswith("index.html?embed=1&theme=light#/m/"), first["frameSrc"]
    assert first["thread"] == "worker" and first["busy"] is None
    assert first["json"] == "Show model JSON"
    assert first["runcodeRequests"] > 0


def test_second_run_updates_the_same_viewer(demo: list[Json]) -> None:
    second = check(demo, "second run")[0]
    assert second["state"] == "drawn" and second["updated"], second
    assert second["sameFrame"] and second["frameCount"] == 1, "the viewer is not reloaded"


def test_error_names_its_line_and_selects_it(demo: list[Json]) -> None:
    err = check(demo, "error")[0]
    assert err["line"] == "3" and "Error on line 3." in err["text"] and "NameError: name 'sytem' is not defined" in err["text"], err
    assert "Traceback" not in err["text"]
    assert err["selected"] == "user >> 'uses' >> sytem" and err["focus"] == "demo-code"
    assert err["role"] == "alert" and err["diagramKept"], "the last diagram stays while the code is wrong"


def test_nothing_to_draw_and_no_code(demo: list[Json]) -> None:
    both = check(demo, "nothing and empty")[0]
    assert "nothing to draw" in both["nothing"] and "There is no code to run." in both["empty"], both


def test_printed_output_and_model_json(demo: list[Json]) -> None:
    extras = check(demo, "extras")[0]
    assert extras["printed"] == "Show printed output" and extras["copiedIsJson"], extras


def test_examples_and_reset(demo: list[Json]) -> None:
    ex = check(demo, "examples")[0]
    assert ex["loaded"] and ex["reset"] and ex["pickBack"] == "", ex


def test_the_viewer_follows_the_docs_theme(demo: list[Json]) -> None:
    theme = check(demo, "theme")[0]
    assert theme["scheme"] == "slate" and theme["frameTheme"] == "dark", theme


def test_the_draft_is_restored_and_never_run(demo: list[Json]) -> None:
    draft = check(demo, "draft")[0]
    assert draft["restored"] == "draft = 1\n# a draft of mine", draft
    assert draft["state"] == "idle" and draft["newRunCodeRequests"] == 0 and draft["frames"] == 0, draft


def test_no_accessibility_violations(demo: list[Json]) -> None:
    assert check(demo, "axe")[0]["violations"] == []


def test_a_loop_that_never_ends_is_stopped_and_the_demo_recovers(demo: list[Json]) -> None:
    limit = check(demo, "time limit")[0]
    assert "took too long" in limit["timedOut"] and "more than 4 seconds" in limit["timedOut"], limit
    assert limit["stillResponsive"] == 2 and limit["afterwards"] == "drawn" and limit["runIsEnabled"] == "false", limit


@pytest.mark.parametrize("index, how", [(0, "button"), (1, "escape")])
def test_stop_button_and_escape(demo: list[Json], index: int, how: str) -> None:
    stop = check(demo, "stop")[index]
    assert stop["how"] == how and stop["status"] == "Stopped." and stop["stopDisabled"], stop
    assert stop["problem"] == "" and stop["thenDrawn"] == "drawn", stop


def test_phone_layout(demo: list[Json]) -> None:
    phone = check(demo, "phone")[0]
    assert phone["stacked"] and not phone["overflowX"] and not phone["after"]["overflowX"], phone
    assert phone["fontSize"] == "16px", "a smaller editor makes iOS zoom in"
    assert phone["small"] == [], f"touch targets under 40px: {phone['small']}"
    assert phone["after"]["viewerInView"] and phone["after"]["backShown"] and phone["nodes"], phone
    assert phone["backFocus"] == "demo-code"


def test_offline_the_demo_says_so_and_recovers(demo: list[Json]) -> None:
    off = check(demo, "offline")[0]
    assert off["note"] and "You are offline" in off["note"], off
    assert "could not start" in off["failed"] and "cdn.jsdelivr.net" in off["failed"] and off["editable"], off
    assert off["afterwards"] == "drawn" and off["noteGone"], off


def test_without_a_web_worker_it_refuses_to_run(demo: list[Json]) -> None:
    text = check(demo, "no worker")[0]["text"]
    assert "cannot run in this browser" in text and "Web Worker" in text, text


def test_no_page_errors(demo: list[Json]) -> None:
    for name in ("wide", "loop", "phone", "offline"):
        assert check(demo, f"page errors {name}")[0]["errors"] == [], name


def test_the_demo_page_is_in_the_docs(tmp_path: Path) -> None:
    site = build_docs(tmp_path)
    html = (site / "demo" / "index.html").read_text(encoding="utf-8")
    assert 'id="buildzr-demo"' in html and "javascripts/runcode-client.js" in html and "javascripts/demo.js" in html
    assert html.index("runcode-client.js") < html.index("interactive-code.js") < html.index("demo.js")
    assert (site / "demo" / "samples.json").is_file()
