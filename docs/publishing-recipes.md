# Recipes

Each recipe on this page reaches one goal that people often ask about, such as a preview of every pull request or a rollback. The recipes combine the commands described on the [Command reference](cli.md), [`buildzr.yaml`](config.md) and [Deploying to an instance](deploy.md) pages.

The documentation tests run every command and every file on this page against a real instance. The only exceptions are the blocks marked as an example you must adapt.

## Words used on this page

| Word | Meaning |
|---|---|
| **site** | The folder that `buildzr build` writes: the viewer, the model data and `build.json`. |
| **deploy** | To copy a built site to a target with `buildzr deploy`. |
| **instance** | A running `buildzr serve --store DIR`: one process that serves every site of a store. With `--accept-deploys`, it also accepts new sites from `buildzr deploy`. |
| **server** | The machine on which the instance runs. |
| **reading listener** | The port at which readers open the sites (default 8000). |
| **deploy listener** | The port of an instance that accepts uploads from `buildzr deploy` (default 8001). It listens only on `127.0.0.1`. |
| **target** | A named destination in `buildzr.yaml`. A `url` target points to a deploy listener. |
| **site path** | Where a site sits on the instance. The site path `pr/42` is served at `/pr/42/`. |
| **release** | One copy of a site on an instance. The instance keeps the current and the previous release of every site path. |
| **preview** | A site deployed for one pull request, at a site path such as `pr/42`. |
| **data-only site** | A site without the viewer, only the model data. |

## The model used by the recipes

The recipes use this small model. Save it as `architecture/model.py`:

<!-- doctest: file architecture/model.py -->
```python
from buildzr.dsl import Workspace, Person, SoftwareSystem

with Workspace("shop") as w:
    customer = Person("Customer")
    shop = SoftwareSystem("Shop")
    customer >> "Buys from" >> shop
```

## A preview for every pull request

Goal: each pull request gets its own preview at `https://preview.example.com/pr/<number>/`, built from the branch of that pull request.

You need two things: an instance that keeps running on a server, and a job in your CI (continuous integration) system that deploys to it.

### Start the instance

On the server, start an instance that accepts deploys. Readers reach it on port 8000. Deploys arrive on `127.0.0.1:8001`, which only the server itself can reach.

```text
$ buildzr serve --store /srv/buildzr --host 0.0.0.0 --public-url https://preview.example.com --accept-deploys
Serving store /srv/buildzr (0 sites) at http://0.0.0.0:8000/ (read only)
Accepting deploys at http://127.0.0.1:8001/ (this machine only; no authentication)
```

Put your web server or proxy in front of port 8000, for `https://preview.example.com`. **Never** point it at port 8001. Read the [security model](deploy.md#the-security-model-in-plain-words) before you set up the proxy.

### Name the target

In the repository, add the instance as a target in `buildzr.yaml`. The CI job reaches the deploy listener through an SSH tunnel, so on the machine of the job the address is `127.0.0.1:9001`. The `path` takes the pull request number from the environment variable `PR_NUMBER`:

```yaml
workspace: architecture/model.py
targets:
  preview: {url: "http://127.0.0.1:9001", path: "pr/${PR_NUMBER}"}
```

If `PR_NUMBER` is not set, `deploy` refuses to run:

```text
$ buildzr deploy -t preview
buildzr.yaml:3: targets.preview.path: environment variable PR_NUMBER is not set (used in "pr/${PR_NUMBER}")
[exit code 2]
```

With `PR_NUMBER` set and the tunnel open, the job is one command:

```text
$ PR_NUMBER=42 buildzr deploy -t preview
built (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)
uploading 12 files, 517 KB to http://127.0.0.1:9001 (path pr/42)
deployed pr/42: release r-0001, modelHash sha256:87716f3c5b04…
open: https://preview.example.com/pr/42/
api:  https://preview.example.com/pr/42/api/v1/
```

The last two lines are the links to post in a comment on the pull request. When you deploy the same pull request again, the new site replaces the one at `pr/42`. The instance keeps the current and the previous release of each site path.

### Write the CI workflow

!!! warning "An example you must adapt"
    This workflow could not be run on GitHub when this page was written, so the documentation tests skip it. Its `buildzr deploy` command is the one tested above; the rest is standard GitHub Actions and SSH. Check the names of the secrets, the host name and the user before you rely on it.

The job installs uv and Node.js, opens the tunnel with an SSH key that is kept in a repository secret, and deploys. In the `ssh` command, `ExitOnForwardFailure` makes `ssh` stop with an error if it cannot open the tunnel, and `-f` moves `ssh` to the background once the tunnel is open.

<!-- doctest: skip GitHub Actions workflow, cannot be run outside GitHub -->
```yaml
name: Architecture preview
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  preview:
    runs-on: ubuntu-latest
    env:
      PR_NUMBER: ${{ github.event.pull_request.number }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v7
      - uses: actions/setup-node@v7 # the layout step of the build needs Node.js 18 or newer
        with:
          node-version: 22
      - name: Open the SSH tunnel to the instance
        env:
          SSH_KEY: ${{ secrets.PREVIEW_SSH_KEY }}
          KNOWN_HOSTS: ${{ secrets.PREVIEW_KNOWN_HOSTS }}
        run: |
          install -m 700 -d ~/.ssh
          printf '%s\n' "$SSH_KEY" > ~/.ssh/id_deploy
          chmod 600 ~/.ssh/id_deploy
          printf '%s\n' "$KNOWN_HOSTS" > ~/.ssh/known_hosts
          ssh -i ~/.ssh/id_deploy -o ExitOnForwardFailure=yes -f -N \
            -L 9001:127.0.0.1:8001 deploy@preview.example.com
      - run: uvx --from "buildzr[serve]" buildzr deploy -t preview
```

Notes:

- The tunnel command is the one from [Deploying to an instance](deploy.md#2-reach-the-deploy-listener-from-your-machine-or-ci). Whoever can open the tunnel can deploy, so use an SSH key that is good for nothing else.
- Pull requests from forks do not get repository secrets, so the job fails for them. Run previews only for branches of the repository.
- The `serve` extra installs `jsonschema`. With it, `deploy` runs the full site check on the machine of the job before it sends the site. Without it, `deploy` prints one warning, and the instance still runs the full check.
- There is no command yet to remove a site from an instance. The preview of a closed pull request stays until you delete it by hand. See [The site store](store.md#what-is-not-there-yet).

## A site for programs only

Goal: deploy the model for scripts, CI jobs, dashboards and AI assistants, without the viewer.

Set `viewer: false` on the target, or pass `--no-viewer` to `deploy`:

<!-- doctest: merge -->
```yaml
workspace: architecture/model.py
targets:
  model: {url: "http://127.0.0.1:8001", path: model, viewer: false}
```

```text
$ buildzr deploy -t model
built (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)
uploading 6 files, 12 KB to http://127.0.0.1:8001 (path model)
deployed model: release r-0001, modelHash sha256:87716f3c5b04…
api:  https://preview.example.com/model/api/v1/
```

The site has 6 files instead of 12, because the viewer is left out. `deploy` prints no `open:` line, because there is no viewer to open. The `api:` line is always printed.

The [Model API](model-api.md) works as on any other site. One field changes: `viewerUrl`, the link in every answer that opens an element in the viewer. A data-only site has no viewer to link to, so `viewerUrl` is `null` in every answer, with or without `--public-url`. The orientation document of the API says so in its `notes` field.

The request below shows such an answer. It was sent to a data-only site of the larger example model `examples/buildzr_models_example.py` from the buildzr repository, because the small shop model has no element that matches `mongo`:

<!-- doctest: api data-only -->
```http
GET /api/v1/elements?q=mongo
```

```json
{
  "apiVersion": "1",
  "modelHash": "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35",
  "total": 1,
  "items": [
    {
      "id": "e-commerce-system/database",
      "name": "Database",
      "type": "Container",
      "parent": "e-commerce-system",
      "description": null,
      "technology": "MongoDB",
      "tags": [
        "Element",
        "Container"
      ],
      "childCount": 0,
      "viewerUrl": null,
      "matched": "technology"
    }
  ],
  "next": null,
  "truncated": false
}
```

## Rolling back a bad deploy

Goal: the last deploy of a site was wrong, and readers must see the release before it, now.

An instance keeps the **current** and the **previous** release of every site path. Suppose you deployed the preview twice. The second time, the model had a Mail system added. This is the second version of `architecture/model.py`:

<!-- doctest: file architecture/model.py -->
```python
from buildzr.dsl import Workspace, Person, SoftwareSystem

with Workspace("shop") as w:
    customer = Person("Customer")
    shop = SoftwareSystem("Shop")
    mail = SoftwareSystem("Mail")
    customer >> "Buys from" >> shop
    shop >> "Sends receipts through" >> mail
```

The second deploy creates release `r-0002`:

```text
$ PR_NUMBER=42 buildzr deploy -t preview
built (3 elements, 2 relationships, 0 views; modelHash sha256:3f8e56fad26b…)
uploading 12 files, 518 KB to http://127.0.0.1:9001 (path pr/42)
deployed pr/42: release r-0002, modelHash sha256:3f8e56fad26b… (previous sha256:87716f3c5b04…)
open: https://preview.example.com/pr/42/
api:  https://preview.example.com/pr/42/api/v1/
```

To go back, roll back. Nothing is built or uploaded; the instance swaps the two releases:

```text
$ PR_NUMBER=42 buildzr deploy -t preview --rollback
rolled back pr/42: release r-0001 is current again, modelHash sha256:87716f3c5b04… (was sha256:3f8e56fad26b…)
open: https://preview.example.com/pr/42/
api:  https://preview.example.com/pr/42/api/v1/
```

Things to know:

- To see what a rollback would do without doing it, add `--dry-run`. It prints `dry run: would roll back path pr/42 at http://127.0.0.1:9001; nothing was sent`.
- A second rollback goes forward again, because the two releases swap each time. After a third deploy, the oldest release is gone, so a rollback goes back one step only.
- If the site has no previous release, the command stops with `nothing to roll back to` and exit code 1.
- `--rollback` works only for `url` targets. A `dir` target keeps no previous copy. To go back, check out the older version of your model and run `buildzr deploy` again. To get exactly the same site, keep the built site of each release (for example as a CI artifact) and deploy it with `buildzr deploy --from DIR`.
- A reader who has the viewer open during a rollback or a deploy can keep working: the instance serves the files of the old release from the previous release. After two newer deploys, those files are gone, and reloading the page fixes it. See [The site store](store.md#opening-a-viewer-during-a-change).

## Several models on one instance

Goal: one instance shows the models of several teams or repositories, each at its own address.

Give each model its own site path: every repository gets a target with a different `path`. In repository A:

<!-- doctest: merge -->
```yaml
workspace: architecture/model.py
targets:
  shared: {url: "http://127.0.0.1:9001", path: billing}
```

Repository B has the same file with `path: crm`.

You can also choose the site path for one run with `--path`, which overrides the `path` of the target. The second command below deploys another model file, `other/model.py`, to `crm`:

<!-- doctest: file other/model.py -->
```python
from buildzr.dsl import Workspace, Person, SoftwareSystem

with Workspace("crm") as w:
    agent = Person("Support Agent")
    crm = SoftwareSystem("CRM")
    agent >> "Looks up customers in" >> crm
```

```text
$ buildzr deploy -t shared
built (3 elements, 2 relationships, 0 views; modelHash sha256:3f8e56fad26b…)
uploading 12 files, 518 KB to http://127.0.0.1:9001 (path billing)
deployed billing: release r-0001, modelHash sha256:3f8e56fad26b…
open: https://preview.example.com/billing/
api:  https://preview.example.com/billing/api/v1/

$ buildzr deploy -t shared --path crm -w other/model.py
built (2 elements, 1 relationship, 0 views; modelHash sha256:5a1f07c2b9d0…)
uploading 12 files, 517 KB to http://127.0.0.1:9001 (path crm)
deployed crm: release r-0001, modelHash sha256:5a1f07c2b9d0…
open: https://preview.example.com/crm/
api:  https://preview.example.com/crm/api/v1/
```

A program that knows only the host name can list the sites. Each site has its own viewer link and API address. The answer below is shortened to its first site:

<!-- doctest: api instance shape -->
```http
GET /_buildzr/v1/sites
```

```json
{
  "apiVersion": "1",
  "sites": [
    {
      "sitePath": "billing",
      "name": "shop",
      "currentRelease": "r-0001",
      "modelHash": "sha256:3f8e56fad26b",
      "previousModelHash": null,
      "elements": 3,
      "relationships": 2,
      "viewerUrl": "https://preview.example.com/billing/",
      "apiUrl": "https://preview.example.com/billing/api/v1/"
    }
  ]
}
```

Site paths follow [the site path rules](store.md#site-paths): lower-case letters, digits, `.`, `_` and `-`, separated by `/`. Some names are reserved: `api`, `assets`, `data`, `_buildzr`, `index.html`, `build.json` and `llms.txt`. A site at `billing` and another at `billing/v2` can exist side by side; a request goes to the site with the longest matching site path.

## Sharing a link to one element

Goal: send a colleague a link, or put one in a ticket, that opens the viewer at one element.

The viewer keeps the state of the screen in the part of the address after `#`, the **hash**. A link with a hash therefore opens the same element at the same level. You can write the hash by hand:

| To open... | Write |
|---|---|
| The landscape (the top level of the model) | `#/m` |
| A box that contains other boxes, expanded | `#/m/billing?sel=billing` |
| One element inside a box, selected | `#/m/billing?sel=billing/api` |
| A view that the authors drew | `#/v/billing-containers` |
| A box with a search and a tag filter on | `#/m/billing?q=pay&tags=PCI` |

```text
#/m
#/m/billing?sel=billing
#/m/billing?sel=billing/api
#/v/billing-containers
#/m/billing?q=pay&tags=PCI
```

Put the hash after the address of the site: `https://preview.example.com/pr/42/#/m/billing?sel=billing/api`. [Viewer links](viewer-hash-routes.md) describes the full grammar.

You can also take the link from the [Model API](model-api.md) instead of writing it. Every element in an answer carries its link in the field `viewerUrl`. Ask for the element and use that field. This example asks the API of a site built from `examples/buildzr_models_example.py`:

<!-- doctest: api example -->
```http
GET /api/v1/elements?q=repository
```

```json
{
  "apiVersion": "1",
  "modelHash": "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35",
  "total": 1,
  "items": [
    {
      "id": "e-commerce-system/order-service/order-repository",
      "name": "Order Repository",
      "type": "Component",
      "parent": "e-commerce-system/order-service",
      "description": null,
      "technology": null,
      "tags": [
        "Element",
        "Component"
      ],
      "childCount": 0,
      "viewerUrl": "/#/m/e-commerce-system/order-service?sel=e-commerce-system/order-service/order-repository",
      "matched": "name"
    }
  ],
  "next": null,
  "truncated": false
}
```

The link starts with `/` because this site was served without `--public-url`. When you start `buildzr serve` with `--public-url https://preview.example.com`, the links are complete: `https://preview.example.com/pr/42/#/m/...`. An instance needs the option once, for all its sites. `buildzr serve` never guesses the address from the request.

Links follow **names**. The id of an element is made from the names of its parents and its own name. Renaming an element changes its id: an old link then opens the nearest box that still exists, and the viewer says so. Two siblings with the same name get `-2`, `-3` in model order. Adding an earlier sibling with the same name can therefore make an old link open a different element. See [Viewer links](viewer-hash-routes.md#what-a-link-restores-and-what-it-cannot).
