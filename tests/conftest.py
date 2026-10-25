"""Keep the test suite off the network: theme icons come from an empty cache of this test session only.

A test that fetches icons fakes the upstream host (``buildzr.themes.assets._urlopen``) or fills the cache itself.
"""

import os
from typing import Iterator

import pytest


@pytest.fixture(autouse=True, scope="session")
def _no_icon_downloads(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in ("BUILDZR_OFFLINE", "BUILDZR_CACHE_DIR")}
    os.environ["BUILDZR_OFFLINE"] = "1"
    os.environ["BUILDZR_CACHE_DIR"] = str(tmp_path_factory.mktemp("buildzr-cache"))
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
