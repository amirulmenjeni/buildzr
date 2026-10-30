<!-- --8<-- [start:home] -->
# buildzr

[![Build](https://github.com/amirulmenjeni/buildzr/actions/workflows/build.yml/badge.svg)](https://github.com/amirulmenjeni/buildzr/actions/workflows/build.yml)
[![PyPI version](https://img.shields.io/pypi/v/buildzr.svg)](https://pypi.org/project/buildzr/)
[![Python versions](https://img.shields.io/pypi/pyversions/buildzr.svg)](https://pypi.org/project/buildzr/)

**Define your C4 software architecture in Python, then build it and explore it in an interactive browser viewer.**

[![Try buildzr in your browser][demo-button]][demo]

No install: edit a model and watch the viewer update.

- **Write architecture as code.** Describe people, systems, containers and components with Python `with` blocks and `>>` relationships.
- **See it in your browser.** One command, `buildzr serve`, builds your model and serves a viewer that you can zoom, search and link to.
- **Stay compatible.** buildzr produces standard [Structurizr](https://structurizr.com/) workspaces, so other Structurizr tools can read your model.

![The buildzr viewer showing an AWS deployment view: two regions, each with a DNS router, a load balancer, an autoscaling group running the web application and an RDS MySQL database, drawn with AWS icons; one load balancer is selected and its details are in the right panel][viewer-image]

## Try it now

The quickest way is the [in-browser demo][demo]: edit a model and run it, with nothing to install.

To run buildzr on your machine, install [uv](https://docs.astral.sh/uv/getting-started/installation/) (it finds or fetches a compatible Python) and run:

```bash
uvx buildzr serve --example
```

<!-- DEPENDS ON feature/serve-example (bundled prebuilt example and `serve --example`); do not merge this README before it. -->
This serves a bundled example workspace and prints its address. Open it to explore the interactive viewer. You do not need a project, a model file or Node.js. If you prefer a browser tab, press **Run Code** on the [complete Quick Start example][try-it]: it runs without installing anything.

## Use buildzr with your coding agent

Let your coding agent model your architecture for you. The buildzr skill teaches it to write model files, build them, fix build errors, serve the viewer and answer questions about your model.

Install the skill in your project:

```bash
npx skills add amirulmenjeni/buildzr
```

Then ask your agent:

```text
Use buildzr to model the architecture of this repository. Read the code, create or update
the model in workspaces/, add a system context view and a container view, build it, and
tell me how to open it with buildzr serve.
```

The agent builds the model and tells you how to open the viewer. See [Use buildzr with AI agents][ai-agents] for the requirements and what the agent can do.

## Quick Start

To write a model yourself, start a project. You need:

- Python 3.11 or newer.
- Node.js 18 or newer: when buildzr builds your model, its layout step runs on Node. Check it with `node --version`.
- [uv](https://docs.astral.sh/uv/getting-started/installation/). With pip, install with `pip install buildzr` instead of `uv add buildzr`.

Create a project and install buildzr:

```bash
uv init hello-buildzr
cd hello-buildzr
uv add buildzr
mkdir workspaces
```

Save this model as `workspaces/hello.py`:

<!-- doctest: file workspaces/hello.py -->
```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    StyleElements,
    SystemContextView,
)

with Workspace('hello') as w:
    user = Person('User', description='A user of the system')
    system = SoftwareSystem(
        'Web Application',
        description='Our main web application'
    )

    user >> "Uses" >> system

    StyleElements(
        on=[user],
        shape='Person'
    )

    SystemContextView(
        software_system_selector=system,
        key='system-context',
        description='System Context View',
        auto_layout='tb'
    )
```

Build and serve it:

```bash
uv run buildzr serve
```

Open <http://127.0.0.1:8000/>. The viewer shows your model; click a box to see its details. The [Quick Start tutorial][quick-start] explains each step.

## What you can do

- **Model in Python.** Nest elements with `with`, connect them with `>>`, group them, and extend an existing workspace. The DSL is type-hinted, so your editor can complete it.
- **Draw the views you need.** System landscape, system context, container, component, dynamic and [deployment views][views], with styles and cloud-provider [themes][themes] (AWS, Azure, Google Cloud, Kubernetes, Oracle Cloud).
- **Build and serve.** `buildzr build` writes each workspace as static web pages. `buildzr serve` builds what changed and serves them on your machine. See [Serve your workspaces][serve].
- **Explore in the viewer.** Expand and collapse boxes, search, filter by type or tag, inspect relationships, switch between light and dark themes, and share a [link to one view or element][viewer-links].
- **Export.** Save Structurizr JSON, and PlantUML, SVG or PNG files (these need Java; see [Export][export]).
- **Query your model.** `buildzr serve` also exposes a read-only JSON [Model API][model-api] for scripts and CI jobs.
- **Run the examples in your browser.** Every example in the documentation has a **Run Code** button that runs it without installing anything.

## Learn more

- Documentation: the [user guides][user-guide], the [command reference][cli] and the [API reference][api].
- [Roadmap][roadmap]: what is planned and what is done.
- [Contributing][contributing]: how to report an issue or send a change.

Found a problem? Check the [issue tracker][issues] for known issues, and open one if something does not work.

buildzr is released under the [MIT License][license].
<!-- --8<-- [end:home] -->

[viewer-image]: docs/images/viewer/readme-aws-deployment.png
[demo]: https://buildzr.dev/latest/demo/
[demo-button]: https://img.shields.io/badge/%E2%96%B6%20Try%20the%20live%20demo-0969da?style=for-the-badge
[quick-start]: https://buildzr.dev/latest/getting-started/quick-start/
[try-it]: https://buildzr.dev/latest/getting-started/quick-start/#6-compare-your-file-with-the-complete-example
[views]: https://buildzr.dev/latest/user-guide/views/
[themes]: https://buildzr.dev/latest/user-guide/themes/
[serve]: https://buildzr.dev/latest/serve-workspaces/
[viewer-links]: https://buildzr.dev/latest/viewer-hash-routes/
[export]: https://buildzr.dev/latest/user-guide/export/
[model-api]: https://buildzr.dev/latest/model-api/
[ai-agents]: https://buildzr.dev/latest/getting-started/ai-agents/
[user-guide]: https://buildzr.dev/latest/user-guide/core-concepts/
[cli]: https://buildzr.dev/latest/cli/
[api]: https://buildzr.dev/latest/api/dsl/
[roadmap]: https://buildzr.dev/roadmap/
[contributing]: https://buildzr.dev/latest/contributing/
[issues]: https://github.com/amirulmenjeni/buildzr/issues
[license]: https://github.com/amirulmenjeni/buildzr/blob/master/LICENSE.md
