"""``buildzr serve --watch``: look at the model files every half second, wait until they settle, then rebuild.

Standard library only. There are no file-system events: a scan of the ``stat`` of a few files works the same on every
system and in mounted folders (containers, network drives), and the build's fingerprint (see
:func:`buildzr.site.build.fingerprint`) decides what is really stale, so a touched but unchanged file builds nothing.

The watched files are those the fingerprint reads: every Python file the build runs and every ``_*.py`` helper of the
workspaces folder, plus ``buildzr.yaml``. Editor swap and backup files, ``__pycache__``, hidden folders and the build
output are not among them, so neither saving with an editor nor writing the build output starts another build.
"""

from __future__ import annotations

import os
import time
from typing import Callable, Iterable, Optional, Sequence

from buildzr.site.build import Entry, find_helpers, find_sources

#: Each watched file and its ``(mtime_ns, size, inode)``; saving by writing a copy and renaming it gives a new inode.
Signature = dict[str, tuple[int, int, int]]

INTERVAL = 0.5  # seconds between two scans
SETTLE = 0.3  # seconds the files must stay the same before a build starts


def watched_files(entries: Sequence[Entry], root: str, config: Optional[str] = None,
                  skip: Iterable[str] = ()) -> list[str]:
    """The files whose change can change a built workspace of ``entries`` (absolute paths, sorted).

    Each entry's Python files (:func:`buildzr.site.build.find_sources`), the ``_*.py`` helpers of its workspaces folder
    (``helpers``, else ``root``), and ``config``. Nothing below a folder of ``skip`` (the build output).
    """
    skipped = [os.path.abspath(s) for s in skip]
    files: set[str] = set()
    for e in entries:
        files.update(find_sources(e.path))
        files.update(find_helpers(e.helpers if e.helpers is not None else root))
    if config is not None:
        files.add(os.path.abspath(config))
    return sorted(f for f in files if not any(f == s or f.startswith(s + os.sep) for s in skipped))


def signature(files: Iterable[str]) -> Signature:
    """The ``stat`` of each file that exists."""
    out: Signature = {}
    for f in files:
        try:
            st = os.stat(f)
        except OSError:
            continue
        out[f] = (st.st_mtime_ns, st.st_size, st.st_ino)
    return out


def changed(before: Signature, after: Signature) -> set[str]:
    """The files added, removed or changed between two signatures."""
    return {f for f in before.keys() | after.keys() if before.get(f) != after.get(f)}


class Watcher:
    """Calls ``on_change`` with the changed files once they have settled, one call at a time.

    ``scan`` gives the current :data:`Signature`. After a change, the files are scanned every ``settle`` seconds until
    two scans in a row agree, so a burst of writes (an editor that saves in several steps, a formatter run after the
    save) gives one build of the last state. A change made while ``on_change`` runs is seen by the next scan, because
    it is compared with the signature taken before the call. ``sleep`` and ``stop`` let a test drive the loop.
    """

    def __init__(self, scan: Callable[[], Signature], on_change: Callable[[set[str]], None],
                 interval: float = INTERVAL, settle: float = SETTLE,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.scan = scan
        self.on_change = on_change
        self.interval = interval
        self.settle = settle
        self.sleep = sleep

    def run(self, last: Optional[Signature] = None, stop: Callable[[], bool] = lambda: False) -> None:
        """Watch until ``stop()`` is true (or Ctrl+C), starting from ``last`` (default: a scan now)."""
        if last is None:
            last = self.scan()
        while not stop():
            self.sleep(self.interval)
            current = self.scan()
            if current == last:
                continue
            while not stop():
                self.sleep(self.settle)
                later = self.scan()
                if later == current:
                    break
                current = later
            else:
                return
            self.on_change(changed(last, current))
            last = current
