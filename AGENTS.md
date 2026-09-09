# AGENTS.md

## Development environment

Use the repository devcontainer for all development and testing. Do not run the
project's test suite, type checks, documentation builds, or package builds on
the host machine. This keeps Python, Java, uv, and the Structurizr tooling
consistent with CI.

Start or rebuild the devcontainer with the Dev Container CLI or VS Code, then
run commands from `/workspace/buildzr` inside the container. For example:

```bash
devcontainer up --workspace-folder .
devcontainer exec --workspace-folder . uv sync --all-extras --locked
devcontainer exec --workspace-folder . uv run pytest --mypy tests
```

Use the devcontainer's installed Structurizr CLI when running workspace
validation tests. When testing a specific supported Python interpreter, pass
that interpreter to uv inside the container, for example:

```bash
devcontainer exec --workspace-folder . uv run --python 3.13 pytest --mypy tests
```

Host-side inspection, editing, and Git operations are fine, but validation must
be performed inside the devcontainer.
