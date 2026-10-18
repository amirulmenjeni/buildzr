"""Every example in the Publishing pages runs: configs load, commands print what the page shows, API answers match.

Conventions of the pages (the ``<!-- doctest: ... -->`` line goes just before the fenced block):

* a ``yaml`` block is a ``buildzr.yaml``; it must load. After ``invalid`` it must fail with the lines the next block
  quotes. It becomes the config of the commands that follow on the same page.
* a ``text`` block that starts with ``$ buildzr ...`` is run in a folder made for the page; the lines after each ``$``
  line are the expected output (hashes, paths, ports, sizes and timings are normalised; ``...`` stands for any lines)
  and a line ``[exit code N]`` states the exit code (else it must be 0).
* ``file PATH`` writes the next block to PATH of that folder (the model of the page).
* an ``http`` block ``GET /path`` is sent to a live server; the ``json`` block after it is compared with the answer
  (same keys, same types, same values unless the directive is ``shape``).
* ``api NAME`` chooses the server of an ``http`` block: ``example`` (default), ``data-only``
  or ``instance`` (the instance that the commands of the page deployed to).
* ``merge`` (before a ``yaml`` block): its targets are added to the config of the page instead of replacing it.
* ``audit`` (before a ``json`` block): the block is a line of ``deploys.log``; it is compared, by shape, with the
  first line the instance of the page wrote.
* ``skip REASON`` opts a block out; the reasons are listed by ``test_opt_outs_are_few_and_listed``.
"""

from __future__ import annotations

import http.client
import io
import json
import os
import re
import shlex
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterator, Optional

import pytest

import buildzr.site.cli as cli
from buildzr.site.build import STATIC_DIR, build_site
from buildzr.site.config import ConfigError, load_config
from buildzr.site.serve import make_server
from tests.docs.blocks import PAGES, ROOT, Block, compare_json, extract_blocks, same_lines
from tests.site.deploy_helpers import Instance
from tests.site.stub_layout import stub_layout
from tests.site.test_cli import make_static

EXAMPLE_PY = os.path.join(ROOT, "examples", "buildzr_models_example.py")
HAS_NODE = bool(shutil.which("node") or os.environ.get("BUILDZR_NODE"))
REAL = HAS_NODE and os.path.isfile(os.path.join(STATIC_DIR, "index.html")) and not os.environ.get("BUILDZR_DOCTEST_STUB")
PUBLIC = "https://preview.example.com"
MAX_OPT_OUTS = 8

Json = dict[str, Any]


def all_blocks() -> list[Block]:
    return [b for page in PAGES for b in extract_blocks(page)]


def is_command_block(b: Block) -> bool:
    return b.lang == "text" and b.text.startswith("$ ")


# --- running commands -------------------------------------------------------------------------------------


def run_cli(argv: list[str], cwd: Path, env: dict[str, str]) -> tuple[int, str]:
    """``buildzr.site.cli.main`` in this process, with stdout and stderr (and the child processes') in one file."""
    with tempfile.TemporaryFile() as sink:
        saved = (os.dup(1), os.dup(2), os.getcwd(), dict(os.environ))
        old = (cli.sys.stdout, cli.sys.stderr)
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
        merged = io.TextIOWrapper(io.FileIO(os.dup(sink.fileno()), "w"), write_through=True)
        cli.sys.stdout = cli.sys.stderr = merged
        os.chdir(cwd)
        os.environ.update(env)
        try:
            code = cli.main(argv)
        finally:
            merged.flush()
            cli.sys.stdout, cli.sys.stderr = old
            os.dup2(saved[0], 1)
            os.dup2(saved[1], 2)
            os.close(saved[0])
            os.close(saved[1])
            os.chdir(saved[2])
            os.environ.clear()
            os.environ.update(saved[3])
        sink.seek(0)
        return code, sink.read().decode("utf-8")


class Page:
    """The folder and the state shared by the commands of one page."""

    def __init__(self, name: str, root: Path, instance: Optional[Instance]) -> None:
        self.name = name
        self.dir = root / name.replace(".", "-")
        self.dir.mkdir()
        (self.dir / ".git").mkdir()  # so that the config search stops here
        (self.dir / "examples").mkdir()
        shutil.copy(EXAMPLE_PY, self.dir / "examples")  # the model that model-api.md builds
        self.instance = instance
        self.urls = False
        self.config_text = ""

    def path(self, p: str) -> Path:
        return self.dir / p.lstrip("/")

    def write_config(self, text: str, merge: bool = False) -> None:
        if merge and (self.dir / "buildzr.yaml").exists():  # `merge`: the targets are added to the page's config
            import yaml
            old = yaml.safe_load(self.config_text)
            new = yaml.safe_load(text)
            old["targets"] = {**old.get("targets", {}), **new.get("targets", {})}
            text = yaml.safe_dump(old, sort_keys=False)
        self.config_text = text
        def url(m: re.Match[str]) -> str:
            assert self.instance is not None
            self.urls = True
            return f"http://127.0.0.1:{self.instance.port}"

        text = re.sub(r"http://127\.0\.0\.1:\d+", url, text)
        text = re.sub(r"(\bdir:\s*)(\"?)(/[^\s,}\"]+)", lambda m: f"{m.group(1)}{m.group(2)}{self.path(m.group(3))}", text)
        (self.dir / "buildzr.yaml").write_text(text, encoding="utf-8")

    def argv(self, tokens: list[str]) -> list[str]:
        out = [str(self.path(t)) if t.startswith("/") else t for t in tokens]
        if out[0] == "serve":
            if "-p" not in out and "--port" not in out:
                out += ["-p", "0"]
            if "--accept-deploys" in out and "--deploy-port" not in out:
                out += ["--deploy-port", "0"]
        return out


@pytest.fixture(scope="module")
def work(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    root = tmp_path_factory.mktemp("docs")
    state: dict[str, Any] = {"root": root, "pages": {}, "instances": []}
    yield state
    for inst in state["instances"]:
        inst.close()


def page_of(work: dict[str, Any], name: str) -> Page:
    if name not in work["pages"]:
        inst = Instance(work["root"] / (name.replace(".", "-") + "-store"), public_url=PUBLIC)
        work["instances"].append(inst)
        work["pages"][name] = Page(name, work["root"], inst)
    page: Page = work["pages"][name]
    return page


def stop_at_once(self: Any, *args: Any, **kw: Any) -> None:
    """``serve_forever`` that returns as if Ctrl+C was pressed (``shutdown`` waits for this event)."""
    self._BaseServer__is_shut_down.set()


def parse_steps(text: str) -> list[tuple[str, list[str], Optional[int]]]:
    """``(command line, expected output lines, exit code or None)`` for every ``$`` line of a command block."""
    steps: list[tuple[str, list[str], Optional[int]]] = []
    for line in text.rstrip("\n").split("\n"):
        if line.startswith("$ "):
            if steps and not steps[-1][1][-1:] == [] and steps[-1][1][-1:] == [""]:
                steps[-1][1].pop()  # a blank line between two steps is only for the eye
            steps.append((line[2:], [], None))
        elif steps:
            cmd, out, code = steps[-1]
            m = re.fullmatch(r"\[exit code (\d+)\]", line)
            if m:
                steps[-1] = (cmd, out, int(m.group(1)))
            else:
                out.append(line)
    return steps


@pytest.fixture
def layout(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    if REAL:
        return
    static = make_static(tmp_path_factory.mktemp("static"))
    real = cli.build_site

    def stub_build(workspace: str, out: str = ".buildzr/site", k: Any = None, text_color: Any = None,
                   viewer: bool = True, **kw: Any) -> dict[str, Any]:
        return real(workspace, out, k, text_color, viewer, layout_fn=stub_layout, static_dir=str(static))

    monkeypatch.setattr(cli, "build_site", stub_build)


# --- servers for the API examples -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def sites(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, int]]:
    tmp = tmp_path_factory.mktemp("apisites")
    if REAL:
        build_site(EXAMPLE_PY, str(tmp / "site"))
    else:
        static = make_static(tmp / "static")
        build_site(EXAMPLE_PY, str(tmp / "site"), layout_fn=stub_layout, static_dir=str(static))
    shutil.copytree(tmp / "site", tmp / "data-only")
    (tmp / "data-only" / "index.html").unlink()
    shutil.rmtree(tmp / "data-only" / "assets")
    servers = []
    ports = {}
    for name, d, kw in (("example", "site", {}), ("data-only", "data-only", {})):
        srv = make_server(str(tmp / d), port=0, **kw)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        ports[name] = srv.server_address[1]
    yield ports
    for srv in servers:
        srv.shutdown()
        srv.server_close()


def fetch(port: int, method: str, target: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(method, target, headers=headers)
        r = conn.getresponse()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
    finally:
        conn.close()


def parse_http(text: str) -> tuple[str, str, dict[str, str], Optional[tuple[int, dict[str, str]]]]:
    """Method, target, request headers and (status, headers) of the response when the block shows one."""
    head, _, resp = text.strip("\n").partition("\n\n")
    lines = head.split("\n")
    method, target = lines[0].split()[:2]
    headers = dict(l.split(": ", 1) for l in lines[1:] if ": " in l)
    answer = None
    if resp.startswith("HTTP/"):
        rl = resp.split("\n")
        answer = (int(rl[0].split()[1]), {k.lower(): v for k, v in (l.split(": ", 1) for l in rl[1:] if ": " in l)})
    return method, target, headers, answer


# --- the blocks -----------------------------------------------------------------------------------------


BLOCKS = all_blocks()
SKIPPED = [b for b in BLOCKS if b.directive and b.directive[0] == "skip"]
CONSUMED: set[str] = set()
for _i, _b in enumerate(BLOCKS):
    if _b.lang == "yaml" and _b.directive and _b.directive[0] == "invalid":
        CONSUMED.add(BLOCKS[_i + 1].id)  # the quoted error belongs to the yaml block before it
    if _b.lang == "http" and _i + 1 < len(BLOCKS) and BLOCKS[_i + 1].lang == "json":
        CONSUMED.add(BLOCKS[_i + 1].id)  # the answer belongs to the request before it
    if _b.lang == "python" and _b.directive and _b.directive[0] == "skip":
        pass
TESTED = [b for b in BLOCKS if b.lang in ("yaml", "http", "json", "python", "text") and b.id not in CONSUMED
          and (b.lang != "text" or is_command_block(b) or (b.directive is not None))
          and (b.lang != "python" or b.directive is not None)]


def needs_real_layout(block: Block) -> bool:
    """A deploy that succeeds (also a dry run) and what reads its result: the checker refuses the stub's scenes, which
    belong to another model. These blocks run only where Node and the built viewer are."""
    if block.lang == "text":
        for cmd, _out, code in parse_steps(block.text):
            if re.search(r"buildzr deploy\b", cmd) and code in (None, 0):
                return True
    d = block.directive
    return bool(d and (d[0] == "audit" or (d[0] == "api" and d[1].split()[:1] == ["instance"])))


@pytest.mark.parametrize("block", TESTED, ids=[b.id for b in TESTED])
def test_block(block: Block, work: dict[str, Any], sites: dict[str, int], layout: None,
               monkeypatch: pytest.MonkeyPatch) -> None:
    d = block.directive
    if d and d[0] == "skip":
        pytest.skip(d[1] or "opted out")
    if not REAL and needs_real_layout(block):
        pytest.skip("needs the real layout (Node and the built viewer)")
    idx = BLOCKS.index(block)
    page = page_of(work, block.page)
    if d and d[0] == "file":
        compile(block.text, d[1], "exec")
        written = page.path(d[1])
        written.parent.mkdir(parents=True, exist_ok=True)
        written.write_text(block.text, encoding="utf-8")
    elif block.lang == "yaml" and d and d[0] == "invalid":
        quoted = BLOCKS[idx + 1].text.rstrip("\n").split("\n")
        tmp = page.dir / "invalid" / "buildzr.yaml"
        tmp.parent.mkdir(exist_ok=True)
        tmp.write_text(block.text, encoding="utf-8")
        with pytest.raises(ConfigError) as e:
            load_config(str(tmp))
        assert e.value.problems == quoted
    elif block.lang == "yaml":
        tmp = page.dir / "valid" / "buildzr.yaml"
        tmp.parent.mkdir(exist_ok=True)
        tmp.write_text(block.text, encoding="utf-8")
        load_config(str(tmp))
        page.write_config(block.text, merge=bool(d and d[0] == "merge"))
    elif block.lang == "text":
        assert is_command_block(block), "a text block that is not a command block cannot carry a directive"
        for cmd, expected, code in parse_steps(block.text):
            tokens = shlex.split(cmd)
            env: dict[str, str] = {}
            while tokens and re.fullmatch(r"[A-Z_]+=\S*", tokens[0]):
                k, _, v = tokens.pop(0).partition("=")
                env[k] = v
            assert tokens[0] == "buildzr", f"only buildzr commands run; mark {cmd!r} with a skip directive"
            serve = tokens[1] == "serve"
            if serve:
                monkeypatch.setattr("socketserver.BaseServer.serve_forever", stop_at_once)
            got, output = run_cli(page.argv(tokens[1:]), page.dir, env)
            lines = [x for x in output.rstrip("\n").split("\n") if not x.startswith('{"time":')]  # the instance's audit log
            msg = same_lines(expected, lines if output.strip() else [])
            assert msg is None, f"$ {cmd}\n{msg}"
            assert got == (0 if code is None else code), f"$ {cmd}: exit code {got}, the page says {code}\n{output}"
    elif block.lang == "http":
        method, target, headers, answer = parse_http(block.text)
        flags = d[1].split() if d and d[0] == "api" else []
        name = flags[0] if flags else "example"
        port = page.instance.rport if name == "instance" and page.instance else sites[name]
        status, rheaders, body = fetch(port, method, target, headers)
        if answer:
            assert status == answer[0], (block.id, status, body[:200])
            for k, v in answer[1].items():
                assert k in rheaders and (re.sub(r"sha256:[0-9a-f]{64}", "H", rheaders[k]) == re.sub(
                    r"sha256:[0-9a-f]{64}", "H", v)), (k, v, rheaders)
        nxt = BLOCKS[idx + 1] if idx + 1 < len(BLOCKS) else None
        if nxt is not None and nxt.lang == "json":
            assert not answer or status == answer[0]
            shape = "shape" in flags
            diffs = compare_json(json.loads(nxt.text), json.loads(body), values=not shape,
                                 ignore=frozenset() if REAL else frozenset({"relationships"}) if "/view?" in target else frozenset())
            assert not diffs, "\n".join(diffs)
        elif not answer:
            assert status == 200, (block.id, status)
    elif block.lang == "json" and d and d[0] == "audit":
        assert page.instance is not None and page.instance.log(), "an audit example needs a deploy before it"
        diffs = compare_json(json.loads(block.text), page.instance.log()[0], values=False)
        assert not diffs, "\n".join(diffs)
    elif block.lang == "json":
        raise AssertionError("a json block needs an http block before it, or a skip directive")


def test_opt_outs_are_few_and_listed(capsys: pytest.CaptureFixture[str]) -> None:
    with capsys.disabled():
        for b in SKIPPED:
            print(f"\nopt-out {b.id}: {b.directive[1] if b.directive else ''}")
    assert len(SKIPPED) <= MAX_OPT_OUTS
    assert all(b.directive and b.directive[1].strip() for b in SKIPPED), "every opt-out names its reason"


def test_every_fenced_block_of_a_tested_page_is_classified() -> None:
    """A yaml, json or `$` text block cannot slip through: the ones that are not tested must opt out."""
    for b in BLOCKS:
        if b.lang in ("yaml", "json") or is_command_block(b):
            assert b.id in CONSUMED or b in TESTED, b.id
