"""The examples of the docs' browser demo (``docs/demo/samples.json``) and the size guard of ``run_snippet``."""

from __future__ import annotations

import json
import os

import pytest

from buildzr.site.browser import MAX_CODE, focus_for, run_code, run_snippet
from buildzr.site.levels import build_levels
from buildzr.site.model import DRAWN_TYPES, export_model
from tests.docs.blocks import DOCS

with open(os.path.join(DOCS, "demo", "samples.json"), encoding="utf-8") as f:
    SAMPLES = json.load(f)


def test_samples_have_the_shape_the_demo_reads() -> None:
    assert SAMPLES and all(set(s) == {"id", "title", "code"} for s in SAMPLES)
    assert len({s["id"] for s in SAMPLES}) == len(SAMPLES)
    assert all(isinstance(v, str) and v.strip() for s in SAMPLES for v in s.values())
    assert all(len(s["code"]) < 50_000 for s in SAMPLES), "the demo's editor limit"


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s["id"])
def test_every_sample_runs_and_has_something_to_draw(sample: dict[str, str]) -> None:
    workspace, _ = run_code(sample["code"])
    model = export_model(workspace)
    assert any(e["type"] in DRAWN_TYPES for e in model["elements"])
    assert build_levels(workspace, model, text_color="wcag")["levels"]
    assert focus_for(sample["code"], model)["route"].startswith("#/")


def test_the_deployment_sample_opens_on_its_deployment_view() -> None:
    sample = next(s for s in SAMPLES if s["id"] == "deployment")
    workspace, _ = run_code(sample["code"])
    assert focus_for(sample["code"], export_model(workspace))["route"].startswith("#/v/")


def test_run_snippet_refuses_code_over_the_limit() -> None:
    result = json.loads(run_snippet("x = 1\n" * MAX_CODE))
    assert result["ok"] is False and "the limit is" in result["error"]["message"]
