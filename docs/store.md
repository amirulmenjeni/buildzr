# The site store

A **store** is a folder in which one `buildzr serve` process keeps several built sites, each at its own address. One site might be the main model at `/`, another a preview of a pull request at `/pr/42/`. Each site has its own viewer, its own [Model API](model-api.md) and its own `llms.txt`.

!!! note "Filling a store"
    `buildzr serve --store DIR` serves a store **read-only**. With `--accept-deploys` the same instance also accepts uploads from `buildzr deploy` on a second listener that only this machine can reach; see [deploying to an instance](deploy.md). The Python functions at the end of this page do the same steps for tests and scripts.

## Words used here

| Word | Meaning |
|---|---|
| **site** | The folder `buildzr build` writes: the viewer, `data/` and `build.json`. |
| **site path** | Where a site sits below the root of the instance. Empty means the root; `pr/42` is served at `/pr/42/`. |
| **release** | One copy of a site in the store (`r-0007`). The store keeps the **current** and the **previous** release of every site. |

## Layout of a store folder

| Path in the store | What it is |
|---|---|
| `buildzr-store.json` | Marks the folder as a store. For each site path it lists the current and the previous release and the `modelHash` of each. |
| `sites/<key>/r-0007/` | One release: an ordinary built site. `<key>` is the first 16 hex characters of the sha256 of the site path, so a site path never becomes a folder name and a path such as `../x` cannot reach the file system. |
| `incoming/<random>/` | Sites being unpacked and checked. Emptied whenever the store is opened. |
| `.buildzr-store.lock` | An empty file the instance that accepts deploys keeps locked while it runs, so a second one cannot start on the same store and a read-only `serve --store` started meanwhile does not clean up what a deploy is writing. |
| `deploys.log` | One JSON line per install or rollback. Lines written by the deploy listener have the fields of [the audit log](deploy.md#the-audit-log); lines written by the Python functions below have `time`, `sitePath`, `release`, `modelHash`, `previousModelHash`, `action` and `result`. |

When the store is opened, `buildzr` reads `buildzr-store.json` strictly. A file that is not JSON, has the wrong shape, has an unknown `version`, lists a release folder that is missing, or names a release that would leave `sites/` is reported as one line (`buildzr: error: buildzr-store.json: ...`), never as a traceback. Release folders that the file does not list (left by an interrupted install) are deleted.

## Site paths

A site path is made of segments separated by `/`:

- each segment matches `[a-z0-9][a-z0-9._-]*` (lower case letters, digits, `.`, `_`, `-`; it starts with a letter or digit);
- no empty segment, no `.` or `..`, no backslash, no NUL byte;
- a leading or trailing `/` is removed; at most 8 segments and 128 characters.

**Reserved names.** These segment names are refused anywhere in a site path: `api`, `assets`, `data`, `_buildzr`, `index.html`, `build.json`, `llms.txt`. They are the names of things inside a site (and of the store's own address), so a nested site can never hide a file of the site above it. `pr/42` is fine; `data/x` and `pr/api` are refused.

## How a URL finds its site

For a request the instance does this, in order:

1. **Normalise the path.** Percent-escapes are decoded **once**. A request is answered `404` if the result contains a backslash, a NUL byte or another control character, an empty segment (`/a//b`), or a `.` or `..` segment. A second decoding never happens, so `%252e%252e` stays the text `%2e%2e` and is just a file name that does not exist.
2. **Pick the site.** The site is the registered site path that is the longest prefix of the URL **on whole segments**. `/pr/42/data/index.json` goes to `pr/42`; `/pr/420/` does **not** match `pr/42`. The root site (`""`) takes what no other site claims. A reserved name never changes this: `/pr/42/data/x` always belongs to `pr/42`.
3. **Add the slash.** `/pr/42` is answered `308 Permanent Redirect` to `/pr/42/` (the query string is kept), because the viewer's relative links only work under a URL that ends in `/`.
4. **Look inside the release.** The rest of the URL is looked up in the current release of that site with the same rule as plain `serve`: the file must be inside the release folder (symbolic links that leave it give `404`), there are no folder listings, and a folder asked for without its closing `/` is redirected.

If the store has no site at the root, `/` shows a small page that lists the sites. An unknown address is `404`; for an address that looks like the API (`.../api/v1/...`, `/_buildzr/...`) the `404` is [problem details](model-api.md) JSON.

## Opening a viewer during a change

Someone may have a viewer open while a new release is installed. The viewer loaded `data/index.json` of the old release and will ask for scene files of that release later. Scene files, the model file (`data/model.<h8>.json`) and the files in `assets/` have a content hash in their name, so a file with a given name always has the same content. So:

- when such a file is **not** in the current release, the instance looks for it in the **previous** release of the same site and serves it from there;
- `data/index.json`, `index.html`, `build.json` and `llms.txt` are **never** taken from the previous release; they always come from the current one;
- after two newer installs the old release is gone, and a viewer that still holds it shows a load error. Reloading the page fixes it.

A request that has started keeps the release it started with, even if a new release is installed while it is being answered.

## Reading the store

To have something to read, deploy two sites to an instance: the main model at the root and a preview at `pr/42`. This page uses a very small model:

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
/home/you/shop/architecture/model.py: 2 elements, 1 relationships, 0 views, 1 levels -> /tmp/tmpab12cd/.build-x1y2z3/export
built (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)
uploading 12 files, 517 KB to http://127.0.0.1:8001 (the root site)
deployed /: release r-0001, modelHash sha256:87716f3c5b04…
open: https://preview.example.com/
api:  https://preview.example.com/api/v1/

$ PR_NUMBER=42 buildzr deploy -t preview
/home/you/shop/architecture/model.py: 2 elements, 1 relationships, 0 views, 1 levels -> /tmp/tmpab12cd/.build-x1y2z3/export
built (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)
uploading 12 files, 517 KB to http://127.0.0.1:8001 (path pr/42)
deployed pr/42: release r-0001, modelHash sha256:87716f3c5b04…
open: https://preview.example.com/pr/42/
api:  https://preview.example.com/pr/42/api/v1/
```

`GET /_buildzr/v1/sites` lists the sites, so a script or AI assistant that knows only the host can find them:

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

The addresses start with `/` when the instance was started without `--public-url` (`"viewerUrl": "/pr/42/"`). Here the instance was started with `--public-url https://preview.example.com`.

- `name` is the workspace name of the site's model (what the model was called in the DSL), so a reader can tell `pr/41` from `pr/42` without opening either.
- `viewerUrl` is `null` for a site that has no viewer (a data-only site, with no `index.html`), with or without `--public-url`. `apiUrl` is always there.
- `previousModelHash` is `null` when the site has no previous release. `name`, `elements` and `relationships` are `null` when the release's model cannot be read (`name` also when the model has no workspace name).
- With `--public-url https://models.example.com` the two URLs start with that address (`https://models.example.com/pr/42/`).
- The answer has an `ETag` that changes when any site, release or `modelHash` changes; `If-None-Match` gets `304`. As in the Model API there are no CORS headers unless `--cors-origin` is given.
- Every other address under `/_buildzr/` is `404`.

Each site's own API lives next to it, `/pr/42/api/v1/`, with `/pr/42/llms.txt`. Its `viewerUrl` links carry the site path, so a link from `/pr/42/api/v1/element?id=billing` opens `/pr/42/#/m/billing?sel=billing`.

## `buildzr serve --store`

```text
buildzr serve --store DIR [-p PORT] [--host HOST] [--public-url URL] [--cors-origin ORIGIN]...
```

The first start of an instance that accepts deploys makes the store folder. After that, the same folder can be served read only:

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

- `--store DIR` cannot be combined with a site `DIR`. The folder must already be a store (it has `buildzr-store.json`), except together with `--accept-deploys`, which makes it.
- The server is read-only: only GET and HEAD are answered. Any other method gets `405` (with problem details) under `/api/v1/` and `/_buildzr/`, and `501` elsewhere. It never writes a file in the store.
- Restarting the server reads `buildzr-store.json` again, so the same sites are served after a restart. A read-only server does not see deploys made after it started, because it keeps its list of sites in memory. Restart it, or let the instance that accepts deploys do the reading too (one instance per store).
- `buildzr serve DIR` (one site) is unchanged and has no `/_buildzr/` address.

## What is not there yet

- Any way to change a store through the reading listener. Without `--accept-deploys` nothing in `serve --store` can write; with it, only the separate deploy listener can.
- Removing a site from a store.

## Python functions (for scripts and tests)

```python
from buildzr.site.store import Store

store = Store.open("/srv/buildzr", create=True)        # makes the folder when it is missing or empty
# a checked site is moved into incoming/<random>/ first, then:
done = store.install("/srv/buildzr/incoming/abc", "pr/42")
print(done.release, done.previous_model_hash)          # r-0001 None
store.rollback("pr/42")                                # current and previous swap; refused when there is no previous
```

- `install` accepts only a folder under `incoming/` of the same store. It renames the folder to `sites/<key>/r-<n+1>/`, writes `buildzr-store.json` through a temporary file (flushed to disk, then `os.replace`), updates the routes in memory, deletes the release older than the previous one and appends a line to `deploys.log`.
- After a crash at any of these steps, opening the store again finds a consistent store: either the old state or the new one, with no folder that the file does not list.
- `Store.open(..., grace=SECONDS)` keeps a pruned release on disk that long before deleting it (default `0`: at once), so a request that started on it can finish. The deploy listener opens its store with `DEPLOY_GRACE_SECONDS` (30).
