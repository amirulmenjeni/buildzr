"""Test-only launcher of an instance that accepts deploys, with a way to kill itself between two store steps.

The kill hook lives here, in the tests, and nowhere in ``buildzr``: no environment variable or flag of ``buildzr serve``
can enable it. Usage: ``python tests/site/deploy_instance.py STORE READ_PORT DEPLOY_PORT``; with
``BUILDZR_TEST_KILL_AT=<step>:<n>`` the process sends itself SIGKILL the n-th time the store reaches ``<step>``.
"""

from __future__ import annotations

import os
import signal
import sys

from buildzr.site.deploy import run_instance
from buildzr.site.store import Store

store = Store.open(sys.argv[1], create=True, exclusive=True)
kill_at = os.environ.get("BUILDZR_TEST_KILL_AT")
if kill_at:
    step, _, nth = kill_at.partition(":")
    seen = {"n": 0}

    def hook(name: str) -> None:
        if name == step:
            seen["n"] += 1
            if seen["n"] == int(nth or "1"):
                os.kill(os.getpid(), signal.SIGKILL)
    store.hook = hook
run_instance(store, port=int(sys.argv[2]), deploy_port=int(sys.argv[3]))
