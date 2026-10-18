# Deploying a site to a running instance

`buildzr deploy` can copy a built site to an **instance**: a running `buildzr serve` that serves many sites from one store. For example, you can deploy a preview of every pull request to `https://preview.example.com/pr/42/`.

This page shows how to set up the deploy, what the instance checks, what each failure means, and how the security model works. You do not need to know the code of buildzr to follow it. Related pages:

- The options of every command: [Command reference](cli.md).
- A first deploy, step by step: [Publish your first site](publish-first-site.md).
- The folder layout of an instance: [The site store](store.md).
- The config file: [`buildzr.yaml`](config.md).
- Ready-made setups, such as a preview of every pull request: [Recipes](publishing-recipes.md).

!!! note "Linux and macOS only"
    An instance that accepts deploys (`buildzr serve --store DIR --accept-deploys`) runs only on POSIX systems such as Linux and macOS. It uses a file lock (`flock`), so that only one instance accepts deploys for a store, and a memory limit (`resource`) for the check of every upload. Windows has neither, so do not run an instance on Windows; use WSL (Windows Subsystem for Linux) or a container. `buildzr deploy` itself only sends HTTP requests and runs on any system.

## Words used on this page

| Word | Meaning |
|---|---|
| **site** | The folder that `buildzr build` writes: the viewer, the model data and `build.json`. |
| **deploy** | To copy a built site to a target with `buildzr deploy`. |
| **instance** | A running `buildzr serve --store DIR`: one process that serves every site of a store. With `--accept-deploys`, it also accepts new sites from `buildzr deploy`. |
| **server** | The machine on which the instance runs. |
| **store** | The folder `DIR` in which an instance keeps its sites. See [The site store](store.md). |
| **release** | One copy of a site on an instance, in a folder such as `r-0007`. The instance keeps the current and the previous release of every site path. |
| **modelHash** | A fingerprint of the model, shown as `sha256:` and the start of a hash. The same model always has the same hash, so two equal hashes mean two equal models. |
| **reading listener** | The address and port at which readers open the sites (`--host`, `--port`, default `127.0.0.1:8000`). It only reads: it answers `GET` and `HEAD`. It closes a connection that sends nothing for 60 seconds. |
| **deploy listener** | A second port of the same instance, **always** on `127.0.0.1` (`--deploy-port`, default `8001`). It is the only place that accepts an upload. Nothing can make it listen on another address. |
| **target** | An entry in `buildzr.yaml` that says where `deploy` copies the site. A `url:` target names a deploy listener. |
| **site path** | Where the site goes on the instance. The site path `pr/42` is served at `/pr/42/`. Empty means the top. |
| **site check** | The check that `deploy` and the instance run on a built site before they use it. |

## Set up a deploy to an instance

### 1. Start the instance (on the server)

```text
$ buildzr serve --store /srv/buildzr --host 0.0.0.0 --public-url https://preview.example.com --accept-deploys
Serving store /srv/buildzr (0 sites) at http://0.0.0.0:8000/ (read only)
Accepting deploys at http://127.0.0.1:8001/ (this machine only; no authentication)
```

- With `--accept-deploys`, the instance creates the store folder when the folder is missing or empty. Without the option, `serve --store` reads only, has one listener, and the folder must already be a store.
- `--accept-deploys` needs the `jsonschema` package, because the instance checks every upload against JSON schemas. Install it with `pip install 'buildzr[serve]'`. Without it, `serve` refuses to start (exit code 1). To run the instance without installing buildzr, use `uvx --from "buildzr[serve]" buildzr serve --store DIR --accept-deploys`.
- Only one instance can accept deploys for a store. A second one stops with `another buildzr process accepts deploys for the store ...`. An instance without `--accept-deploys` can serve the same folder next to it, but it does not see new deploys until you restart it.
- `--deploy-port N` (default `8001`) and `--max-upload-mb N` (default `50`) work only together with `--accept-deploys`.
- `--public-url` is the address that readers use. The instance uses it for the links it sends back after a deploy (`open:` and `api:`). Without it, the links use the address of the reading listener. A data-only site has no viewer, so its answer has no `viewerUrl`, and `deploy` prints no `open:` line.
- Ctrl+C stops both listeners.

### 2. Reach the deploy listener (from your machine or CI)

The deploy listener listens only on `127.0.0.1` of the server. To deploy from another machine, open an SSH tunnel to the server:

<!-- doctest: skip ssh needs a real host -->
```text
$ ssh -N -L 9001:127.0.0.1:8001 preview-host
```

While the tunnel is open, `http://127.0.0.1:9001` on your machine is the deploy listener of `preview-host`. On the server itself, for example a CI (continuous integration) runner that also runs the instance, use `http://127.0.0.1:8001` directly.

### 3. Name the target in `buildzr.yaml`

Any model file works. This page uses a very small one:

<!-- doctest: file architecture/model.py -->
```python
from buildzr.dsl import Workspace, Person, SoftwareSystem

with Workspace("shop") as w:
    customer = Person("Customer")
    shop = SoftwareSystem("Shop")
    customer >> "Buys from" >> shop
```

Add a `url:` target that points to the deploy listener, here through the tunnel:

```yaml
workspace: architecture/model.py
targets:
  preview: {url: "http://127.0.0.1:9001", path: "pr/${PR_NUMBER}", timeout: 120}
```

`deploy` refuses a `url:` whose host is not `127.0.0.1`, `localhost` or `[::1]`, because deploys have no authentication in this version (v1). It exits with code 2 and shows the tunnel command of step 2.

An `https://` address on this machine is allowed, but `deploy` prints a warning. The deploy listener speaks plain `http`, so an `https://` address works only if something in between translates.

### 4. Deploy

```text
$ PR_NUMBER=42 buildzr deploy -t preview
built (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)
uploading 12 files, 517 KB to http://127.0.0.1:9001 (path pr/42)
deployed pr/42: release r-0001, modelHash sha256:87716f3c5b04…
open: https://preview.example.com/pr/42/
api:  https://preview.example.com/pr/42/api/v1/
```

With `-v`, `deploy` prints one more line first, from the step that runs your model file. When the new site replaces an older release, the `deployed` line ends with `(previous sha256:…)`: the hash of the release it replaced.

`deploy` takes these steps:

1. It builds the site in a temporary folder. With `--from DIR`, it takes the site that is already built in `DIR` instead.
2. It runs the same site check as the instance, so most problems are found before anything is sent.
3. It packs the site as a `.tar.gz` archive. The archive has the same bytes every time for the same site: names sorted, times 0, owners 0, modes `0644` for files and `0755` for folders.
4. It asks the instance for its limits (`GET /_buildzr/v1/status`). The answer also shows whether the address really is a deploy listener.
5. It sends the archive (`PUT /_buildzr/v1/deploy?path=pr/42`) and prints the answer.

## Other ways to run `deploy`

### Try a deploy without sending anything

`--dry-run` builds, checks and packs the site, and prints the size and the destination. It sends **nothing**; it does not even connect.

```text
$ PR_NUMBER=42 buildzr deploy -t preview --dry-run
built (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)
packed 12 files, 517 KB (192 KB compressed)
dry run: would upload 12 files, 517 KB to http://127.0.0.1:9001 (path pr/42); nothing was sent
```

### Deploy the same site again

When you deploy a site that the instance already has, the instance answers `unchanged` and keeps the current release. The audit log still gets a line.

```text
$ PR_NUMBER=42 buildzr deploy -t preview
built (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)
uploading 12 files, 517 KB to http://127.0.0.1:9001 (path pr/42)
unchanged pr/42: release r-0001 already has these files (modelHash sha256:87716f3c5b04…)
open: https://preview.example.com/pr/42/
api:  https://preview.example.com/pr/42/api/v1/
```

### Roll back to the previous release

`buildzr deploy -t preview --rollback` makes the previous release current again (`POST /_buildzr/v1/rollback?path=pr/42`). Nothing is built. When there is no previous release, the command stops with `nothing to roll back to` (exit code 1). The [recipes](publishing-recipes.md#rolling-back-a-bad-deploy) show a rollback that works.

### Exit codes of `deploy`

| Code | Meaning |
|---|---|
| 0 | Deployed, or unchanged. |
| 1 | The instance rejected the site, the site check failed, or the address is not a deploy listener. |
| 2 | A usage or config problem. |
| 3 | The instance cannot be reached, the upload was interrupted, the instance stayed busy until the timeout, or it is out of disk space. Try again later. |

The [Command reference](cli.md#exit-codes) has the table for all commands.

## What the instance checks

The instance treats every request body as hostile. It checks the request, then the archive, then the site, in this order.

### The request

1. The `Host` header must be `127.0.0.1`, `localhost` or `[::1]`, with any port, because the port of a tunnel differs from the port of the listener. Any other host gets `403`. This stops "DNS rebinding", in which a web page makes its own domain name point at `127.0.0.1`.
2. A request with a `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host` or `X-Real-IP` header gets `403`. A request that went through a proxy never deploys.
3. An upload must carry `X-Buildzr-Deploy: 1` (else `400`) and `Content-Type: application/gzip` (else `415`).
4. `Content-Length` is required and must be above 0 (else `411`). Chunked uploads are not accepted. An upload larger than `--max-upload-mb` gets `413` **before** the body is read.
5. The site path must follow the [site path rules](store.md#site-paths) (else `400` with the rule).
6. Only one deploy or rollback runs at a time. A second one gets `409` with `Retry-After: 5`. There is no queue: `deploy` waits and tries again until its `timeout`.
7. The whole body must arrive within 60 seconds (else `408`). The instance reads exactly `Content-Length` bytes. If fewer arrive, the answer is `400` "upload incomplete".
8. The instance never answers `OPTIONS` and never sends a CORS (Cross-Origin Resource Sharing) header. Every other method or address gets `405` or `404`.
9. The request line and all headers must arrive within 30 seconds. Headers that cannot be read cleanly get `400`. The deploy listener serves at most 16 connections at once.

### The archive

The instance never unpacks the archive with a library's "extract everything" function. It reads the archive one member at a time into `incoming/<random>/` of the store, and checks each member:

- **Names** use only letters, digits, `.`, `_`, `-` and `/`. A name has no `.` or `..` part, no leading `/`, and at most 255 characters. No name appears twice, also not twice with different upper and lower case. (`deploy` writes the plain `ustar` archive format, which cannot hold a single name part of more than 100 characters; `deploy` reports such a name and exits with code 1.)
- **Types**: only plain files and folders. Symbolic links, hard links, devices, FIFOs and the extended (pax and GNU) headers are refused before the archive reader acts on them.
- **Top level**: only `index.html`, `assets/`, `data/` and `build.json`. Anything else, such as `.htaccess`, `llms.txt` or an extra page, is refused.
- **`assets/`**: files end in `.js`, `.css`, `.woff2`, `.woff` or `.txt`, which is what the viewer is made of.
- **Size**: at most 200 MB unpacked, 20,000 files, 20,000 folders and 16 levels of folders. The instance counts while it reads, so a "zip bomb" stops early. Past 16 MB, an archive that unpacks to more than 250 times its compressed size is also refused. `data/index.json` is at most 4 MB, and every other file in `data/` at most 32 MB.
- **Modes**: files are written `0644` and folders `0755`, whatever the archive says. Owners and times are ignored.

### The site

Then the instance runs the site check on the unpacked copy. The check runs in a separate process with a limit of 60 seconds and 1 GB of memory, so no upload can take the instance down with it. The site check covers:

- the JSON schemas, the hashes in `data/index.json`, the `modelHash` of every file, and the geometry checks, as `buildzr build` does;
- every file named in `data/index.json` is inside `data/`, and `data/` holds no file that `data/index.json` does not name;
- `build.json` is there, and its `modelHash` equals the one in the index;
- the schema names are the ones this instance reads. An upload made by a newer buildzr is refused, for example with `this instance reads buildzr.model/2; the upload is buildzr.model/3; upgrade the instance`;
- `index.html`, when there is one, refers only to files under `assets/` that exist. It has no inline script, no inline style, no `on...=` attribute, no `<base>`, `<iframe>`, `<object>`, `<embed>`, `<form>` and no refresh. This check confirms that the page is a built viewer page; it is not a sandbox (see [the security model](#the-security-model-in-plain-words)). A data-only site (built with `viewer: false`) is accepted.

If anything is wrong, the answer is `422` with up to 20 problems. Nothing is installed, and `incoming/<random>/` is removed.

Only a site that passes every check becomes the current release, with the same steps as in [The site store](store.md). Readers see it at once. A release that a deploy replaced stays on disk for 30 seconds before it is deleted, so that a reader in the middle of a request can finish.

## When it goes wrong

In every row of this table, the current release on the instance stays as it was.

| What happened | What the instance answers | What `deploy` prints (exit code) | What to do |
|---|---|---|---|
| The upload was cut off | `400` "upload incomplete" (or the connection closes) | `upload interrupted, nothing changed` (3) | Run the deploy again. The current release was not touched. |
| The site is invalid | `422` with up to 20 problems | the problems (1) | Fix the model or the build; `buildzr build` shows the same problems. |
| The site is too large | `413` with the limit | `site is 63 MB, the instance accepts 50 MB (--max-upload-mb)` (1) | Start the instance with a larger `--max-upload-mb`, or make the site smaller. |
| The disk of the server is full | `507` | `instance is out of disk space; nothing changed` (3) | Free space on the server. `incoming/` was cleaned. |
| The instance does not accept deploys | nothing listens | `nothing is listening at http://127.0.0.1:9001; start the instance with buildzr serve --store DIR --accept-deploys (or open the SSH tunnel)` (3) | Start the instance with `--accept-deploys`, or open the tunnel. |
| The address is wrong (the reading listener, or another server) | `404`/`405`/`501`, or not JSON | `... is not a buildzr deploy address ...` (1) | Use the deploy listener (`--deploy-port`, default 8001), not the reading listener. |
| Another deploy is running | `409` with `Retry-After` | waits and tries again until `timeout`, then `the instance is busy with another deploy ...` (3) | Try again later, or raise the `timeout` of the target. |
| The upload is too slow | `408` after 60 s | `upload interrupted, nothing changed` (3) | Check the network or the tunnel. |
| The address is not on this machine | (not sent) | `... is not this machine. ... ssh -N -L 9001:127.0.0.1:8001 HOST ...` (2) | Use an SSH tunnel and `url: http://127.0.0.1:<local port>`. |

## The audit log

Every deploy, rejection and rollback adds one JSON line to `deploys.log` in the store. The instance also prints the line on its standard error output:

<!-- doctest: audit -->
```json
{"time":"2026-10-17T10:41:07Z","action":"deploy","path":"pr/42","result":"ok","release":"r-0007","modelHash":"sha256:d2cb…","previous":"sha256:5a1f…","files":23,"bytes":548211,"senderVersion":"0.0.36","client":"127.0.0.1","ms":412}
```

- `result` is `ok`, `unchanged` or `rejected`. A rejected line has `status` (the HTTP status) and `error` (the first problem) instead of the release fields.
- `client` is the address the connection came from; it is always `127.0.0.1`.
- `senderVersion` is the buildzr version that the client sent, or `null` if the value did not look like a version.

Requests that fail the first checks of the request (a wrong `Host`, a forwarded header, a missing `X-Buildzr-Deploy`) never reach the deploy code and are not logged, so a web page cannot fill the log. Nothing else from the request is logged: no body and no other header.

## The security model, in plain words

- **Only the server itself can deploy.** The deploy listener listens on `127.0.0.1` and nowhere else, so another computer on the network cannot even connect to it. The reading listener may be public, but it has no way to write anything.
- **There is no password or token in this version (v1).** Anyone who can open a connection to `127.0.0.1:8001` **on the server** can deploy or roll back. On a server with one user, that is only you and your programs. On a server shared with other people, **every other user account on that server can replace your sites.** If that is not acceptable, do not use `--accept-deploys` there until tokens exist.
- **Web pages cannot deploy.** A web page open in a browser on the server could try to send a request to `127.0.0.1:8001`, but the request fails. The instance requires the custom header `X-Buildzr-Deploy: 1` and `Content-Type: application/gzip`. A browser sends these only after it asks for permission first (a "preflight"), and the instance never gives that permission: it has no `OPTIONS` answer and no CORS headers. A page that points its own domain name at `127.0.0.1` through DNS is refused by the `Host` check.
- **Never point a reverse proxy at the deploy listener.** A proxy on the server (nginx, Caddy, a load balancer) makes every request look as if it came from `127.0.0.1`. Pointed at the deploy listener, it would let the whole internet deploy. Point it only at the reading listener. As a second guard, the deploy listener refuses any request with a `Forwarded`, `X-Forwarded-*` or `X-Real-IP` header, which proxies add. Do not rely on that guard: some proxies do not add these headers.
- **The SSH tunnel is the authentication.** To reach an instance on another machine, you need an SSH login on that machine. Whoever can open the tunnel can deploy.
- **A deployed site is trusted.** The person who deploys chooses the JavaScript of the viewer that readers run, and all sites of one instance share one web origin. An instance has no logins or cookies, so the harm a hostile site can do to readers is small, but it is not zero. Only let people you trust deploy.
- **An archive cannot escape the store.** The instance checks the names, refuses links and devices, and names each release folder by a hash of its site path, not by the site path itself.
