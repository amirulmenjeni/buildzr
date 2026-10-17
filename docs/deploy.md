# Deploying a site to a running instance

`buildzr deploy` can put a built site on a running `buildzr serve` (an **instance**), for example a preview of every pull request at `https://preview.example.com/pr/42/`. This page explains how that works, what the instance checks, what each failure means, and what the security model is.

You do not need to know the code to follow it. For the commands and their flags see the [command line](cli.md) page; for the folder layout of an instance see [the site store](store.md); for the config file see [buildzr.yaml](config.md); for ready-made setups such as a preview per pull request see the [recipes](publishing-recipes.md).

!!! note "Linux and macOS only"
    The instance (`buildzr serve --store DIR --accept-deploys`) is for POSIX systems. It uses a file lock (`flock`) so that only one instance accepts deploys for a store, and a memory limit (`resource`) for the check of every upload. Neither exists on Windows, so do not run an instance there; use WSL or a container. `buildzr deploy` itself only sends HTTP requests and needs neither.

## The parts

| Word | Meaning |
|---|---|
| **site** | The folder `buildzr build` writes: the viewer, the data and `build.json`. |
| **release** | One copy of a site on an instance (`r-0007`). The instance keeps the current and the previous release of every site path. See [the site store](store.md). |
| **modelHash** | A fingerprint of the model, shown as `sha256:` and the start of a hash. The same model always has the same hash, so two equal hashes mean two equal models. |
| **instance** | A running `buildzr serve --store DIR --accept-deploys`. It keeps its sites in the store folder `DIR`. |
| **reading listener** | The address readers use (`--host`, `--port`, default `127.0.0.1:8000`). It only reads: GET and HEAD. |
| **deploy listener** | A second address of the same instance, **always** `127.0.0.1:<--deploy-port>` (default `8001`). It is the only place that accepts an upload. Nothing can make it listen on another address. |
| **target** | An entry in `buildzr.yaml` that says where `deploy` sends the site. A `url:` target names a deploy listener. |
| **site path** | Where the site goes on the instance: `pr/42` is served at `/pr/42/`. Empty means the root. |

## The flow

### 1. Start the instance (on the server)

```text
$ buildzr serve --store /srv/buildzr --host 0.0.0.0 --public-url https://preview.example.com --accept-deploys
Serving store /srv/buildzr (0 sites) at http://0.0.0.0:8000/ (read only)
Accepting deploys at http://127.0.0.1:8001/ (this machine only; no authentication)
```

- With `--accept-deploys` the store folder is created when it is missing or empty. Without the flag, `serve --store` works exactly as before (read only, one listener, the folder must already be a store).
- `--accept-deploys` needs the `jsonschema` package, because every upload is checked against the JSON schemas. Install it with `pip install 'buildzr[serve]'`. Without it, `serve` refuses to start (exit code 1).
- Only one instance can accept deploys for a store: a second one stops with `another buildzr process accepts deploys for the store ...`. A read-only `serve --store` on the same folder can run next to it, but it does not see new deploys until it is restarted.
- `--deploy-port N` (default `8001`) and `--max-upload-mb N` (default `50`) only exist together with `--accept-deploys`.
- `--public-url` is the address readers use. The instance uses it for the links it sends back after a deploy (`open:` and `api:`). Without it, the links use the reading listener's own address.
- Ctrl+C stops both listeners.

### 2. Reach the deploy listener (from your machine or CI)

The deploy listener only listens on the server's own `127.0.0.1`. From another machine, open an SSH tunnel:

<!-- doctest: skip ssh needs a real host -->
```text
$ ssh -N -L 9001:127.0.0.1:8001 preview-host
```

Now `http://127.0.0.1:9001` on your machine is the deploy listener of `preview-host`. On the server itself (for example a CI runner that also runs the instance) you can use `http://127.0.0.1:8001` directly.

### 3. Name the target in `buildzr.yaml`

Any model file will do. This page uses a very small one:

<!-- doctest: file architecture/model.py -->
```python
from buildzr.dsl import Workspace, Person, SoftwareSystem

with Workspace("shop") as w:
    customer = Person("Customer")
    shop = SoftwareSystem("Shop")
    customer >> "Buys from" >> shop
```

```yaml
workspace: architecture/model.py
targets:
  preview: {url: "http://127.0.0.1:9001", path: "pr/${PR_NUMBER}", timeout: 120}
```

`deploy` refuses a `url:` whose host is not `127.0.0.1`, `localhost` or `[::1]` (exit code 2, with the tunnel hint above), because v1 deploys have no authentication. An `https://` address to this machine is allowed but prints a warning: the v1 deploy listener speaks plain `http`, so it cannot work unless something in between speaks `https`.

### 4. Deploy

```text
$ PR_NUMBER=42 buildzr deploy -t preview
/home/you/shop/architecture/model.py: 2 elements, 1 relationships, 0 views, 1 levels -> /tmp/tmpab12cd/.build-x1y2z3/export
built (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)
uploading 12 files, 517 KB to http://127.0.0.1:9001 (path pr/42)
deployed pr/42: release r-0001, modelHash sha256:87716f3c5b04…
open: https://preview.example.com/pr/42/
api:  https://preview.example.com/pr/42/api/v1/
```

The first line comes from the step that runs your model file. When a site replaces an older release, the `deployed` line ends with `(previous sha256:…)`, the hash of the release it replaced.

What `deploy` does:

1. Builds the site in a temporary folder (or takes `--from DIR`, an already built site).
2. Runs the same checker as the instance will, so most problems are found before anything is sent.
3. Packs the site as a `.tar.gz`. The archive is the same bytes every time for the same site: names sorted, times 0, owners 0, modes `0644` for files and `0755` for folders.
4. Asks the instance for its limits (`GET /_buildzr/v1/status`). This also tells it whether the address really is a deploy listener.
5. Sends the archive (`PUT /_buildzr/v1/deploy?path=pr/42`) and prints the answer.

Other forms:

- `buildzr deploy -t preview --dry-run` builds, checks and packs, prints the size and the destination, and sends **nothing** (it does not even connect):

```text
$ PR_NUMBER=42 buildzr deploy -t preview --dry-run
/home/you/shop/architecture/model.py: 2 elements, 1 relationships, 0 views, 1 levels -> /tmp/tmpab12cd/.build-x1y2z3/export
built (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)
packed 12 files, 517 KB (192 KB compressed)
dry run: would upload 12 files, 517 KB to http://127.0.0.1:9001 (path pr/42); nothing was sent
```

- `buildzr deploy -t preview` a second time with the same site answers `unchanged`. The instance keeps the current release, and the audit log still gets a line:

```text
$ PR_NUMBER=42 buildzr deploy -t preview
/home/you/shop/architecture/model.py: 2 elements, 1 relationships, 0 views, 1 levels -> /tmp/tmpab12cd/.build-x1y2z3/export
built (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)
uploading 12 files, 517 KB to http://127.0.0.1:9001 (path pr/42)
unchanged pr/42: release r-0001 already has these files (modelHash sha256:87716f3c5b04…)
open: https://preview.example.com/pr/42/
api:  https://preview.example.com/pr/42/api/v1/
```

- `buildzr deploy -t preview --rollback` makes the previous release current again (`POST /_buildzr/v1/rollback?path=pr/42`). Nothing is built. It stops with `nothing to roll back to` (exit code 1) when there is no previous release; the [recipes](publishing-recipes.md#rolling-back-a-bad-deploy) show a rollback that works.

Exit codes of `deploy`: `0` deployed or unchanged; `1` the instance rejected the site, the local check failed, or the address is not a deploy listener; `2` a usage or config problem; `3` the instance cannot be reached, the upload was interrupted, the instance stayed busy until the timeout, or it is out of disk space (all worth trying again). The full table is on the [command line](cli.md#exit-codes) page.

## What the instance checks

Every request body is treated as hostile. In this order:

**The request.**

1. The `Host` header must be `127.0.0.1`, `localhost` or `[::1]` (any port, because a tunnel's port differs from the listener's). Anything else: `403`. This stops "DNS rebinding", where a web page makes its own domain name point at `127.0.0.1`.
2. A request with `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host` or `X-Real-IP` is refused (`403`): a request that went through a proxy never deploys.
3. An upload must carry `X-Buildzr-Deploy: 1` (else `400`) and `Content-Type: application/gzip` (else `415`).
4. `Content-Length` is required and above 0 (else `411`; chunked uploads are not accepted). Above `--max-upload-mb` the upload is refused with `413` **before** the body is read.
5. The site path follows the [site path rules](store.md#site-paths) (else `400` with the rule).
6. One deploy or rollback at a time. A second one gets `409` with `Retry-After: 5`; there is no queue (`deploy` waits and tries again until its `timeout`).
7. The whole body must arrive within 60 seconds (else `408`), and exactly `Content-Length` bytes are read. If fewer arrive, the answer is `400` "upload incomplete".
8. There is no `OPTIONS` answer and no CORS header, ever. Every other method or address gets `405` or `404`.
9. The request line and all headers must arrive within 30 seconds, headers that cannot be read cleanly are refused (`400`), and the deploy listener serves at most 16 connections at once.

**The archive.** The instance never unpacks with a library's "extract everything". It reads the archive member by member into `incoming/<random>/` of the store:

- names use only letters, digits, `.`, `_`, `-` and `/`; no `.` or `..` part, no leading `/`, at most 255 characters (the client writes the plain `ustar` archive format, so it cannot pack a single name part of more than 100 characters, and says so with exit code 1), and no name twice (also not twice with different upper and lower case);
- only plain files and folders: symbolic links, hard links, devices, FIFOs and the extended (pax and GNU) headers are refused before the archive reader acts on them;
- only `index.html`, `assets/`, `data/` and `build.json` at the top; anything else (`.htaccess`, `llms.txt`, an extra page) is refused;
- files in `assets/` end in `.js`, `.css`, `.woff2`, `.woff` or `.txt` (what the viewer is made of);
- at most 200 MB unpacked, 20,000 files, 20,000 folders and 16 levels of folders, counted while reading, so a "zip bomb" stops early; past 16 MB, an archive that unpacks to more than 250 times its compressed size is refused too; `data/index.json` is at most 4 MB and every other file in `data/` at most 32 MB;
- files are written `0644` and folders `0755` whatever the archive says; owners and times are ignored.

**The site.** Then the checker runs on the unpacked copy, in a separate process with a 60 second limit and a memory limit of 1 GB, so no upload can take the instance down with it:

- the JSON schemas, the hashes in `data/index.json`, the `modelHash` of every file, the geometry checks (as `buildzr build` does);
- every file named in `data/index.json` stays inside `data/`, and `data/` holds no file that `data/index.json` does not name;
- `build.json` is there and its `modelHash` equals the index's;
- the schema names must be the ones this instance reads. An upload made by a newer buildzr is refused with, for example: `this instance reads buildzr.model/2; the upload is buildzr.model/3; upgrade the instance`;
- `index.html`, when there is one, may only refer to files under `assets/` that exist, and has no inline script, no inline style, no `on...=` attribute, no `<base>`, `<iframe>`, `<object>`, `<embed>`, `<form>` or refresh. This is a check that the page is a built viewer page, not a sandbox (see the security model). A site without a viewer (built with `viewer: false`) is accepted.

Anything wrong gives `422` with up to 20 problems. Nothing is installed and `incoming/<random>/` is removed. Only a site that passes everything becomes the current release, with the same steps as in [the site store](store.md); readers see it at once. A release replaced by a deploy stays on disk for 30 seconds before it is deleted, so a reader in the middle of a request can finish.

## When it goes wrong

| What happened | What the instance answers | What `deploy` prints (exit code) | What to do |
|---|---|---|---|
| The upload was cut off | `400` "upload incomplete" (or the connection closes) | `upload interrupted, nothing changed` (3) | Run the deploy again. The current release was not touched. |
| The site is invalid | `422` with up to 20 problems | the problems (1) | Fix the model or the build; `buildzr build` shows the same problems. |
| The site is too large | `413` with the limit | `site is 63 MB, the instance accepts 50 MB (--max-upload-mb)` (1) | Start the instance with a larger `--max-upload-mb`, or make the site smaller. |
| The instance's disk is full | `507` | `instance is out of disk space; nothing changed` (3) | Free space on the server. `incoming/` was cleaned. |
| The instance does not accept deploys | nothing listens | `nothing is listening at http://127.0.0.1:9001; start the instance with buildzr serve --store DIR --accept-deploys (or open the SSH tunnel)` (3) | Start the instance with `--accept-deploys`, or open the tunnel. |
| The address is wrong (the reading port, another server) | `404`/`405`/`501`, or not JSON | `... is not a buildzr deploy address ...` (1) | Use the deploy port (`--deploy-port`, default 8001), not the reading port. |
| Another deploy is running | `409` with `Retry-After` | waits and tries again until `timeout`, then `the instance is busy with another deploy ...` (3) | Try again later, or raise the target's `timeout`. |
| The upload is too slow | `408` after 60 s | `upload interrupted, nothing changed` (3) | Check the network or tunnel. |
| The address is not this machine | (not sent) | `... is not this machine. ... ssh -N -L 9001:127.0.0.1:8001 HOST ...` (2) | Use an SSH tunnel and `url: http://127.0.0.1:<local port>`. |

In every row the current release on the instance stays as it was.

## The audit log

Every deploy, rejection and rollback adds one JSON line to `deploys.log` in the store and prints it on the instance's stderr:

<!-- doctest: audit -->
```json
{"time":"2026-10-17T10:41:07Z","action":"deploy","path":"pr/42","result":"ok","release":"r-0007","modelHash":"sha256:d2cb…","previous":"sha256:5a1f…","files":23,"bytes":548211,"senderVersion":"0.0.36","client":"127.0.0.1","ms":412}
```

Requests that fail the first checks (a wrong `Host`, a forwarded header, a missing `X-Buildzr-Deploy`) never reach the deploy code and are not logged, so a web page cannot fill the log. `result` is `ok`, `unchanged` or `rejected`; a rejected line has `status` (the HTTP status) and `error` (the first problem) instead of the release fields. `client` is the address the connection came from (always `127.0.0.1`), `senderVersion` the buildzr version the client sent (or `null` if it did not look like a version). Nothing else from the request is logged: no body and no other header.

## The security model, in plain words

- **Only this machine can deploy.** The deploy listener listens on `127.0.0.1` and nowhere else. A computer on the network cannot even connect to it. The reading listener, which may be public, has no way to write anything.
- **There is no password or token in v1.** Anyone who can open a connection to `127.0.0.1:8001` **on the server** can deploy or roll back. On a machine with one user that is only you (and your programs). On a machine shared with other people, **every other user account on that machine can replace your sites.** If that is not acceptable, do not use `--accept-deploys` there until tokens exist.
- **Web pages cannot deploy.** A web page open in a browser on the server could try to send a request to `127.0.0.1:8001`. It cannot: the instance wants the custom header `X-Buildzr-Deploy: 1` and `Content-Type: application/gzip`, which a browser only sends after asking permission first (a "preflight"), and the instance never gives that permission (no `OPTIONS` answer, no CORS headers). A page that renames itself to `127.0.0.1` through DNS is refused by the `Host` check.
- **Never point a reverse proxy at the deploy port.** A proxy (nginx, Caddy, a load balancer) on the server makes every request look as if it came from `127.0.0.1`. Pointed at the deploy port, it would let the whole internet deploy. Point it only at the reading port. As a second guard, the deploy listener refuses any request that carries a `Forwarded` or `X-Forwarded-*` or `X-Real-IP` header, which proxies add, but do not rely on that: some proxies do not add them.
- **The SSH tunnel is the authentication.** Reaching a remote instance means having an SSH login on it. Whoever can open the tunnel can deploy.
- **A deployed site is trusted.** The person deploying chooses the viewer's JavaScript that readers run, and all sites of one instance share one web origin. There are no logins or cookies on an instance, so the harm a hostile site can do to readers is small, but it is not zero. Only let people you trust deploy.
- **An archive cannot escape the store.** Names are checked, links and devices are refused, and a release folder is named by a hash of its site path, not by the path itself.
