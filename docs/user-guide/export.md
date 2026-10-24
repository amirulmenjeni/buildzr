# Export

A buildzr workspace can be exported as Structurizr JSON, or rendered through
PlantUML as `.puml` source, SVG, or PNG. The way to do it is the `buildzr export`
command. It runs a model file and writes **every workspace the file creates**, or
the one you pick, so the model file does not need any export code.

!!! tip "Download an image from the viewer"
    The viewer can also save the diagram on screen as a PNG or SVG, in your browser, with its own layout and colours. See [Download the diagram as an image](../ui-settings.md#download-the-diagram-as-an-image). The command below draws with PlantUML instead.

## Formats

| Format       | Output                                  |
|--------------|-----------------------------------------|
| `json`       | One Structurizr JSON file, `workspace.json` (default) |
| `plantuml`   | One `.puml` file per view               |
| `svg`        | One `.svg` file per view (plus `.puml`) |
| `png`        | One `.png` file per view (plus `.puml`) |

```bash
buildzr export workspaces/shop.py                      # export/shop/workspace.json
buildzr export workspaces/shop.py --pretty -o out      # indented JSON in out/
buildzr export workspaces/shop.py -f plantuml -f svg   # .puml and .svg files
buildzr export workspaces/shop.py -f png --layout smetana
buildzr export workspaces/many.py --workspace "Billing"   # one workspace of several
```

Every option is in the [command reference](../cli.md#buildzr-export). To get the
content in memory instead of on disk (for example in a Jupyter notebook), use the
methods of the workspace:

```python
# no-run: needs Java for the PlantUML export, and the workspace w of your model
json_str = w.to_json()        # str
puml = w.to_plantuml()        # Dict[view_key, puml_source]
svg = w.to_svg()              # Dict[view_key, svg_source]; accepts layout=...
```

## Requirements

| Format       | Requirements                                                                                   |
|--------------|------------------------------------------------------------------------------------------------|
| `json`       | Nothing extra                                                                                  |
| `plantuml`   | `buildzr[export-plantuml]` and Java 11+                                                        |
| `svg`, `png` | As for `plantuml`, plus Graphviz `dot` on `PATH` (or set via `GRAPHVIZ_DOT`), unless you use `--layout smetana` |

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
mise exec java@temurin-21 -- buildzr export model.py -f svg
```

## Output files and paths

`buildzr export FILE -o DIR` writes one subfolder of `DIR` (default `export`) for
each workspace, named after the workspace: `Workspace('Big Bank plc')` is written
to `DIR/big-bank-plc/`. Two workspaces with the same name get `-2`, `-3` and so
on. In the subfolder:

- `workspace.json` is the JSON.
- Each view is written as `<view key>.<ext>`.
- `svg` and `png` also write the `.puml` source next to each image.

## Migrating from `Workspace.save()`

`Workspace.save()` is **deprecated**. It still works exactly as before and returns
the same values, but it emits a `DeprecationWarning` that points here, and it will
be removed in a future release. A model file that still calls it can be exported
with `buildzr export` unchanged: the command runs the file in a temporary folder
and silences this warning, so nothing is written next to your model.

| Before | After |
|---|---|
| `w.save(path='workspace.json')` | `buildzr export model.py -o out` (writes `out/<name>/workspace.json`) |
| `w.save(path='workspace.json', pretty=True)` | `buildzr export model.py --pretty` |
| `w.save(format='plantuml', path='d/')` | `buildzr export model.py -f plantuml -o d` |
| `w.save(format='svg', path='d/', layout='smetana')` | `buildzr export model.py -f svg --layout smetana -o d` |
| `w.save(format='png', path='d/')` | `buildzr export model.py -f png -o d` |

Differences to know:

- The files go into a subfolder per workspace, `workspace.json` and
  `<view key>.<ext>` inside it, so a file that creates several workspaces does
  not overwrite itself. `save()` took the file or folder you gave it.
- Delete the `w.save(...)` line from the model file when you can. A file
  without it also works with `buildzr build` and `buildzr serve`.
- If you need the content in a program, `to_json()`, `to_plantuml()` and
  `to_svg()` are not deprecated.
- To silence the warning while you migrate, use
  `warnings.filterwarnings("ignore", message=r"Workspace\.save\(\) is deprecated", category=DeprecationWarning)`.

## Rendering without Graphviz

Pass `--layout smetana` to use PlantUML's built-in Java port of Graphviz
instead of the `dot` executable:

```bash
buildzr export workspaces/shop.py -f svg --layout smetana -o diagrams
```

In Python, `w.to_svg(layout='smetana')` does the same in memory.

Java is still required. The trade-off is that the layout quality is somewhat
worse than with `dot`. With `--layout smetana`, the line `!pragma layout smetana`
is also written into the generated `.puml` files, so they match the images.
`to_plantuml()` takes no `layout` argument.

## Failure behaviour

`buildzr export` prints `buildzr: error: ...` and exits with 1 when something
fails, and with 2 when the file, `--workspace` or `--index` is wrong (see the
[exit codes](../cli.md#exit-codes)).

- If `jpype1` is not installed, `plantuml`, `svg` and `png` fail with the install
  hint above.
- If Graphviz is missing (with the default `dot` layout), the error says so and
  suggests `--layout smetana`. These two checks run before any file is written,
  so a run that asks for `json` and `svg` writes nothing when Graphviz is missing.
- If PlantUML reports an error instead of producing a diagram, the error is
  printed and the exit status is 1.
- `-f plantuml` never needs Graphviz.

In Python, the same problems raise `ImportError` and `PlantUmlRenderError` (a
subclass of `RuntimeError`) from `to_plantuml()` and `to_svg()`:

```python
# no-run: needs Java for the PlantUML export, and the workspace w of your model
from buildzr.sinks.plantuml_sink import PlantUmlRenderError

try:
    svgs = w.to_svg()
except PlantUmlRenderError as e:
    print(f"Rendering failed: {e}")
```
