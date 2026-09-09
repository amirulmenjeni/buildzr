# Python support policy

buildzr supports maintained CPython minor versions that are compatible with
the project. The current supported matrix is Python 3.10, 3.11, 3.12, and
3.13. Package metadata enforces the lower bound with `requires-python`, while
the classifiers and GitHub Actions matrix describe the versions tested and
advertised to users.

## Rolling support

When a new CPython minor version is released, the project will revisit the
matrix and add it once the dependency and tooling stack can support it. CI
tests every advertised minor version, including the optional PlantUML,
Jupyter, documentation, and development dependencies where practical.

The oldest supported minor version is dropped only when it reaches Python
end-of-life or becomes impractical because of a dependency or tooling
constraint. Such a change will be announced in the release notes and made
with a deprecation notice before removal when feasible. This is a rolling
maintained-versions policy, not a fixed “last three versions” rule.

The `.python-version` file lists the supported minors for local uv-managed
interpreter installation. Use `uv sync --all-extras --locked --python <version>`
to create a reproducible environment for any version in the matrix.
