"""``buildzr serve --watch``: what is watched, the debounce, keeping the last good build, the viewer reload, shutdown."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

import pytest

import buildzr.site.cli as cli
from buildzr.site import watch
from buildzr.site.build import Entry, build_all
from buildzr.site.serve import BUILD_HEADER, LIVE_SCRIPT, make_server, with_live_script
from tests.site.test_broken import out_dir, static
from tests.site.test_build_all import HEAD, info, tree, ws
from tests.site.test_cli import ROOT, project, run, stubbed  # noqa: F401  (fixture)
from tests.site.test_serve import Server

DEADLINE = 30.0  # seconds a test waits for a rebuild before it fails; a passing run takes far less


def wait_for(condition: Callable[[], bool], what: str) -> None:
    end = time.monotonic() + DEADLINE
    while not condition():
        if time.monotonic() > end:
            raise AssertionError(f"timed out waiting for {what}")
        time.sleep(0.02)


# --- what is watched -------------------------------------------------------------------------------------


def test_the_watched_files_are_what_the_fingerprint_reads(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    tree(root, {"shop.py": "", "nested/billing.py": "", "_helpers.py": "", "nested/_more.py": "",
                "notes.md": "", "data.json": "", "shop.py~": "", ".#shop.py": "", ".shop.py.swp": "", "4913": "",
                "__pycache__/shop.cpython-313.pyc": "", "__pycache__/_x.py": "", ".hidden/hidden.py": "",
                "_private/skipped.py": "", "build/out.py": ""})
    config = tmp_path / "buildzr.yaml"
    config.write_text("")
    files = watch.watched_files([Entry(str(root))], str(root), str(config), skip=[str(root / "build")])
    assert [os.path.relpath(f, tmp_path).replace(os.sep, "/") for f in files] == [
        "buildzr.yaml", "workspaces/_helpers.py", "workspaces/nested/_more.py", "workspaces/nested/billing.py",
        "workspaces/shop.py"]


def test_a_single_file_entry_watches_it_and_the_helpers_beside_it(tmp_path: Path) -> None:
    tree(tmp_path, {"shop.py": "", "other.py": "", "_helpers.py": ""})
    files = watch.watched_files([Entry(str(tmp_path / "shop.py"))], str(tmp_path))
    assert files == [str(tmp_path / "_helpers.py"), str(tmp_path / "shop.py")]
    os.remove(tmp_path / "shop.py")  # a file deleted while watched: gone from the list, so its signature changes
    assert watch.watched_files([Entry(str(tmp_path / "shop.py"))], str(tmp_path)) == [str(tmp_path / "_helpers.py")]


def test_signature_and_changed(tmp_path: Path) -> None:
    a, b, c = tmp_path / "a.py", tmp_path / "b.py", tmp_path / "c.py"
    a.write_text("1")
    b.write_text("1")
    before = watch.signature([str(a), str(b), str(c)])
    assert set(before) == {str(a), str(b)}  # c does not exist
    b.write_text("22")
    os.remove(a)
    c.write_text("1")
    after = watch.signature([str(a), str(b), str(c)])
    assert watch.changed(before, after) == {str(a), str(b), str(c)}
    assert watch.changed(after, watch.signature([str(a), str(b), str(c)])) == set()


def test_a_file_saved_by_rename_is_a_change(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    a.write_text("one")
    before = watch.signature([str(a)])
    tmp = tmp_path / ".a.py.tmp"
    tmp.write_text("two")  # the same size; the mtime can be the same on a coarse clock
    os.replace(tmp, a)
    os.utime(a, ns=(before[str(a)][0], before[str(a)][0]))
    assert watch.changed(before, watch.signature([str(a)])) == {str(a)}


# --- the debounce, with a scripted clock -------------------------------------------------------------------


class Script:
    """A scan that returns the given signatures one after another (the last one forever), and a sleep that logs."""

    def __init__(self, *states: dict[str, int]) -> None:
        self.states = [{f: (v, 0, 0) for f, v in s.items()} for s in states]
        self.scans = 0
        self.slept: list[float] = []
        self.calls: list[set[str]] = []

    def scan(self) -> watch.Signature:
        i = min(self.scans, len(self.states) - 1)
        self.scans += 1
        return self.states[i]

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)

    def watcher(self, on_change: Optional[Callable[[set[str]], None]] = None) -> watch.Watcher:
        return watch.Watcher(self.scan, on_change or self.calls.append, interval=0.5, settle=0.3, sleep=self.sleep)

    def stop_after(self, scans: int) -> Callable[[], bool]:
        return lambda: self.scans >= scans


def test_no_change_no_build() -> None:
    s = Script({"a.py": 1})
    s.watcher().run(stop=s.stop_after(5))
    assert s.calls == [] and s.slept == [0.5] * 4


def test_a_burst_of_writes_gives_one_build_of_the_last_state() -> None:
    seen: list[watch.Signature] = []
    s = Script({"a.py": 1}, {"a.py": 2}, {"a.py": 3}, {"a.py": 4, "b.py": 1}, {"a.py": 5, "b.py": 1},
               {"a.py": 5, "b.py": 1})

    def on_change(files: set[str]) -> None:
        seen.append(s.states[min(s.scans - 1, len(s.states) - 1)])
        s.calls.append(files)
    s.watcher(on_change).run(stop=s.stop_after(9))
    assert s.calls == [{"a.py", "b.py"}]
    assert seen == [{"a.py": (5, 0, 0), "b.py": (1, 0, 0)}]  # built once the scans agreed, with the last state
    assert s.slept[:5] == [0.5, 0.3, 0.3, 0.3, 0.3]


def test_a_change_made_during_a_build_builds_again() -> None:
    s = Script({"a.py": 1}, {"a.py": 2}, {"a.py": 2})

    def on_change(files: set[str]) -> None:
        s.calls.append(files)
        if len(s.calls) == 1:  # the file is saved again while the first build runs
            s.states = s.states[:s.scans] + [{"a.py": (3, 0, 0)}]
    s.watcher(on_change).run(stop=s.stop_after(8))
    assert s.calls == [{"a.py"}, {"a.py"}]


def test_the_signature_before_the_first_build_is_the_starting_point() -> None:
    s = Script({"a.py": 2})
    s.watcher().run(last={"a.py": (1, 0, 0)}, stop=s.stop_after(4))  # changed while the build at start ran
    assert s.calls == [{"a.py"}]


def test_stop_while_settling_builds_nothing() -> None:
    s = Script({"a.py": 1}, {"a.py": 2}, {"a.py": 3}, {"a.py": 4})
    s.watcher().run(stop=s.stop_after(3))
    assert s.calls == []


def test_real_files_are_seen_and_debounced(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    a.write_text("0")
    calls: list[set[str]] = []
    done = threading.Event()
    w = watch.Watcher(lambda: watch.signature([str(a)]), calls.append, interval=0.05, settle=0.4)
    t = threading.Thread(target=w.run, kwargs={"stop": done.is_set}, daemon=True)
    t.start()
    try:
        time.sleep(0.2)
        for i in range(5):  # faster than the settle time
            a.write_text("x" * (i + 1))
            time.sleep(0.05)
        wait_for(lambda: bool(calls), "the build")
        time.sleep(0.6)
        assert calls == [{str(a)}]
    finally:
        done.set()
        t.join(5)
    assert not t.is_alive()


# --- keeping the last good build -----------------------------------------------------------------------------


def _build(root: Path, tmp_path: Path, keep_good: bool = True, **kw: Any) -> Any:
    viewer = tmp_path / "static"
    return build_all(str(root / "workspaces"), str(out_dir(root)), keep_good=keep_good, only_stale=True,
                     static_dir=str(viewer) if viewer.is_dir() else static(tmp_path), **kw)


def _files(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


@pytest.mark.usefixtures("stubbed")
def test_a_model_error_keeps_the_good_build(tmp_path: Path) -> None:
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A")})
    assert [b.name for b in _build(root, tmp_path).built] == ["a"]
    good = _files(out_dir(root) / "a")
    (root / "workspaces" / "a.py").write_text(HEAD + ws("A") + "raise RuntimeError('boom')\n")
    result = _build(root, tmp_path)
    assert (result.built, result.broken, [b.name for b in result.kept]) == ([], [], ["a"])
    assert result.kept[0].info["stage"] == "model" and "boom" in str(result.kept[0].info["errors"])
    assert _files(out_dir(root) / "a") == good  # byte for byte
    assert sorted(os.listdir(out_dir(root))) == ["a"]  # no staging folder left behind
    (root / "workspaces" / "a.py").write_text(HEAD + ws("A", "Fixed"))  # recovery
    result = _build(root, tmp_path)
    assert [b.name for b in result.built] == ["a"] and info(root, "a")["status"] == "ok"
    assert _files(out_dir(root) / "a") != good


@pytest.mark.usefixtures("stubbed")
def test_without_a_good_build_the_broken_one_is_written(tmp_path: Path) -> None:
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A") + "raise RuntimeError('boom')\n"})
    result = _build(root, tmp_path)
    assert [b.name for b in result.broken] == ["a"] and result.kept == []
    assert info(root, "a")["status"] == "broken"
    (root / "workspaces" / "a.py").write_text(HEAD + ws("A") + "raise RuntimeError('boom again')\n")
    result = _build(root, tmp_path)  # broken replaces broken: the viewer shows the new error
    assert [b.name for b in result.broken] == ["a"] and "boom again" in str(info(root, "a")["errors"])


@pytest.mark.usefixtures("stubbed")
def test_a_layout_failure_keeps_that_good_build_and_writes_the_others(tmp_path: Path,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.site.stub_layout import stub_layout
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"two.py": HEAD + ws("Fine") + ws("Tangled")})
    _build(root, tmp_path, layout_fn=stub_layout)
    tangled = _files(out_dir(root) / "tangled")

    def layout(levels: Any, model: Any, data_dir: str, k: int = 4) -> None:
        if model["workspace"]["name"] == "Tangled":
            raise ValueError("does not converge")
        stub_layout(levels, model, data_dir, k=k)
    (root / "workspaces" / "two.py").write_text(HEAD + ws("Fine", "Changed") + ws("Tangled", "Changed"))
    result = _build(root, tmp_path, layout_fn=layout, prune=True)
    assert ([b.name for b in result.built], [b.name for b in result.kept], result.removed) == (["fine"], ["tangled"], [])
    assert result.kept[0].info["stage"] == "layout"
    assert _files(out_dir(root) / "tangled") == tangled


@pytest.mark.usefixtures("stubbed")
def test_without_keep_good_a_broken_build_still_replaces_the_good_one(tmp_path: Path) -> None:
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A")})
    _build(root, tmp_path, keep_good=False)
    (root / "workspaces" / "a.py").write_text(HEAD + ws("A") + "raise RuntimeError('boom')\n")
    result = _build(root, tmp_path, keep_good=False)
    assert [b.name for b in result.broken] == ["a"] and result.kept == [] and info(root, "a")["status"] == "broken"


# --- the viewer reload ------------------------------------------------------------------------------------


def test_the_script_goes_before_the_end_of_head() -> None:
    page = with_live_script(b"<html><head><title>x</title></HEAD><body></body></html>", "abc")
    assert page.index(b"<script>") < page.index(b"</HEAD>") and b'var token = "abc";' in page
    assert with_live_script(b"<body>x</body>", None).endswith(b"</script>\n</body>")
    assert with_live_script(b"<p>x", None).startswith(b"<p>x<script>")
    assert BUILD_HEADER in LIVE_SCRIPT % ("null", BUILD_HEADER)


@pytest.mark.usefixtures("stubbed")
def test_the_viewer_reloads_only_in_watch_mode(tmp_path: Path) -> None:
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A")})
    _build(root, tmp_path)
    page = (out_dir(root) / "a" / "index.html").read_bytes()
    plain, live = Server(out_dir(root)), Server(out_dir(root), live=True)
    try:
        for path in ("/a/", "/a/index.html"):
            assert plain.get(path)[2] == page  # ordinary serve: the file as it is
        status, headers, body = plain.get("/a/build.json")
        assert status == 200 and BUILD_HEADER not in headers
        status, headers, body = live.get("/a/build.json")
        token = headers[BUILD_HEADER]
        assert status == 200 and len(token) == 32
        for path in ("/a/", "/a/index.html"):
            status, headers, body = live.get(path)
            assert status == 200 and headers["Content-Type"] == "text/html; charset=utf-8"
            assert body == with_live_script(page, token) and f'var token = "{token}";'.encode() in body
            assert headers["X-Buildzr-Workspaces"] == "../_buildzr/v1/workspaces"
        status, headers, body = live.get("/a/assets/" + os.listdir(out_dir(root) / "a" / "assets")[0])
        assert status == 200 and b"buildzr serve --watch" not in body
        (root / "workspaces" / "a.py").write_text(HEAD + ws("A", "Changed"))
        _build(root, tmp_path)
        assert live.get("/a/build.json")[1][BUILD_HEADER] != token  # what makes the open page reload
        assert live.get("/a/")[2] != body
    finally:
        plain.close()
        live.close()


@pytest.mark.usefixtures("stubbed")
def test_a_data_only_workspace_gets_no_script(tmp_path: Path) -> None:
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A")})
    build_all(str(root / "workspaces"), str(out_dir(root)), viewer=False)
    live = Server(out_dir(root), live=True)
    try:
        assert live.get("/a/")[0] == 404
        assert live.get("/a/build.json")[0] == 200
    finally:
        live.close()


# --- the command ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("argv, message", [
    (["serve", "--watch", "--no-build"], "--no-build and --watch cannot be used together"),
    (["serve", "--watch", "built"], "built holds built workspaces, which are served as they are; --watch needs"),
    (["serve", "--watch", "--example"], "--example serves the bundled example, so it cannot be used with --watch"),
])
def test_watch_conflicts_are_usage_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                          capsys: pytest.CaptureFixture[str], argv: list[str], message: str) -> None:
    root = project(tmp_path)
    (root / "built" / "w" / "data").mkdir(parents=True)
    (root / "built" / "w" / "data" / "index.json").write_text("{}")
    (root / "built" / "w" / "build.json").write_text("{}")
    code, _, err = run(root, monkeypatch, capsys, *argv)
    assert code == 2 and message in err


def test_watch_is_in_the_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["serve", "--help"]) == 0
    assert "--watch" in capsys.readouterr().out


class Session:
    """``buildzr serve --watch`` run by :func:`cli.main` in a thread, with a real server and fast scans.

    ``cli.serve`` is replaced by one that starts the server on a free port and runs the watch until :meth:`stop`.
    """

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch, *argv: str) -> None:
        self.cycles = 0
        self.done = threading.Event()
        self.ready = threading.Event()
        self.server: Optional[Server] = None
        real_rebuild, real_run = cli._rebuild, watch.Watcher.run

        def rebuild(*a: Any) -> None:
            real_rebuild(*a)
            self.cycles += 1
        monkeypatch.setattr(cli, "_rebuild", rebuild)

        def fast_run(w: watch.Watcher, last: Optional[watch.Signature] = None,
                     stop: Callable[[], bool] = lambda: False) -> None:
            w.interval, w.settle = 0.05, 0.1
            real_run(w, last, stop=self.done.is_set)
        monkeypatch.setattr(watch.Watcher, "run", fast_run)

        def fake_serve(directory: str, *a: Any, watch: Optional[Callable[[], None]] = None, **kw: Any) -> None:
            assert watch is not None
            self.server = Server(Path(directory), live=True)
            self.ready.set()
            try:
                watch()
            finally:
                self.server.close()
        monkeypatch.setattr(cli, "serve", fake_serve)
        monkeypatch.chdir(root)
        self.code: Optional[int] = None
        self.thread = threading.Thread(target=self._main, args=(list(argv),), daemon=True)
        self.thread.start()
        wait_for(lambda: self.ready.is_set() or self.code is not None, "the server")

    def _main(self, argv: list[str]) -> None:
        self.code = cli.main(argv)

    def after(self, change: Callable[[], object]) -> None:
        """Make ``change`` and wait until the rebuild it starts has finished."""
        before = self.cycles
        time.sleep(0.05)
        change()
        wait_for(lambda: self.cycles > before, "the rebuild")

    def token(self, name: str) -> str:
        assert self.server is not None
        return self.server.get(f"/{name}/build.json")[1][BUILD_HEADER]

    def stop(self) -> int:
        self.done.set()
        self.thread.join(DEADLINE)
        assert not self.thread.is_alive() and self.code is not None
        return self.code


@pytest.mark.usefixtures("stubbed")
def test_serve_watch_rebuilds_keeps_the_good_build_and_recovers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A"), "b.py": HEAD + ws("B")})
    s = Session(root, monkeypatch, "serve", "--watch")
    try:
        out = capsys.readouterr().out
        assert "built .buildzr/build/a (" in out and "built .buildzr/build/b (" in out
        a, b = s.token("a"), s.token("b")

        s.after(lambda: (root / "workspaces" / "a.py").write_text(HEAD + ws("A", "Changed")))
        out = capsys.readouterr().out
        assert "changed: workspaces/a.py\n" in out and "reloading the open viewers of a\n" in out
        assert "built .buildzr/build/a (" in out and "built .buildzr/build/b (" not in out  # only what is stale
        assert s.token("a") != a and s.token("b") == b
        a = s.token("a")

        s.after(lambda: (root / "workspaces" / "a.py").write_text(HEAD + ws("A") + "raise RuntimeError('boom')\n"))
        cap = capsys.readouterr()
        assert "buildzr: BROKEN: workspace a (workspaces/a.py) failed at the model step" in cap.err
        assert "RuntimeError: boom" in cap.err and "the last good build is still served" in cap.err
        assert "reloading" not in cap.out
        assert s.token("a") == a and info(root, "a")["status"] == "ok"  # the open viewer stays as it was

        s.after(lambda: (root / "workspaces" / "_shared.py").write_text("X = 1\n"))  # a helper: both are stale
        cap = capsys.readouterr()
        assert "changed: workspaces/_shared.py\n" in cap.out and "built .buildzr/build/b (" in cap.out
        assert "RuntimeError: boom" in cap.err and s.token("a") == a  # still broken, still kept

        s.after(lambda: (root / "workspaces" / "a.py").write_text(HEAD + ws("A", "Fixed")))
        out = capsys.readouterr().out
        assert "built .buildzr/build/a (" in out and "reloading the open viewers of a\n" in out
        assert s.token("a") != a and info(root, "a")["status"] == "ok"

        s.after(lambda: (root / "workspaces" / "c.py").write_text(HEAD + ws("C")))  # a new file
        assert "built .buildzr/build/c (" in capsys.readouterr().out
        s.after(lambda: os.remove(root / "workspaces" / "c.py"))  # and gone again
        assert "removed c: its model file workspaces/c.py is gone" in capsys.readouterr().out

        def unrelated() -> None:  # a file that is not watched, and a model file touched but not changed
            (root / "workspaces" / "notes.md").write_text("x")
            os.utime(root / "workspaces" / "a.py")
        s.after(unrelated)
        assert "nothing to rebuild: every built workspace is up to date" in capsys.readouterr().out
    finally:
        assert s.stop() == 0


@pytest.mark.usefixtures("stubbed")
def test_serve_watch_says_a_config_change_needs_a_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                          capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {k: 4}\n", ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A")})
    s = Session(root, monkeypatch, "serve", "--watch")
    try:
        capsys.readouterr()
        s.after(lambda: (root / "buildzr.yaml").write_text("build: {k: 5}\n"))
        cap = capsys.readouterr()
        assert "buildzr.yaml changed; restart buildzr serve --watch to use its new settings" in cap.err
        assert "built" not in cap.out
    finally:
        assert s.stop() == 0


@pytest.mark.usefixtures("stubbed")
def test_serve_watch_starts_with_nothing_built_and_waits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                         capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"a.py": "X = 1\n"})
    s = Session(root, monkeypatch, "serve", "--watch")
    try:
        out = capsys.readouterr().out
        assert "skipped workspaces/a.py: it creates no workspace" in out
        assert "nothing built yet in .buildzr/build; waiting for a model file to change" in out
        s.after(lambda: (root / "workspaces" / "a.py").write_text(HEAD + ws("A")))
        assert "built .buildzr/build/a (" in capsys.readouterr().out
    finally:
        assert s.stop() == 0


@pytest.mark.usefixtures("stubbed")
def test_a_bug_in_a_rebuild_keeps_the_watch_going(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A")})
    s = Session(root, monkeypatch, "serve", "--watch")
    real = cli.build_all
    try:
        monkeypatch.setattr(cli, "build_all", lambda *a, **kw: (_ for _ in ()).throw(ValueError("a bug")))
        s.after(lambda: (root / "workspaces" / "a.py").write_text(HEAD + ws("A", "x")))
        assert "buildzr: error: the rebuild failed: ValueError: a bug" in capsys.readouterr().err
        monkeypatch.setattr(cli, "build_all", real)
        s.after(lambda: (root / "workspaces" / "a.py").write_text(HEAD + ws("A", "y")))
        assert "built .buildzr/build/a (" in capsys.readouterr().out
    finally:
        assert s.stop() == 0


def test_ordinary_serve_does_not_watch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str], stubbed: None) -> None:  # noqa: F811
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(cli, "serve", lambda *a, **kw: calls.append(kw))
    root = project(tmp_path, "build: {viewer: false}\n")
    code, _, _ = run(root, monkeypatch, capsys, "serve", "ws")
    assert code == 0 and calls == [{"shown": ".buildzr/build"}]  # no watch=, so no live script and no thread


# --- shutdown, in a real process --------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # a zombie nobody has reaped yet (a container's PID 1 may not) is gone too
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            return f.read().split(") ", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return True


@pytest.fixture
def watching(tmp_path: Path) -> Iterator[tuple[subprocess.Popen[str], Path]]:
    """``buildzr serve --watch`` in its own process, with a model file that creates no workspace yet."""
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"a.py": "X = 1\n"})
    env = {**os.environ, "PYTHONPATH": ROOT, "NO_COLOR": "1"}
    proc = subprocess.Popen([sys.executable, "-m", "buildzr.site.cli", "serve", "--watch", "-p", str(_free_port())],
                            cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        yield proc, root
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.communicate(timeout=DEADLINE)


@pytest.mark.skipif(sys.platform == "win32", reason="sends POSIX signals to one process")
@pytest.mark.parametrize("sig", ["SIGINT", "SIGTERM"])
def test_a_signal_stops_the_watch_the_server_and_a_running_build(
        watching: tuple[subprocess.Popen[str], Path], sig: str) -> None:
    proc, root = watching
    pid_file = root / "child.pid"
    assert proc.stdout is not None
    lines: list[str] = []

    def read() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
    threading.Thread(target=read, daemon=True).start()
    wait_for(lambda: any(l.startswith("Watching ") for l in lines), "the watch to start: " + "".join(lines))
    (root / "workspaces" / "a.py").write_text(  # a model file that runs until it is stopped
        f"import os, time\nopen({str(pid_file)!r}, 'w').write(str(os.getpid()))\ntime.sleep(600)\n")
    wait_for(lambda: pid_file.is_file() and pid_file.read_text() != "", "the model file to run")
    child = int(pid_file.read_text())
    assert _alive(child)
    proc.send_signal(getattr(signal, sig))  # to the parent only, as a service manager would
    assert proc.wait(DEADLINE) == 0, "".join(lines)
    wait_for(lambda: not _alive(child), "the model file's process to stop")
    assert "Traceback" not in "".join(lines)
    assert os.listdir(root / ".buildzr" / "build") == []  # nothing half-written left in the output
