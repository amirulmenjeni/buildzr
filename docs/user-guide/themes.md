# Themes

Add cloud provider icons to your architecture diagrams with zero friction. `buildzr` provides auto-generated theme constants for AWS, Azure, Google Cloud, Kubernetes, and Oracle Cloud Infrastructure.

## Overview

Structurizr themes work via tag-based styling --- elements need specific tags like `"Amazon Web Services - EC2"` to receive their icons. This is powerful but requires you to know the exact tag strings.

`buildzr` solves this with IDE-discoverable theme constants:

```python
from buildzr.dsl import Workspace, SoftwareSystem, Container, StyleElements
from buildzr.themes import AWS

with Workspace('My System') as w:
    with SoftwareSystem('Cloud App') as app:
        api = Container('API Server')
        db = Container('Database')

    # Apply AWS icons with autocomplete support
    StyleElements(on=[api], **AWS.EC2)
    StyleElements(on=[db], **AWS.RDS)
```

The legend will display meaningful names like "Amazon Web Services - EC2" with the corresponding icon.

## Available Themes

| Theme | Import | Services |
|-------|--------|----------|
| **AWS** | `from buildzr.themes import AWS` | 1000+ services across all versions |
| **Azure** | `from buildzr.themes import AZURE` | 500+ services |
| **Google Cloud** | `from buildzr.themes import GOOGLE_CLOUD` | 200+ services |
| **Kubernetes** | `from buildzr.themes import KUBERNETES` | 80+ resources |
| **Oracle Cloud** | `from buildzr.themes import ORACLE_CLOUD` | 150+ services |

## Basic Usage

### Applying Theme Styles

Use the `**` unpacking operator to apply theme styles to elements:

```python
from buildzr.dsl import Workspace, SoftwareSystem, Container, StyleElements
from buildzr.themes import AWS

with Workspace('AWS Architecture') as w:
    with SoftwareSystem('E-Commerce Platform') as platform:
        web = Container('Web App', technology='React')
        api = Container('API', technology='Node.js')
        db = Container('Database', technology='PostgreSQL')
        cache = Container('Cache', technology='Redis')
        queue = Container('Message Queue', technology='SQS')

    # Apply AWS service icons
    StyleElements(on=[web], **AWS.AMPLIFY)
    StyleElements(on=[api], **AWS.LAMBDA)
    StyleElements(on=[db], **AWS.RDS)
    StyleElements(on=[cache], **AWS.ELASTICACHE)
    StyleElements(on=[queue], **AWS.SIMPLE_QUEUE_SERVICE)
```

### Discovering Available Services

Use your IDE's autocomplete to discover available services:

```python
from buildzr.themes import AWS

# Type AWS. and your IDE will show all available services:
# AWS.EC2
# AWS.LAMBDA
# AWS.RDS
# AWS.S3
# AWS.DYNAMODB
# ... and hundreds more
```

You can also list all elements programmatically:

```python
from buildzr.themes import AWS

# Get all available theme elements
for element in AWS.all_elements():
    print(element.tag)
```

## Theme Versions

Cloud providers update their icon sets over time. `buildzr` includes multiple versions:

### AWS Versions

```python
# no-run: a fragment; container and region are elements of your model
from buildzr.themes import AWS, AWS_2023_01_31, AWS_2022_04_30, AWS_2020_04_30

# AWS is an alias for the latest version (AWS_2023_01_31)
StyleElements(on=[container], **AWS.EC2)

# Use older versions for specific icons (e.g., Cloud/Region icons)
StyleElements(on=[region], **AWS_2020_04_30.CLOUD)
StyleElements(on=[region], **AWS_2020_04_30.REGION)
```

### Azure Versions

```python
from buildzr.themes import AZURE, AZURE_2023_01_24
```

### Google Cloud Versions

```python
from buildzr.themes import GOOGLE_CLOUD, GOOGLE_CLOUD_V1_5
```

### Kubernetes Versions

```python
from buildzr.themes import KUBERNETES, KUBERNETES_V0_3
```

### Oracle Cloud Versions

```python
# no-run: a fragment; db and api are elements of your model
from buildzr.themes import ORACLE_CLOUD, ORACLE_CLOUD_2023_04_01, ORACLE_CLOUD_2021_04_30, ORACLE_CLOUD_2020_04_30

# ORACLE_CLOUD is an alias for the latest version (ORACLE_CLOUD_2023_04_01)
StyleElements(on=[db], **ORACLE_CLOUD.AUTONOMOUS_DATABASE)
StyleElements(on=[api], **ORACLE_CLOUD.API_GATEWAY)
```

## Offline / Self-Contained Workspaces

The icons of `buildzr.themes` are URLs into one commit of the [structurizr/themes](https://github.com/structurizr/themes) repository (see [The Pinned Themes Commit](#the-pinned-themes-commit)). For the viewer you need nothing more: `buildzr build` and `buildzr serve` [put the icons into the built workspace](#theme-icons-at-build-time). For a workspace JSON that carries its icons itself, for example for another Structurizr tool on a machine without network, use `as_inline()` to embed icons as base64:

```python
# no-run: as_inline() fetches the icons from the network
from buildzr.dsl import Workspace, SoftwareSystem, Container, StyleElements
from buildzr.themes import AWS

with Workspace('Offline Workspace') as w:
    with SoftwareSystem('System') as sys:
        api = Container('API')

    # Embed icon as base64 (fetched at runtime)
    StyleElements(on=[api], **AWS.LAMBDA.as_inline())
```

!!! warning "Network Required at Build Time"
    `as_inline()` reads the icon from buildzr's [icon cache](#theme-icons-at-build-time), or fetches it from the pinned commit when your script runs and caches it. The resulting workspace JSON will be self-contained, but the first run needs network access. Without network and without the icon in the cache, `as_inline()` raises `buildzr.themes.assets.IconFetchError`.

## Deployment Diagrams

Themes work great with deployment views:

```python
from buildzr.dsl import (
    Workspace, SoftwareSystem, Container,
    DeploymentEnvironment, DeploymentNode, InfrastructureNode, ContainerInstance,
    DeploymentView, StyleElements
)
from buildzr.themes import AWS, AWS_2020_04_30

with Workspace('AWS Deployment') as w:
    with SoftwareSystem('My App') as app:
        web = Container('Web App', technology='Spring Boot')
        db = Container('Database', technology='MySQL')

    with DeploymentEnvironment('Production') as production:
        with DeploymentNode('Amazon Web Services') as aws:
            with DeploymentNode('us-east-1') as region:
                with DeploymentNode('EC2') as ec2:
                    ContainerInstance(web)
                with DeploymentNode('RDS') as rds:
                    ContainerInstance(db)
                elb = InfrastructureNode('Load Balancer', technology='ELB')

    # Style deployment nodes with AWS icons
    StyleElements(on=[aws], **AWS_2020_04_30.CLOUD)
    StyleElements(on=[region], **AWS_2020_04_30.REGION)
    StyleElements(on=[ec2], **AWS.EC2)
    StyleElements(on=[rds], **AWS.RDS)
    StyleElements(on=[elb], **AWS.ELASTIC_LOAD_BALANCING)

    DeploymentView(environment=production, key='deployment', software_system_selector=app,
                   description='Production deployment')
```

## Themes, Icons and Branding in the Viewer

The viewer of `buildzr build` and `buildzr serve` draws the styles of a workspace: its own `StyleElements` and `StyleRelationships`, the Structurizr themes it uses, the icons of its styles and its branding.

### Using a Theme

`apply_theme` adds a Structurizr theme to the workspace (`views.configuration.themes`). Pass a theme of `buildzr.themes` or the URL of a theme's `theme.json`:

```python
from buildzr.dsl import Workspace, SoftwareSystem, Container, StyleElements
from buildzr.themes import KUBERNETES_V0_3

with Workspace('On Kubernetes') as w:
    with SoftwareSystem('Shop'):
        api = Container('API', tags={'Kubernetes - pod'})
        gateway = Container('Gateway', tags={'Kubernetes - svc'})

    w.apply_theme(KUBERNETES_V0_3)
    # your own style of a tag the theme styles too: yours wins
    StyleElements(on=['Kubernetes - pod'], background='#ffffff')
```

The elements tagged `Kubernetes - pod` get the theme's stroke and text colour and the white background of your style.

buildzr does not download themes: it applies the styles it ships, and [fetches their icons at build time](#theme-icons-at-build-time). A theme URL is matched by the name of the folder that holds its `theme.json`, such as `kubernetes-v0.3` or `amazon-web-services-2023.01.31`, against the [themes buildzr ships](#available-themes), whatever the host: `https://static.structurizr.com/themes/kubernetes-v0.3/theme.json` and the GitHub address of `KUBERNETES_V0_3.THEME_URL` are the same theme. The styles of any other theme are not applied, and the build says so (see [Warnings](#warnings)). Add the styles you need with `StyleElements` and `StyleRelationships` instead.

### How Styles Combine

For each element, the viewer starts from the C4 default of its type (a person, a software system, a container...). It then applies the styles of the element's tags, and for each tag:

1. the styles of the themes, in the order you added the themes: a later theme wins over an earlier one;
2. then the workspace's own styles, in the order you wrote them: your style wins over every theme.

A style changes only the properties it sets: your style with only a `background` keeps the theme's stroke, text colour and icon. The tags apply in this order: `Element`, then the type tag (`Person`, `Container`...), then the element's other tags in the order the style list (the themes' styles first, then yours) first names them. Relationships work the same way, starting from the `Relationship` tag.

A theme that sets a text `color` sets it as you would: buildzr does not change it for contrast. Without a `color`, the text is black or white, whichever reads better on the fill.

The layout makes the boxes; the `width` and `height` of a style are not used.

### Icons

The viewer draws an icon above the name of a box, and before the name of a person, of a box with children (a frame) and of a boundary. The layout leaves room for it.

The viewer shows only the images that the built workspace carries, so the icons look the same from `buildzr serve`, from any static host and offline: the viewer loads nothing from other sites. The build puts in:

- **a data URI**, as it is (for example from `as_inline()`, see [Offline / Self-Contained Workspaces](#offline-self-contained-workspaces));
- **the icon of a theme buildzr ships**: the URL of a `buildzr.themes` element, such as `**KUBERNETES_V0_3.POD`, and the icons of a theme you add with `apply_theme`. The build fetches the icon from the [pinned commit](#the-pinned-themes-commit) or reads it from its cache. The same file on another branch of the GitHub repository (`https://raw.githubusercontent.com/structurizr/themes/<branch>/<theme>/<file>`) or on the Structurizr CDN (`https://static.structurizr.com/themes/<theme>/<file>`) gives the file at the pinned commit too.

An image from any other URL is not shown, and the build says so (see [Warnings](#warnings)): buildzr fetches nothing else. Embed it as a data URI instead.

An icon is a PNG, JPEG, GIF, WebP or SVG image of at most 512 KB.

### Theme Icons at Build Time

buildzr ships the styles of its themes, not their icons (about 17 MB). The build fetches the icons a workspace uses, once:

- **From where.** Only `https://raw.githubusercontent.com/structurizr/themes/<pinned commit>/...`, and only the files that the themes buildzr ships use. No redirect is followed. The build waits at most 15 seconds for an icon, and its bytes must be a PNG, JPEG, GIF, WebP or SVG image of at most 512 KB.
- **The cache.** A fetched icon is kept in `~/.cache/buildzr/themes-<commit>/` (under `$XDG_CACHE_HOME` when that is set, or under `BUILDZR_CACHE_DIR` instead of `~/.cache/buildzr`). A commit never changes, so the cache never expires: the next build reads the icon from there without network. A damaged file is fetched again. Delete the folder to reclaim the space. A new pin uses a new folder.
- **No network.** With `BUILDZR_OFFLINE=1`, buildzr fetches nothing: the icons come from the cache only.
- **Failures.** An icon that cannot be fetched (no network, a timeout, an upstream error, a file that is not an image) does not stop the build. The workspace is built without it, the build prints a [warning](#warnings) that names the icon and the reason, and `build.json` records `"incomplete": true`. Such a built workspace is never up to date, so the next `buildzr build` or `buildzr serve` builds it again, even when the model file has not changed. After the first icon whose host cannot be reached, the build takes the other icons from the cache only, so it does not wait 15 seconds for each.
- **The viewer.** The built workspace carries the icons as data, so the viewer makes no request to GitHub or any other site, online or offline.

The "Run Code" button of these docs runs buildzr in your browser and fetches no icon: the diagrams it draws have none.

The icons belong to their cloud providers and are published in the structurizr/themes repository; see each provider's terms (for example the [AWS Architecture Icons](https://aws.amazon.com/architecture/icons/)) before you publish a built workspace that carries them.

### The Pinned Themes Commit

Every theme of `buildzr.themes` and every icon URL in it names one full commit SHA of [structurizr/themes](https://github.com/structurizr/themes), never a branch such as `master`, a tag or a short SHA, which can move or become ambiguous. The commit is `buildzr.themes.assets.THEMES_COMMIT`:

```python
from buildzr.themes import AWS, assets

print(assets.THEMES_COMMIT)     # 67da2b503abc708f941e5aa2ea35dd553f742c3a
print(AWS.EC2.icon_url.startswith(assets.PINNED_BASE))  # True
```

The commit is part of buildzr, like the themes. To move the pin (buildzr maintainers):

1. Set `THEMES_COMMIT` in `buildzr/themes/assets.py` and the `@ref` line of `buildzr/themes/themes.txt` to the new full 40-digit commit SHA. The generator refuses anything else.
2. Regenerate the modules: `python -m buildzr.themes.generate --urls-file buildzr/themes/themes.txt`.
3. Run the tests. `tests/test_themes.py` checks that the two agree and that every theme and icon URL in `buildzr/` names the commit; `.github/scripts/check_wheel.py` checks the same in the built wheel and sdist.

The commit is part of the [fingerprint](../cli.md#when-a-built-workspace-is-out-of-date) of every model file, so after a new pin `buildzr build` builds every workspace again and fetches the icons of the new commit.

### Branding

`apply_branding` sets the logo and the font of the diagrams (`views.configuration.branding`):

```python
# no-run: reads logo.png from your project
import base64
from pathlib import Path

logo = 'data:image/png;base64,' + base64.b64encode(Path('logo.png').read_bytes()).decode()
w.apply_branding(logo=logo, font='Georgia, serif')
```

- **Logo.** A data URI of an image, as for icons. The viewer shows it in the lower right corner of the diagram.
- **Font.** A font family, or a list of them as in CSS, such as `'Georgia, serif'`. The viewer sets the text of the diagrams in the first one that the reader's computer has; the rest of the page stays in Inter. Without a generic family (`serif`, `sans-serif`...) at the end, Inter comes after your fonts. The viewer waits up to 3 seconds for the font before it draws the diagram.
- **Font URL.** `apply_branding(font_url=...)` keeps a web font URL in the workspace for other Structurizr tools. The viewer does not load it: it loads fonts only from the built workspace.

The layout measures text with Inter, the viewer's own font, because the build cannot know the fonts of the reader's computer. Where your font is wider than Inter, the viewer scales the label down until it is as wide as the layout made room for, so no text runs out of its box. It does so again when a font finishes loading, so the same font always gives the same picture.

An image you [download from the viewer](../ui-settings.md#download-the-diagram-as-an-image) has the icons, but not the logo. Its font is embedded only when it is Inter: a branding font from the reader's computer is not part of the file.

### Warnings

What the viewer cannot show does not stop the build. The workspace is built without it, `buildzr build` prints a warning, and `build.json` lists it under `warnings`:

```text
buildzr: warning: shop.py: theme https://example.com/themes/mine/theme.json: not a theme buildzr ships, so its styles are not applied (buildzr does not download themes). Use one from buildzr.themes, or add the styles you need with StyleElements and StyleRelationships
buildzr: warning: shop.py: icon https://raw.githubusercontent.com/structurizr/themes/67da2b503abc708f941e5aa2ea35dd553f742c3a/kubernetes-v0.3/pod-256.png: not shown, could not reach the host (Temporary failure in name resolution). The next build tries again
buildzr: warning: shop.py: icon https://example.com/logo/icon.png: not shown, the image is on another site and the viewer loads nothing from other sites (buildzr fetches only the icons of the themes it ships). Embed it instead: a data URI
```

You get one for a theme buildzr does not ship, a theme icon that could not be fetched (see [Theme Icons at Build Time](#theme-icons-at-build-time)), an image on another site, an image that is not a data URI of a supported type, is damaged or is too large, a font name that is not a font family, and a font URL. When the viewer cannot read the branding file or an image, it draws the diagram without them and says why in the browser console.

### When the Viewer Draws Them Again

Themes and branding are part of the model file, so a change to them changes the file's [fingerprint](../cli.md#when-a-built-workspace-is-out-of-date) and `buildzr build` and `buildzr serve` build the workspace again. The themes that buildzr ships and the [commit they are pinned to](#the-pinned-themes-commit) are part of its version and of the fingerprint. A built workspace that lacks a theme icon it could not fetch is built again by the next build. An image that the model file reads from another file is not part of the fingerprint, like code it imports: after you change the image, build with `--rebuild`.

## PlantUML Export with Icons

When exporting to PlantUML, icons are automatically included as sprites:

```python
# no-run: needs Java for the PlantUML export, and the workspace w of your model
# Export to PlantUML with icons
puml_dict = w.to_plantuml()

# Export to SVG (icons embedded as base64)
svg_dict = w.to_svg()
```

To write files, run `buildzr export model.py -f plantuml -f svg -o output`.

The generated PlantUML will include `AddElementTag()` directives with sprite definitions, and the legend will display service names with their icons.

## Combining with Custom Styles

Theme styles can be combined with custom styling:

```python
from buildzr.dsl import Workspace, SoftwareSystem, Container, StyleElements
from buildzr.themes import AWS

with Workspace('Custom + Theme') as w:
    with SoftwareSystem('System') as sys:
        critical_api = Container('Critical API')
        normal_api = Container('Normal API')

    # Apply AWS icon with custom background color
    StyleElements(
        on=[critical_api],
        **AWS.LAMBDA,
        background='#ff0000',  # Override with red background
    )

    # Just the AWS icon with default colors
    StyleElements(on=[normal_api], **AWS.LAMBDA)
```

## What's in a ThemeElement?

Each theme constant (like `AWS.EC2`) is a `ThemeElement` that contains:

| Property | Description |
|----------|-------------|
| `tag` | The Structurizr tag (e.g., `"Amazon Web Services - EC2"`) |
| `stroke` | Border color from the theme |
| `color` | Text/font color from the theme |
| `icon_url` | URL to the icon on Structurizr's CDN |

When unpacked with `**`, it provides `tag`, `stroke`, `color`, and `icon` to `StyleElements`.

## Regenerating Themes

Themes are auto-generated from Structurizr's official theme JSON files. To regenerate with the latest icons:

```bash
cd buildzr/themes
python generate.py
```

This fetches theme definitions from URLs in `themes.txt` and generates Python modules in `generated/`.

## See Also

- [Styles](./styles.md)
- [Views](./views.md)