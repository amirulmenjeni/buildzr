# Recipes

These recipes combine the pieces of the [Publishing](cli.md) section for jobs people ask about. Every command and every file shown here is run by the documentation tests against a real instance, except the blocks that say they are an example you must adapt.

All recipes use this small model. Save it as `architecture/model.py`:

<!-- doctest: file architecture/model.py -->
```python
from buildzr.dsl import Workspace, Person, SoftwareSystem

with Workspace("shop") as w:
    customer = Person("Customer")
    shop = SoftwareSystem("Shop")
    customer >> "Buys from" >> shop
```

## A preview for every pull request

Goal: each pull request gets its own copy of the diagrams at `https://preview.example.com/pr/<number>/`, built from the branch of that pull request.

You need two things: an **instance** that stays running on a server, and a **job** in your CI that deploys to it.

### The instance

On the server, start an instance that accepts deploys. Readers reach it on port 8000; deploys arrive on `127.0.0.1:8001`, which only the server itself can reach:

```text
$ buildzr serve --store /srv/buildzr --host 0.0.0.0 --public-url https://preview.example.com --accept-deploys
Serving store /srv/buildzr (0 sites) at http://0.0.0.0:8000/ (read only)
Accepting deploys at http://127.0.0.1:8001/ (this machine only; no authentication)
```

Put your web server or proxy in front of port 8000 for `https://preview.example.com`. **Never** point it at port 8001; read the [security model](deploy.md#the-security-model-in-plain-words) first.

### The target

In the repository, name the instance as a target. The job reaches the deploy port through an SSH tunnel, so on the job's machine it is `127.0.0.1:9001`. The `path` holds the pull request number from an environment variable:

```yaml
workspace: architecture/model.py
targets:
  preview: {url: "http://127.0.0.1:9001", path: "pr/${PR_NUMBER}"}
```

If `PR_NUMBER` is not set, the command refuses to run:

```text
$ buildzr deploy -t preview
buildzr.yaml:3: targets.preview.path: environment variable PR_NUMBER is not set (used in "pr/${PR_NUMBER}")
[exit code 2]
```

Set it and deploy. With the tunnel open, this is the whole job:

```text
$ PR_NUMBER=42 buildzr deploy -t preview
built (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)
uploading 12 files, 517 KB to http://127.0.0.1:9001 (path pr/42)
deployed pr/42: release r-0001, modelHash sha256:87716f3c5b04…
open: https://preview.example.com/pr/42/
api:  https://preview.example.com/pr/42/api/v1/
```

The last two lines are the links to put in a pull request comment. Deploying the same pull request again replaces the site at `pr/42` (the instance keeps the current and the previous release of each path).

### The workflow

!!! warning "An example you must adapt"
    This workflow could not be run against GitHub when this page was written, so the documentation tests skip it. The `buildzr` commands in it are the tested ones above; the rest is standard GitHub Actions and SSH. Check the names of the secrets, the host name and the user before you rely on it.

The job installs buildzr, opens the tunnel with an SSH key kept in a repository secret, and deploys. `ExitOnForwardFailure` makes `ssh` stop with an error if the tunnel cannot be made, and `-f` puts it in the background once it is up.

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
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install buildzr jsonschema
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
      - run: buildzr deploy -t preview
```

Notes:

- The tunnel command is the one from [Deploying to an instance](deploy.md#2-reach-the-deploy-listener-from-your-machine-or-ci). Whoever can open the tunnel can deploy, so use a key that is only good for this.
- Pull requests from forks do not get repository secrets. The job fails for them; run previews for branches of the repository only.
- `pip install jsonschema` lets `deploy` check the whole site on the job's machine before it sends it. Without it `deploy` prints one warning and the instance still checks everything.
- There is no command to remove a site from an instance yet. The preview of a closed pull request stays until you delete it by hand. See [the site store](store.md#what-is-not-there-yet).

## A site for programs only

Goal: publish the model for scripts, CI jobs, dashboards and AI assistants, without the viewer. Set `viewer: false` on the target, or `--no-viewer` on the command:

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

The site has 6 files instead of 12 because the viewer is left out. The [Model API](model-api.md) works as before. What changes is `viewerUrl`, the link in every answer that a person can open to see an element. There is no viewer to link to, so `viewerUrl` is `null` everywhere, with or without `--public-url`, and the orientation document says so in `notes`. The `deploy` command above prints no `open:` line for the same reason. The `api:` link is always there:

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

Goal: the last deploy of a site was wrong and readers should see the one before it, now.

An instance keeps the **current** and the **previous** release of every site path. Suppose the preview was deployed twice, the second time with a model that has a Mail system added. This is the second version of `architecture/model.py`:

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
- Rolling back twice goes forward again: the two releases swap each time. After a third deploy the older one is gone, and then a rollback goes back one step only.
- If the site has no previous release, the command stops with `nothing to roll back to` and exit code 1.
- `--rollback` works only for `url` targets. A `dir` target keeps no previous copy, so check out the older version of your model and run `buildzr deploy` again. To make that exact, keep the built site of each release (a CI artifact) and deploy it with `buildzr deploy --from DIR`.
- A reader who has the viewer open during a change keeps working: the instance still serves the files of the old release from the previous one. After two newer deploys those files are gone, and a reload fixes it. See [the site store](store.md#opening-a-viewer-during-a-change).

## Several models on one instance

Goal: one instance shows the models of several teams or repositories, each at its own address.

Each model gets its own **site path**. Give every repository a target with a different `path`. Repository A:

<!-- doctest: merge -->
```yaml
workspace: architecture/model.py
targets:
  shared: {url: "http://127.0.0.1:9001", path: billing}
```

Repository B has the same file with `path: crm`. You can also choose the path for one run with `--path`, which beats the target's `path`. This deploys another model to `crm`:

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

A program that knows only the host can list the sites. Each has its own viewer link and API address:

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

Site paths follow [these rules](store.md#site-paths): lower-case letters, digits, `.`, `_` and `-`, separated by `/`, and some names are reserved (`api`, `assets`, `data`, `_buildzr`, `index.html`, `build.json`, `llms.txt`). A site at `billing` and another at `billing/v2` can exist side by side; a request goes to the site with the longest matching path.

## Sharing a link to one element

Goal: send a colleague, or put in a ticket, a link that opens the viewer at one element.

A viewer address keeps everything after `#` as the state of the screen, so a link opens the same element at the same level. You can write one by hand. These are the forms:

| To open... | Write |
|---|---|
| The landscape | `#/m` |
| A box with things inside, expanded | `#/m/billing?sel=billing` |
| One element inside a box, selected | `#/m/billing?sel=billing/api` |
| A view the authors drew | `#/v/billing-containers` |
| A box with a search and tag filter on | `#/m/billing?q=pay&tags=PCI` |

```text
#/m
#/m/billing?sel=billing
#/m/billing?sel=billing/api
#/v/billing-containers
#/m/billing?q=pay&tags=PCI
```

Put the hash after the address of the site: `https://preview.example.com/pr/42/#/m/billing?sel=billing/api`. The full grammar is in [Viewer links](viewer-hash-routes.md).

You do not have to write them by hand. Every element in a [Model API](model-api.md) answer carries its link as `viewerUrl`. Ask for the element and use the field:

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

The link starts with `/` because this server was started without `--public-url`. Start the server with `--public-url https://preview.example.com` (an instance does this once for all its sites) and the links are complete: `https://preview.example.com/pr/42/#/m/...`. The address is never guessed from the request.

Links follow **names**. An element's id is made from the names of its parents and itself. If someone renames an element, an old link opens the nearest box that still exists and the viewer says so. If two siblings have the same name they get `-2`, `-3` in model order, so adding an earlier sibling with the same name can make an old link open a different element. See [Viewer links](viewer-hash-routes.md#what-a-link-restores-and-what-it-cannot).
