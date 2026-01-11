# Themes

Add cloud provider icons to your architecture diagrams with zero friction. `buildzr` provides auto-generated theme constants for AWS, Azure, Google Cloud, Kubernetes, and Oracle Cloud Infrastructure.

## Overview

Structurizr themes work via tag-based styling --- elements need specific tags like `"Amazon Web Services - EC2"` to receive their icons. This is powerful but requires you to know the exact tag strings.

`buildzr` solves this with IDE-discoverable theme constants:

```python
from buildzr.dsl import Workspace, Container, StyleElements
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
for name, element in AWS.all_elements():
    print(f"{name}: {element.tag}")
```

## Theme Versions

Cloud providers update their icon sets over time. `buildzr` includes multiple versions:

### AWS Versions

```python
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
from buildzr.themes import ORACLE_CLOUD, ORACLE_CLOUD_2023_04_01, ORACLE_CLOUD_2021_04_30, ORACLE_CLOUD_2020_04_30

# ORACLE_CLOUD is an alias for the latest version (ORACLE_CLOUD_2023_04_01)
StyleElements(on=[db], **ORACLE_CLOUD.AUTONOMOUS_DATABASE)
StyleElements(on=[api], **ORACLE_CLOUD.API_GATEWAY)
```

## Offline / Self-Contained Workspaces

By default, theme icons reference URLs on Structurizr's CDN. For offline or self-contained workspaces, use `as_inline()` to embed icons as base64:

```python
from buildzr.dsl import Workspace, Container, StyleElements
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
    DeploymentEnvironment, DeploymentNode, InfrastructureNode,
    DeploymentView, StyleElements
)
from buildzr.themes import AWS, AWS_2020_04_30

with Workspace('AWS Deployment') as w:
    with SoftwareSystem('My App') as app:
        web = Container('Web App', technology='Spring Boot')
        db = Container('Database', technology='MySQL')

    with DeploymentEnvironment('Production'):
        with DeploymentNode('Amazon Web Services') as aws:
            with DeploymentNode('us-east-1') as region:
                with DeploymentNode('EC2') as ec2:
                    ec2.add(web)
                with DeploymentNode('RDS') as rds:
                    rds.add(db)
                elb = InfrastructureNode('Load Balancer', technology='ELB')

    # Style deployment nodes with AWS icons
    StyleElements(on=[aws], **AWS_2020_04_30.CLOUD)
    StyleElements(on=[region], **AWS_2020_04_30.REGION)
    StyleElements(on=[ec2], **AWS.EC2)
    StyleElements(on=[rds], **AWS.RDS)
    StyleElements(on=[elb], **AWS.ELASTIC_LOAD_BALANCING)

    DeploymentView(app, 'Production', key='deployment', description='Production deployment')
```

## PlantUML Export with Icons

When exporting to PlantUML, icons are automatically included as sprites:

```python
# Export to PlantUML with icons
puml_dict = w.to_plantuml()

# Export to SVG (icons embedded as base64)
svg_dict = w.to_svg()

# Save to files
w.save(format='plantuml', path='output/')
w.save(format='svg', path='output/')
```

The generated PlantUML will include `AddElementTag()` directives with sprite definitions, and the legend will display service names with their icons.

## Combining with Custom Styles

Theme styles can be combined with custom styling:

```python
from buildzr.dsl import Workspace, Container, StyleElements
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