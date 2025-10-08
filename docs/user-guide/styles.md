# Styles

Because nobody wants to look at a diagram that screams "I just accepted all the defaults." Let's make your architecture actually pleasant to look at.

## Overview

Style your diagrams using two main classes:

- **`StyleElements`**: Control how elements look (colors, shapes, borders, etc.)
- **`StyleRelationships`**: Control how relationships look (line colors, thickness, dashes, etc.)

Both classes support flexible targeting: by tag, direct reference, type, group, or custom predicate.

!!! tip "More Powerful Styling"
    `buildzr` extends Structurizr DSL's styling capabilities! While Structurizr DSL only supports styling tags, `buildzr` allows you to target elements by direct reference, types, groups, or custom predicates.

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

Tags are labels you stick on elements to categorize them. Like in Structurizr DSL, their primary use is for styling elements and relationships.

### Adding Tags to Elements

```python
# norun
# Multiple tags
database = SoftwareSystem('Database', tags={'database', 'critical', 'pci'})
```

### Default Tags

Elements automatically receive tags based on their type:

|Element/Relationship|Tags|
|---|---|
|`Person`|`{'Element', 'Person'}`|
|`SoftwareSystem`|`{'Element', 'Software System'}`|
|`Container`|`{'Element', 'Container'}`|
|`Component`|`{'Element', 'Component'}`|
|`DeploymentNode`|`{'Element', 'Deployment Node'}`|
|`InfrastructureNode`|`{'Element', 'Infrastructure Node'}`|
|`SoftwareSystemInstance`|`{'Element', 'Software System Instance'}`|
|`ContainerInstance`|`{'Element', 'Container Instance'}`|
|Relationship|`{'Relationship'}`|

So, you can use the `Container` tag to style all containers to a specific style,
for example.

## Element Styles

!!! info "It's Tags All the Way Down"
    No matter which styling method you use below, `buildzr` secretly uses tags under the hood. It's tags all the way down. For methods that doesn't require explicit tag input, `buildzr` generates them for you automatically. You're welcome.

### Method 1: Style by Tag

As in Structurizr DSL, you can style elements using tags:

```python
from buildzr.dsl import Workspace, SoftwareSystem, StyleElements

with Workspace('w') as w:

    system_a = SoftwareSystem('System A', tags={'critical'})
    system_b = SoftwareSystem('System B', tags={'spot-instance'})

    # This style will be applied to `system_a`, but not `system_b`.
    StyleElements(
        on=['critical'],
        background='#ff0000',
        color='#ffffff'
    )
```

### Method 2: Style by Element Reference

Sometimes you just need to point at something and say "make THAT one red." Direct references let you do exactly that:

```python
from buildzr.dsl import Workspace, Person, SoftwareSystem, StyleElements

with Workspace('w') as w:
    user = Person('User')
    admin = Person('Admin')
    system = SoftwareSystem('System')

    # Style only specific elements
    StyleElements(
        on=[user],  # Direct element references
        shape='Person',
        background='#1168bd'
    )

    # Admin and system uses default styling
```

### Method 3: Style by Type

Style all elements of a specific type:

```python
from buildzr.dsl import Workspace, Person, SoftwareSystem, Container, Component, StyleElements

with Workspace('w') as w:

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

Style all elements within a group. This works with nested groups too --- just reference the group you want to style:

```python
from buildzr.dsl import Workspace, Group, SoftwareSystem, StyleElements

with Workspace('w') as w:
    with Group("MyCompany") as company:
        with Group("Department A") as dept_a:
            sys1 = SoftwareSystem('System 1')
            sys2 = SoftwareSystem('System 2')

        with Group("Department B") as dept_b:
            sys3 = SoftwareSystem('System 3')
            sys4 = SoftwareSystem('System 4')

    with Group("External") as external:
        sys5 = SoftwareSystem('System 5')

    # Style Department A with blue
    StyleElements(
        on=[dept_a],
        background='#1168bd',
        color='#ffffff'
    )

    # Style Department B with green
    StyleElements(
        on=[dept_b],
        background='#2d9f4e',
        color='#ffffff'
    )

    # Style all external systems with gray
    StyleElements(
        on=[external],
        background='#999999',
        color='#ffffff'
    )
```

### Method 5: Style by Predicate

For when tags and types aren't enough --- write custom logic to decide what gets styled:

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
            lambda w, e: e.name.startswith('API')
        ],
        shape='Hexagon',
        background='#00ff00'
    )
```

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

### Method 5: Style by Predicate

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

Here's your style palette --- all the visual knobs you can tweak to make your diagrams sing (or at least not look like they were designed in 1997).

### Element Style Properties

```python
# norun
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

Your shape-shifting toolkit (unfortunately, no actual shape-shifting included):

- `Box` (default --- when in doubt, use a box)
- `RoundedBox` (for the friendlier box)
- `Circle`
- `Ellipse`
- `Hexagon`
- `Cylinder` (databases love this one)
- `Component`
- `Person` (stick figures, not detailed portraits)
- `Robot` (for when your "person" is actually a bot)
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
    SystemContextView,
    ContainerView,
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

    # Relationships
    customer >> "Uses" >> webapp
    webapp >> "Processes payments via" >> payment
    frontend >> "Makes API calls to" >> api
    api >> "Reads from and writes to" >> db

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

    # Views
    SystemContextView(
        software_system_selector=webapp,
        key='SystemContext',
        description='System context view showing the Web App and its users'
    )

    ContainerView(
        software_system_selector=webapp,
        key='Containers',
        description='Container view showing the internal structure of the Web App'
    )
```

### Example 2: Predicate Styling

```python
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Component,
    StyleElements,
    StyleRelationships,
    SystemContextView,
    ContainerView,
    ComponentView,
)

with Workspace('predicate-styling') as w:
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
    order_repo >> "Reads from and writes to" >> database
    payment_repo >> "Reads from and writes to" >> database

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

    # Views
    SystemContextView(
        software_system_selector=ecommerce,
        key='SystemContext',
        description='System context view of the E-Commerce platform'
    )

    ContainerView(
        software_system_selector=ecommerce,
        key='Containers',
        description='Container view showing the services and database'
    )

    ComponentView(
        container_selector=order_svc,
        key='OrderComponents',
        description='Component view of the Order Service'
    )

    ComponentView(
        container_selector=payment_svc,
        key='PaymentComponents',
        description='Component view of the Payment Service'
    )
```

## Next Steps

- [Views](./views.md)
- [API Reference](../api/dsl.md)
