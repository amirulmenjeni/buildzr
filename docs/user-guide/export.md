# Export

A buildzr workspace can be exported as Structurizr JSON, or rendered through
PlantUML as `.puml` source, SVG, or PNG.

## Formats

| Format       | Output                                  |
|--------------|-----------------------------------------|
| `'json'`     | One Structurizr JSON file (default)     |
| `'plantuml'` | One `.puml` file per view               |
| `'svg'`      | One `.svg` file per view (plus `.puml`) |
| `'png'`      | One `.png` file per view (plus `.puml`) |

```python
# norun
w.save()                                   # ./<workspace_name>.json
w.save(format='json', path='out/arch.json', pretty=True)
w.save(format='plantuml', path='diagrams/')
w.save(format='svg', path='diagrams/')
w.save(format='png', path='diagrams/')
```

The signature is `save(format='json', path=None, pretty=False, layout='dot')`.
`layout` applies to `plantuml`, `svg` and `png` and is ignored for `json`; an unknown
value raises `ValueError` for every format. To get the
content in memory instead of on disk (for example in a Jupyter notebook):

```python
# norun
json_str = w.to_json()        # str
puml = w.to_plantuml()        # Dict[view_key, puml_source]
svg = w.to_svg()              # Dict[view_key, svg_source]; accepts layout=...
```

## Requirements

| Format       | Requirements                                                                                   |
|--------------|------------------------------------------------------------------------------------------------|
| `json`       | Nothing extra                                                                                  |
| `plantuml`   | `buildzr[export-plantuml]` and Java 11+                                                        |
| `svg`, `png` | As for `plantuml`, plus Graphviz `dot` on `PATH` (or set via `GRAPHVIZ_DOT`), unless you use `layout='smetana'` |

Install the extra with:

```bash
pip install "buildzr[export-plantuml]"
```

[Graphviz](https://graphviz.org/download/) is needed for the default layout
engine. If `GRAPHVIZ_DOT` is set it must point to the `dot` executable;
otherwise `dot` is looked up on `PATH`.

### Getting Java without root

If you cannot install Java system-wide, a version manager such as
[mise](https://mise.jdx.dev/) can provide it for a single command:

```bash
mise exec java@temurin-21 -- python model.py
```

## Output files and paths

- Each view is written as `<view key>.<ext>`.
- For `json`, `path` is a **file** (default `./<workspace_name>.json`).
- For `plantuml`, `svg` and `png`, `path` is a **directory** (default: the
  current working directory).
- `svg` and `png` also write the `.puml` source next to each image.

`save()` returns the written file path (`str`) for `json`, and a list of
written paths for the other formats.

## Rendering without Graphviz

Pass `layout='smetana'` to use PlantUML's built-in Java port of Graphviz
instead of the `dot` executable:

```python
# norun
w.save(format='svg', path='diagrams/', layout='smetana')
svg = w.to_svg(layout='smetana')
```

Java is still required. The trade-off is that the layout quality is somewhat
worse than with `dot`. With `layout='smetana'`, the line `!pragma layout smetana`
is also written into the generated `.puml` files, so they match the images.
`to_plantuml()` takes no `layout` argument.

## Failure behaviour

- If `jpype1` is not installed, `plantuml`/`svg`/`png` raise `ImportError`
  with the install hint above.
- If Graphviz is missing (with the default `dot` layout), or PlantUML reports
  an error instead of producing a diagram, buildzr raises `PlantUmlRenderError`
  (a subclass of `RuntimeError`). The Graphviz check runs before any `.puml`
  or image file is written, although `save()` may still create the (empty)
  output directory. PlantUML syntax errors raise `PlantUmlRenderError` for both
  `svg` and `png`, and PlantUML's "Dot executable does not exist" banner is
  caught for `svg`.
- `format='plantuml'` and `to_plantuml()` never need Graphviz.

```python
# norun
from buildzr.sinks.plantuml_sink import PlantUmlRenderError

try:
    w.save(format='svg', path='diagrams/')
except PlantUmlRenderError as e:
    print(f"Rendering failed: {e}")
```

## Known limitations

The PlantUML export path currently has these limitations, tracked in
[issue #139](https://github.com/amirulmenjeni/buildzr/issues/139). The JSON
output is unaffected.

- Exporting a workspace that contains a `DynamicView` currently fails with an
  error.
- `DeploymentView` include/exclude filters are ignored in the PlantUML output.
- Using `StyleRelationships` with `thickness` makes the PlantUML export fail.
