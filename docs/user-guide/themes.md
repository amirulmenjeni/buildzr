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

By default, theme icons reference URLs on Structurizr's CDN. For offline or self-contained workspaces, use `as_inline()` to embed icons as base64:

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
    `as_inline()` fetches icons from the CDN when your script runs. The resulting workspace JSON will be self-contained, but you need network access during the build.

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

buildzr does not download themes. A theme URL is matched by the name of the folder that holds its `theme.json`, such as `kubernetes-v0.3` or `amazon-web-services-2023.01.31`, against the [themes buildzr ships](#available-themes), whatever the host: `https://static.structurizr.com/themes/kubernetes-v0.3/theme.json` and the GitHub address of `KUBERNETES_V0_3.THEME_URL` are the same theme. The styles of any other theme are not applied, and the build says so (see [Warnings](#warnings)). Add the styles you need with `StyleElements` and `StyleRelationships` instead.

### How Styles Combine

For each element, the viewer starts from the C4 default of its type (a person, a software system, a container...). It then applies the styles of the element's tags, and for each tag:

1. the styles of the themes, in the order you added the themes: a later theme wins over an earlier one;
2. then the workspace's own styles, in the order you wrote them: your style wins over every theme.

A style changes only the properties it sets: your style with only a `background` keeps the theme's stroke, text colour and icon. The tags apply in this order: `Element`, then the type tag (`Person`, `Container`...), then the element's other tags in the order the style list (the themes' styles first, then yours) first names them. Relationships work the same way, starting from the `Relationship` tag.

A theme that sets a text `color` sets it as you would: buildzr does not change it for contrast. Without a `color`, the text is black or white, whichever reads better on the fill.

The layout makes the boxes; the `width` and `height` of a style are not used.

### Icons

The viewer draws an icon above the name of a box, and before the name of a person, of a box with children (a frame) and of a boundary. The layout leaves room for it.

The viewer shows only the images that the workspace carries, as data URIs. The build copies them into the built workspace, so the icons look the same from `buildzr serve`, from any static host and offline. Icons from a URL are not shown: the viewer loads nothing from other sites. The icons of `buildzr.themes` are URLs; use `as_inline()` to embed one (see [Offline / Self-Contained Workspaces](#offline-self-contained-workspaces)):

```python
# no-run: as_inline() fetches the icon from the network
StyleElements(on=[api], **KUBERNETES_V0_3.POD.as_inline())
```

An icon is a PNG, JPEG, GIF, WebP or SVG image of at most 512 KB.

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
buildzr: warning: shop.py: icon https://raw.githubusercontent.com/structurizr/themes/67da2b503abc708f941e5aa2ea35dd553f742c3a/kubernetes-v0.3/pod-256.png: not shown, the image is on another site and the viewer loads nothing from other sites. Embed it instead: .as_inline() on a buildzr.themes element, or a data URI
```

You get one for a theme buildzr does not ship, an image on another site, an image that is not a data URI of a supported type, is damaged or is too large, a font name that is not a font family, and a font URL. When the viewer cannot read the branding file or an image, it draws the diagram without them and says why in the browser console.

### When the Viewer Draws Them Again

Themes and branding are part of the model file, so a change to them changes the file's [fingerprint](../cli.md#when-a-built-workspace-is-out-of-date) and `buildzr build` and `buildzr serve` build the workspace again. The themes that buildzr ships are part of its version. An image that the model file reads from another file is not part of the fingerprint, like code it imports: after you change the image, build with `--rebuild`.

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