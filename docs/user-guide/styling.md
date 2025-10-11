# Styling

Customize the appearance of your diagrams using styles and multiple targeting methods.

## Overview

`buildzr` supports styling through:

1. **Tags** - Categorize elements
2. **Element Styles** - Style elements by tag, element reference, type, group, or predicate
3. **Relationship Styles** - Style relationships by tag, reference, group, or predicate

!!! tip "More Powerful Than Structurizr DSL"
    `buildzr` extends Structurizr DSL's styling capabilities! While Structurizr DSL only supports styling by tags, `buildzr` allows you to target elements by direct reference, types, groups, or custom predicates.

## Styling Methods

`buildzr` provides five powerful ways to target elements and relationships for styling:

| Method | Description | Use Case |
|--------|-------------|----------|
| **By Tag** | Style all elements/relationships with a specific tag | Consistent styling across related elements |
| **By Element Reference** | Style specific element instances directly | One-off styling for specific elements |
| **By Type** | Style all elements of a specific type (Person, Container, etc.) | Consistent type-based styling |
| **By Group** | Style all elements within a group | Organize styling by business domain |
| **By Predicate** | Use custom logic to filter elements | Advanced, complex styling rules |

## Tags

Tags are labels attached to elements for categorization and styling.

### Adding Tags to Elements

```python
from buildzr.dsl import SoftwareSystem

# Single tag
system = SoftwareSystem('System', tags={'critical'})

# Multiple tags
database = SoftwareSystem('Database', tags={'database', 'critical', 'pci'})
```

### Default Tags

Elements automatically receive tags based on their type:

- `Person` → `"Element,Person"`
- `SoftwareSystem` → `"Element,Software System"`
- `Container` → `"Element,Container"`
- `Component` → `"Element,Component"`

You can add additional custom tags.

## Element Styles

### Method 1: Style by Tag

Style all elements with a specific tag:

```python
from buildzr.dsl import Workspace, StyleElements

with Workspace('w') as w:
    # ... define your model ...
    system = SoftwareSystem('System', tags={'critical'})

    StyleElements(
        on=['critical'],  # Target elements with 'critical' tag
        background='#ff0000',
        color='#ffffff'
    )
```

### Method 2: Style by Element Reference

Target specific element instances directly:

```python
from buildzr.dsl import Person, SoftwareSystem, StyleElements

with Workspace('w') as w:
    user = Person('User')
    admin = Person('Admin')
    system = SoftwareSystem('System')

    # Style only specific elements
    StyleElements(
        on=[user, system],  # Direct element references
        shape='Box',
        background='#1168bd'
    )

    # Admin uses default styling
```

### Method 3: Style by Type

Style all elements of a specific type:

```python
from buildzr.dsl import Person, SoftwareSystem, Container, Component, StyleElements

with Workspace('w') as w:
    # ... define your model ...

    # Style ALL Person elements
    StyleElements(
        on=[Person],
        shape='Person',
        background='#08427b'
    )

    # Style ALL SoftwareSystem and Container elements
    StyleElements(
        on=[SoftwareSystem, Container],
        shape='RoundedBox',
        background='#438dd5'
    )

    # Style ALL Component elements
    StyleElements(
        on=[Component],
        shape='Circle'
    )
```

### Method 4: Style by Group

Style all elements within a group:

```python
from buildzr.dsl import Group, SoftwareSystem, StyleElements

with Workspace('w') as w:
    with Group("Internal Systems") as internal:
        sys1 = SoftwareSystem('System 1')
        sys2 = SoftwareSystem('System 2')

    with Group("External Systems") as external:
        sys3 = SoftwareSystem('System 3')

    # Style all elements in the "Internal Systems" group
    StyleElements(
        on=[internal],
        background='#1168bd',
        color='#ffffff'
    )

    # Style all elements in the "External Systems" group
    StyleElements(
        on=[external],
        background='#999999',
        color='#ffffff'
    )
```

### Method 5: Style by Predicate (Advanced)

Use custom logic to filter elements:

```python
from buildzr.dsl import Workspace, Person, SoftwareSystem, Container, StyleElements

with Workspace('w') as w:
    user = Person('User')
    with SoftwareSystem('System A') as sys_a:
        api_a = Container('API')
    with SoftwareSystem('System B') as sys_b:
        api_b = Container('API')

    # Style using custom predicate logic
    StyleElements(
        on=[
            lambda w, e: e == w.software_system().system_a or e == w.software_system().system_b
        ],
        shape='WebBrowser',
        background='#ff9900'
    )

    # Style containers whose name starts with 'API'
    StyleElements(
        on=[
            lambda w, e: hasattr(e, 'name') and e.name.startswith('API')
        ],
        shape='Hexagon',
        background='#00ff00'
    )
```

!!! warning "Predicate Scope"
    Predicates must be used within an active workspace context. They cannot be applied after the workspace context has exited.

## Relationship Styles

### Method 1: Style All Relationships

Style all relationships when no target is specified:

```python
from buildzr.dsl import StyleRelationships

with Workspace('w') as w:
    # ... define your model and relationships ...

    # Style ALL relationships
    StyleRelationships(
        color='#707070',
        thickness=2,
        dashed=False
    )
```

### Method 2: Style by Relationship Reference

Target specific relationships directly:

```python
from buildzr.dsl import Person, SoftwareSystem, StyleRelationships

with Workspace('w') as w:
    user = Person('User')
    system_a = SoftwareSystem('System A')
    system_b = SoftwareSystem('System B')

    r1 = user >> "Uses" >> system_a
    r2 = system_a >> "Calls" >> system_b

    # Style specific relationships
    StyleRelationships(
        on=[r1],
        color='#ff0000',
        thickness=4
    )

    StyleRelationships(
        on=[r2],
        color='#0000ff',
        dashed=True
    )
```

### Method 3: Style by Tag

Style relationships with specific tags:

```python
from buildzr.dsl import Person, SoftwareSystem, With, StyleRelationships

with Workspace('w') as w:
    user = Person('User')
    system_a = SoftwareSystem('System A')
    system_b = SoftwareSystem('System B')

    # Tag relationships
    user >> "Uses" >> system_a | With(tags={'sync'})
    system_a >> "Calls" >> system_b | With(tags={'async'})

    # Style by tag
    StyleRelationships(
        on=['sync'],
        color='#ff0000',
        thickness=3,
        dashed=False
    )

    StyleRelationships(
        on=['async'],
        color='#0000ff',
        thickness=2,
        dashed=True
    )
```

### Method 4: Style by Group

Style all relationships within a group:

```python
from buildzr.dsl import Group, Component, StyleRelationships

with Workspace('w') as w:
    with Group("Service Layer") as service_group:
        with Container('API') as api:
            comp1 = Component('Service 1')
            comp2 = Component('Service 2')
            comp1 >> "Uses" >> comp2

    with Group("Data Layer") as data_group:
        with Container('Database') as db:
            comp3 = Component('Repository 1')
            comp4 = Component('Repository 2')
            comp3 >> "Queries" >> comp4

    # Style relationships within groups
    StyleRelationships(
        on=[service_group],
        color='#00ff00',
        thickness=3
    )

    StyleRelationships(
        on=[data_group],
        color='#0000ff',
        thickness=2,
        dashed=True
    )
```

### Method 5: Style by Predicate (Advanced)

Use custom logic to filter relationships:

```python
from buildzr.dsl import Person, SoftwareSystem, Component, StyleRelationships

with Workspace('w') as w:
    user = Person('User')
    with SoftwareSystem('System') as sys:
        with Container('API') as api:
            comp1 = Component('Component 1')
            comp2 = Component('Component 2')

    user >> "Uses" >> sys
    comp1 >> "Calls" >> comp2

    # Style relationships from Person elements
    StyleRelationships(
        on=[
            lambda w, r: r.source.type == Person
        ],
        color='#ff0000',
        thickness=4
    )

    # Style relationships between Components
    StyleRelationships(
        on=[
            lambda w, r: r.source.type == Component and r.destination.type == Component
        ],
        color='#0000ff',
        dashed=True
    )
```

## Available Style Properties

### Element Style Properties

```python
StyleElements(
    on=[...],
    width=450,              # Width in pixels
    height=300,             # Height in pixels
    background='#1168bd',   # Background color
    color='#ffffff',        # Text color
    shape='RoundedBox',     # Shape
    icon='https://...',     # Icon URL
    fontSize=24,            # Font size
    border='Solid',         # Border style
    stroke='#000000',       # Border color
    opacity=85,             # Opacity (0-100)
    metadata=True,          # Show metadata
    description=True        # Show description
)
```

### Available Shapes

- `Box` (default)
- `RoundedBox`
- `Circle`
- `Ellipse`
- `Hexagon`
- `Cylinder`
- `Component`
- `Person`
- `Robot`
- `Folder`
- `WebBrowser`
- `MobileDevicePortrait`
- `MobileDeviceLandscape`
- `Pipe`

### Relationship Style Properties

```python
StyleRelationships(
    on=[...],
    thickness=2,           # Line thickness
    color='#707070',       # Line color
    dashed=True,           # Dashed line
    routing='Direct',      # Routing algorithm
    fontSize=24,           # Label font size
    width=200,             # Width
    position=50,           # Label position (0-100)
    opacity=100            # Opacity (0-100)
)
```

## Complete Examples

### Example 1: Combining Multiple Methods

```python
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Group,
    StyleElements,
)

with Workspace('combined-styling') as w:
    customer = Person('Customer')

    with Group("Internal") as internal:
        webapp = SoftwareSystem('Web App', tags={'web'})
        with webapp:
            frontend = Container('Frontend', technology='React')
            api = Container('API', technology='FastAPI', tags={'critical'})
            db = Container('Database', technology='PostgreSQL')

    with Group("External") as external:
        payment = SoftwareSystem('Payment Gateway', tags={'external'})

    # Style 1: All Person elements by type
    StyleElements(
        on=[Person],
        shape='Person',
        background='#08427b',
        color='#ffffff'
    )

    # Style 2: Specific element by reference
    StyleElements(
        on=[api],
        background='#ff0000',  # Highlight critical API
        color='#ffffff'
    )

    # Style 3: By tag
    StyleElements(
        on=['external'],
        background='#999999',
        color='#ffffff'
    )

    # Style 4: By group
    StyleElements(
        on=[internal],
        border='solid',
        stroke='#0000ff'
    )

    # Style 5: Database by type
    StyleElements(
        on=[Container],
        shape='Cylinder'
    )
```

### Example 2: Advanced Predicate Styling

```python
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Component,
    StyleElements,
    StyleRelationships,
)

with Workspace('advanced-styling') as w:
    admin = Person('Admin')
    user = Person('User')

    with SoftwareSystem('E-Commerce') as ecommerce:
        with Container('Order Service') as order_svc:
            order_ctrl = Component('Order Controller')
            order_repo = Component('Order Repository')

        with Container('Payment Service') as payment_svc:
            payment_ctrl = Component('Payment Controller')
            payment_repo = Component('Payment Repository')

        database = Container('Database')

    # Relationships
    r1 = admin >> "Manages" >> ecommerce
    r2 = user >> "Uses" >> ecommerce
    r3 = order_ctrl >> "Uses" >> order_repo
    r4 = payment_ctrl >> "Uses" >> payment_repo

    # Style elements whose names end with 'Controller'
    StyleElements(
        on=[
            lambda w, e: e.name.endswith('Controller') if hasattr(e, 'name') else False
        ],
        shape='Hexagon',
        background='#00ff00'
    )

    # Style elements whose names end with 'Repository'
    StyleElements(
        on=[
            lambda w, e: e.name.endswith('Repository') if hasattr(e, 'name') else False
        ],
        shape='Cylinder',
        background='#0000ff'
    )

    # Style relationships from admins differently
    StyleRelationships(
        on=[
            lambda w, r: r.source == admin
        ],
        color='#ff0000',
        thickness=4,
        dashed=False
    )

    # Style internal component relationships
    StyleRelationships(
        on=[
            lambda w, r: r.source.type == Component and r.destination.type == Component
        ],
        color='#00ff00',
        dashed=True
    )
```

## Best Practices

### 1. Use Type-Based Styling for Consistency

```python
# Style all elements of the same type consistently
StyleElements(on=[Person], shape='Person', background='#08427b')
StyleElements(on=[Container], background='#438dd5')
StyleElements(on=[Component], shape='Circle')
```

### 2. Use Tags for Cross-Cutting Concerns

```python
# Tag for cross-cutting styling
critical_api = Container('API', tags={'critical', 'monitored'})
critical_db = Container('DB', tags={'critical', 'monitored'})

StyleElements(on=['critical'], background='#ff0000')
StyleElements(on=['monitored'], border='solid', stroke='#00ff00')
```

### 3. Use Direct References for One-Off Styling

```python
# Highlight specific important element
main_api = Container('Main API')
StyleElements(on=[main_api], background='#ffff00')  # Yellow highlight
```

### 4. Use Groups for Domain Organization

```python
with Group("Payment Domain") as payments:
    payment_sys = SoftwareSystem('Payments')

with Group("Order Domain") as orders:
    order_sys = SoftwareSystem('Orders')

StyleElements(on=[payments], background='#ff9900')
StyleElements(on=[orders], background='#0099ff')
```

### 5. Use Predicates for Complex Logic

```python
# Style elements based on naming conventions
StyleElements(
    on=[lambda w, e: 'Service' in e.name if hasattr(e, 'name') else False],
    shape='Hexagon'
)
```

## Next Steps

- [Examples](../examples/system-context.md)
- [API Reference](../api/dsl.md)
