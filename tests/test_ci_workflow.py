"""The CI workflow gives the Python tests what they need, which is not in Git."""

from pathlib import Path
from typing import Any

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "build.yml"


def _steps(job: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"][job]["steps"]
    return steps


def test_the_viewer_is_built_before_the_python_tests() -> None:
    steps = _steps("tests")
    names = [s.get("name") for s in steps]
    build = steps[names.index("Build viewer")]
    assert "npm ci" in build["run"] and "npm run build" in build["run"]
    assert build["working-directory"] == "viewer"
    node = steps[names.index("Set up Node")]
    assert node["uses"].startswith("actions/setup-node@")
    assert names.index("Set up Node") < names.index("Build viewer") < names.index("Run tests")


def test_a_viewer_change_runs_the_python_tests() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    src = yaml.safe_load(text)["jobs"]["check_changes"]["steps"][1]["with"]["filters"]
    assert "viewer/**" in yaml.safe_load(src)["src"]
