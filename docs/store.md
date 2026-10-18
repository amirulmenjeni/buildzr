# The site store

A **store** is a folder that holds several sites, so that one `buildzr serve` process can serve them all, each at its own address. For example, the main model can be at `/` and a preview of a pull request at `/pr/42/`. Each site has its own viewer, its own [Model API](model-api.md) and its own `llms.txt`.

This page is a reference for people who run a store. It describes how to serve a store, what is in the folder, which site paths are allowed, how an address finds its site, and how to list the sites. To add sites to a store, read [Deploying to an instance](deploy.md).

## Words used on this page

| Word | Meaning |
|---|---|
| **site** | The folder that `buildzr build` writes: the viewer, the model data (`data/`) and a file called `build.json`. |
| **data-only site** | A site without the viewer, only the model data. |
| **store** | A folder that holds several sites and the file `buildzr-store.json`. |
| **instance** | A running `buildzr serve --store DIR`: one process that serves every site of a store. With `--accept-deploys`, it also accepts new sites from `buildzr deploy`. |
| **reading listener** | The address and port at which an instance serves the sites (`--host`, `--port`). It only reads. |
| **deploy listener** | The second port of an instance started with `--accept-deploys`. It accepts uploads from `buildzr deploy`, and only from the same machine. |
| **site path** | Where a site sits below the top of the instance. Empty means the top; the site path `pr/42` is served at `/pr/42/`. |
| **release** | One copy of a site in the store, in a folder such as `r-0007`. The store keeps the **current** release and the **previous** release of every site path. |
| **modelHash** | A fingerprint of the model, shown as `sha256:` and a hash. The same model always gives the same hash. |

## `buildzr serve --store`

```text
buildzr serve --store DIR [-p PORT] [--host HOST] [--public-url URL] [--cors-origin ORIGIN]...
```

An instance that accepts deploys creates the store folder the first time it starts. These examples use the folder `/srv/buildzr`:

```text
$ buildzr serve --store /srv/buildzr --accept-deploys
Serving store /srv/buildzr (0 sites) at http://127.0.0.1:8000/ (read only)
Accepting deploys at http://127.0.0.1:8001/ (this machine only; no authentication)
```

```text
$ buildzr serve --store /srv/buildzr
Serving the store /srv/buildzr (0 sites) at http://127.0.0.1:8000/ (Ctrl+C to stop)
Site list at http://127.0.0.1:8000/_buildzr/v1/sites (read only)
```

A folder that is not a store is refused:

```text
$ buildzr serve --store /srv/elsewhere
buildzr: error: /srv/elsewhere is not a buildzr store (no buildzr-store.json)
[exit code 1]
```

- `--store DIR` cannot be combined with a site folder `DIR`.
- The folder must already be a store (it has `buildzr-store.json`). The exception is `--accept-deploys`, which creates the store.
- The reading listener only reads: it answers `GET` and `HEAD`. Any other method gets `405` (with problem details) under `/api/v1/` and `/_buildzr/`, and `501` elsewhere. The reading listener never writes a file in the store.
- When an instance starts, it reads `buildzr-store.json`, so it serves the same sites after a restart.
- An instance without `--accept-deploys` keeps its list of sites in memory. It does not see deploys made after it started. Restart it, or serve the store from the instance that accepts deploys (one instance per store).
- `buildzr serve DIR`, which serves one site, is unchanged and has no `/_buildzr/` address.

## Layout of a store folder

| Path in the store | What it is |
|---|---|
| `buildzr-store.json` | Marks the folder as a store. For each site path, it lists the current and the previous release and the `modelHash` of each. |
| `sites/<key>/r-0007/` | One release: an ordinary site. `<key>` is the first 16 hex characters of the sha256 of the site path. A site path therefore never becomes a folder name, and a site path such as `../x` cannot reach the file system. |
| `incoming/<random>/` | Sites that are being unpacked and checked. The folder is emptied whenever the store is opened. |
| `.buildzr-store.lock` | An empty file that the instance that accepts deploys keeps locked while it runs. A second instance that accepts deploys cannot start on the same store. An instance without `--accept-deploys` that starts meanwhile does not clean up what a deploy is writing. |
| `deploys.log` | One JSON line per install or rollback. Lines written by the deploy listener have the fields of [the audit log](deploy.md#the-audit-log). Lines written by the [Python functions](#python-functions-for-scripts-and-tests) have `time`, `sitePath`, `release`, `modelHash`, `previousModelHash`, `action` and `result`. |

When the store is opened, `buildzr` reads `buildzr-store.json` strictly. Any of these problems is reported as one line, `buildzr: error: buildzr-store.json: ...`, never as a traceback:

- the file is not JSON, or has the wrong shape;
- it has an unknown `version`;
- it lists a release folder that is missing;
- it names a release that would leave `sites/`.

Release folders that the file does not list are deleted. An interrupted install can leave such folders.

## Site paths

A site path is made of segments separated by `/`:

- Each segment matches `[a-z0-9][a-z0-9._-]*`: lower-case letters, digits, `.`, `_` and `-`, starting with a letter or digit.
- No segment is empty, `.` or `..`. A site path contains no backslash and no NUL byte.
- A leading or trailing `/` is removed.
- A site path has at most 8 segments and 128 characters.

**Reserved names.** These segment names are refused anywhere in a site path: `api`, `assets`, `data`, `_buildzr`, `index.html`, `build.json`, `llms.txt`. They are the names of things inside a site, and of the store's own address `/_buildzr/`. This rule makes sure a nested site can never hide a file of the site above it. For example, `pr/42` is allowed; `data/x` and `pr/api` are refused.

## How a URL finds its site

For each request, the instance takes these steps in order:

1. **Normalise the path.** Percent-escapes are decoded **once**. The answer is `404` if the result contains a backslash, a NUL byte or another control character, an empty segment (`/a//b`), or a `.` or `..` segment. The path is never decoded a second time, so `%252e%252e` stays the text `%2e%2e`: a file name that does not exist.
2. **Pick the site.** The site is the one whose site path is the longest prefix of the URL **on whole segments**. `/pr/42/data/index.json` goes to `pr/42`, but `/pr/420/` does **not** match `pr/42`. The site at the top (site path `""`) receives every request that no other site matches. A reserved name never changes this: `/pr/42/data/x` always belongs to `pr/42`.
3. **Add the slash.** `/pr/42` is answered with `308 Permanent Redirect` to `/pr/42/`, and the query string is kept. The redirect is needed because the relative links of the viewer only work below a URL that ends in `/`.
4. **Look inside the release.** The rest of the URL is looked up in the current release of that site, with the same rules as `buildzr serve` for one site. The file must be inside the release folder; a symbolic link that leaves it gives `404`. There are no folder listings, and a folder requested without its closing `/` is redirected.

If the store has no site at the top, `/` shows a small page that lists the sites. An unknown address gets `404`. For an address that looks like an API (`.../api/v1/...` or `/_buildzr/...`), the `404` answer is [problem details](model-api.md) JSON.

## List the sites of a store

`GET /_buildzr/v1/sites` lists the sites of an instance. A script or an AI assistant that knows only the host name can find every site with it.

To show an answer, this example deploys two sites to an instance: the main model at the top and a preview at `pr/42`. It uses a very small model:

<!-- doctest: file architecture/model.py -->
```python
from buildzr.dsl import Workspace, Person, SoftwareSystem

with Workspace("shop") as w:
    customer = Person("Customer")
    shop = SoftwareSystem("Shop")
    customer >> "Buys from" >> shop
```

<!-- doctest: merge -->
```yaml
workspace: architecture/model.py
targets:
  main: {url: "http://127.0.0.1:8001"}
  preview: {url: "http://127.0.0.1:8001", path: "pr/${PR_NUMBER}"}
```

```text
$ buildzr deploy -t main
built (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)
uploading 12 files, 517 KB to http://127.0.0.1:8001 (the root site)
deployed /: release r-0001, modelHash sha256:87716f3c5b04…
open: https://preview.example.com/
api:  https://preview.example.com/api/v1/

$ PR_NUMBER=42 buildzr deploy -t preview
built (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)
uploading 12 files, 517 KB to http://127.0.0.1:8001 (path pr/42)
deployed pr/42: release r-0001, modelHash sha256:87716f3c5b04…
open: https://preview.example.com/pr/42/
api:  https://preview.example.com/pr/42/api/v1/
```

The request and its answer:

<!-- doctest: api instance shape -->
```http
GET /_buildzr/v1/sites
```

```json
{
  "apiVersion": "1",
  "sites": [
    {
      "sitePath": "",
      "name": "shop",
      "currentRelease": "r-0001",
      "modelHash": "sha256:87716f3c5b04b965d25a6abb01c53cc577a5f830310e1dca1d4c1d4ad25328a7",
      "previousModelHash": null,
      "elements": 2,
      "relationships": 1,
      "viewerUrl": "https://preview.example.com/",
      "apiUrl": "https://preview.example.com/api/v1/"
    },
    {
      "sitePath": "pr/42",
      "name": "shop",
      "currentRelease": "r-0001",
      "modelHash": "sha256:87716f3c5b04b965d25a6abb01c53cc577a5f830310e1dca1d4c1d4ad25328a7",
      "previousModelHash": null,
      "elements": 2,
      "relationships": 1,
      "viewerUrl": "https://preview.example.com/pr/42/",
      "apiUrl": "https://preview.example.com/pr/42/api/v1/"
    }
  ]
}
```

This instance was started with `--public-url https://preview.example.com`, so the addresses start with that URL. Without `--public-url`, the addresses start with `/`, for example `"viewerUrl": "/pr/42/"`.

- `name` is the name of the `Workspace` in the model file of the site. It lets a reader tell `pr/41` from `pr/42` without opening either.
- `viewerUrl` is `null` for a data-only site (a site with no `index.html`), with or without `--public-url`. `apiUrl` is always present.
- `previousModelHash` is `null` when the site has no previous release.
- `name`, `elements` and `relationships` are `null` when the model of the release cannot be read. `name` is also `null` when the `Workspace` has no name.
- The answer has an `ETag` header that changes when any site, release or `modelHash` changes. A request with `If-None-Match` gets `304`.
- As in the Model API, the answer has no CORS (Cross-Origin Resource Sharing) headers unless the instance was started with `--cors-origin`.
- Every other address under `/_buildzr/` gets `404`.

The Model API of each site is below the address of the site, for example `/pr/42/api/v1/`, next to `/pr/42/llms.txt`. Its `viewerUrl` links include the site path, so a link from `/pr/42/api/v1/element?id=billing` opens `/pr/42/#/m/billing?sel=billing`.

## Opening a viewer during a change

A reader may have the viewer open while a new release is installed. The viewer has loaded `data/index.json` of the old release, and asks for scene files of that release later. The instance handles this as follows:

- Scene files, the model data file (`data/model.<h8>.json`) and the files in `assets/` have a content hash in their name. A file with a given name therefore always has the same content.
- When such a file is **not** in the current release, the instance looks for it in the **previous** release of the same site and serves it from there.
- `data/index.json`, `index.html`, `build.json` and `llms.txt` are **never** taken from the previous release. They always come from the current one.
- After two newer installs, the old release is gone, and a viewer that still uses it shows a load error. Reloading the page fixes it.

A request that has started keeps the release it started with, even if a new release is installed while the instance answers it.

## What is not there yet

- A way to change a store through the reading listener. Without `--accept-deploys`, nothing in `serve --store` can write. With it, only the separate deploy listener can.
- A way to remove a site from a store.

## Python functions (for scripts and tests)

The module `buildzr.site.store` installs and rolls back sites without an instance:

```python
from buildzr.site.store import Store

store = Store.open("/srv/buildzr", create=True)        # makes the folder when it is missing or empty
# a checked site is moved into incoming/<random>/ first, then:
done = store.install("/srv/buildzr/incoming/abc", "pr/42")
print(done.release, done.previous_model_hash)          # r-0001 None
store.rollback("pr/42")                                # current and previous swap; refused when there is no previous
```

- `install` accepts only a folder under `incoming/` of the same store. It renames the folder to `sites/<key>/r-<n+1>/` and writes `buildzr-store.json` through a temporary file (flushed to disk, then `os.replace`). Then it updates the routes in memory, deletes the release older than the previous one, and appends a line to `deploys.log`.
- After a crash at any of these steps, opening the store again finds a consistent store: either the old state or the new one, with no folder that the file does not list.
- `Store.open(..., grace=SECONDS)` keeps a deleted release on disk for that many seconds before it removes it, so that a request that started on it can finish. The default `0` removes it at once. The deploy listener opens its store with `DEPLOY_GRACE_SECONDS` (30).
