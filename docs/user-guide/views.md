# Views

Views are how you actually *look* at your architecture. Think of them as different camera angles on the same movie set --- your models are the actors, and views are how you frame the shot. A landscape view is the sweeping helicopter shot showing everything. A component view is the intimate close-up on a single character's face. Without views, you've got a bunch of models sitting in a database that nobody can see. With views, you've got architecture diagrams that actually tell a story.

## View Types

`buildzr` supports all major C4 model view types:

- **System Landscape View**: Shows all systems and people across your entire organization
- **System Context View**: Focuses on a single system and what it depends on or talks to
- **Container View**: Zooms into a system to show its applications, databases, and services
- **Component View**: Drills into a container to reveal its internal code structure
- **Deployment View**: Maps containers to actual infrastructure (servers, clusters, cloud resources)
- **Dynamic View**: Shows ordered sequences of interactions for a specific use case or feature
- **Custom View**: Displays custom elements that sit outside the C4 model

## System Landscape View

The `SystemLandscapeView` is your 30,000-foot view --- it shows every software system and every person in your organization's ecosystem. This is the view you show to executives who want to see "everything" without actually wanting to understand anything. It answers the question: "What systems do we even have?"

```python
# norun
SystemLandscapeView(
    key='landscape',
    description='Enterprise System Landscape',
    auto_layout='tb'
)
```

### Example

```python
from buildzr.dsl import Workspace, Person, SoftwareSystem, SystemLandscapeView, Group

with Workspace('w') as w:
    with Group("Users"):
        customer = Person('Customer')

    with Group("Internal"):
        web = SoftwareSystem('Web App')
        api = SoftwareSystem('API')

    with Group("External"):
        payment = SoftwareSystem('Payment Gateway')

    customer >> "Uses" >> web
    web >> "Calls" >> api
    api >> "Processes payments via" >> payment

    SystemLandscapeView(
        key='landscape',
        description='System Landscape',
        auto_layout='lr'
    )

    w.save(path='workspace.json')
```

## System Context View

Zoom in one level, and you've got the `SystemContextView`. This shows a single software system surrounded by everything it talks to --- users, external systems, databases, or external APIs (including free or third-party services).

```python
# norun
SystemContextView(
    software_system_selector=my_system,
    key='context',
    description='System Context for My System',
    auto_layout='tb'
)
```

### Example

```python
from buildzr.dsl import Workspace, Person, SoftwareSystem, SystemContextView

with Workspace('w') as w:
    user = Person('User')
    system = SoftwareSystem('My System')
    email = SoftwareSystem('Email System', tags=['external'])
    database = SoftwareSystem('Legacy Database', tags=['external'])

    user >> "Uses" >> system
    system >> "Sends emails via" >> email
    system >> "Reads data from" >> database

    SystemContextView(
        software_system_selector=system,
        key='system-context',
        description='My System Context',
        auto_layout='tb'
    )

    w.save(path='workspace.json')
```

## Container View

Open up that system and peer inside! The `ContainerView` shows you all the applications, databases, microservices, and other runtime components that make up a software system. This is where you start seeing the actual architecture --- web apps talking to APIs, APIs talking to databases, message queues doing their queuey thing.

```python
# norun
ContainerView(
    software_system_selector=my_system,
    key='containers',
    description='Container View',
    auto_layout='tb'
)
```

### Example

```python
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    ContainerView,
)

with Workspace('w') as w:
    user = Person('User')
    system = SoftwareSystem('Web Application')

    with system:
        web = Container('Web App', technology='React')
        api = Container('API', technology='FastAPI')
        db = Container('Database', technology='PostgreSQL')

    user >> "Uses" >> web
    web >> ("Calls", "REST/HTTPS") >> api
    api >> ("Reads/Writes", "SQL") >> db

    ContainerView(
        software_system_selector=system,
        key='containers',
        description='Web Application Containers',
        auto_layout='tb'
    )

    w.save(path='workspace.json')
```

## Component View

The `ComponentView` shows the most granular level of detail in the C4 model. It reveals the internal structure of a single container --- the controllers, services, repositories, and other architectural layers that live inside. This is the view developers care about most, because it shows where the code lives and how it's organized.

```python
# norun
ComponentView(
    container_selector=my_container,
    key='components',
    description='Component View',
    auto_layout='tb'
)
```

### Example

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Container,
    Component,
    ComponentView,
)

with Workspace('w') as w:
    system = SoftwareSystem('System')

    with system:
        api = Container('API')

        with api:
            controller = Component('REST Controller')
            service = Component('Business Service')
            repository = Component('Data Repository')

        database = Container('Database')

    controller >> "Uses" >> service
    service >> "Uses" >> repository
    repository >> ("Queries", "SQL") >> database

    ComponentView(
        container_selector=api,
        key='api-components',
        description='API Components',
        auto_layout='tb'
    )

    w.save(path='workspace.json')
```

## Deployment View

Time to get physical! The `DeploymentView` shows where your containers actually *run* --- which cloud provider, which region, which servers, which Docker containers on which Kubernetes clusters in which data centers. For this reason, `DeploymentNode`s can be nested indefinitely. This is the bridge between your beautiful logical architecture and the messy reality of infrastructure. DevOps engineers live here.

```python
# norun
DeploymentView(
    software_system_selector=my_system,
    environment='Production',
    key='deployment',
    description='Production Deployment',
    auto_layout='tb'
)
```

### Example

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Container,
    DeploymentEnvironment,
    DeploymentNode,
    ContainerInstance,
    DeploymentView,
)

with Workspace('w') as w:
    system = SoftwareSystem('Web App')

    with system:
        api = Container('API', technology='Python')
        db = Container('Database', technology='PostgreSQL')

    with DeploymentEnvironment('Production') as prod:
        with DeploymentNode('AWS', technology='Cloud'):
            with DeploymentNode('ECS Cluster', technology='Docker'):
                api_instance = ContainerInstance(api)

            with DeploymentNode('RDS', technology='Managed Service'):
                db_instance = ContainerInstance(db)

    DeploymentView(
        software_system_selector=system,
        environment=prod,
        key='prod-deployment',
        description='Production Deployment',
        auto_layout='tb'
    )

    w.save(path='workspace.json')
```

## Dynamic View

Static diagrams show structure, but sometimes you need to show *behavior* --- the sequence of interactions that happen at runtime. The `DynamicView` is your flow diagram. It shows ordered interactions between elements for a specific use case, story, or feature. Instead of "these things are connected," it shows "first this happens, then that happens, then this other thing."

```python
# norun
DynamicView(
    key='checkout-flow',
    description='Customer checkout process',
    scope=ecommerce_system,  # Optional: None, SoftwareSystem, or Container
    steps=[r1, r2, r3],  # Order determined by list position
    auto_layout='lr'
)
```

### How It Works

Dynamic views reference *existing* relationships in your model, but display them in a specific order with optional description overrides. You define the static relationships first, then create a dynamic view that shows them in sequence:

```python
# norun
# First, define the static relationships (what CAN happen)
r_browse = customer >> "Browses" >> webapp
r_query = webapp >> "Queries" >> database

# Then, show them in a specific order (what DOES happen in this scenario)
DynamicView(
    key='browse-products',
    scope=system,
    steps=[
        customer >> "Requests product list from" >> webapp,  # Step 1
        webapp >> "Fetches products using" >> database,      # Step 2
    ],
)
```

Notice that the descriptions in the dynamic view can be different from the static relationships --- they describe what happens in *this specific scenario*, not the general relationship.

!!! note "Technology as a Selector, Not an Override"
    Unlike descriptions, **technology cannot be overridden** in dynamic views. When you specify a technology in a dynamic view relationship, it acts as a *selector* to match a model relationship with that exact technology. This is useful when you have multiple relationships between the same elements with different technologies:

    ```python
    # norun
    # Model has two relationships with different technologies
    webapp >> ("Queries", "SQL") >> database
    webapp >> ("Syncs", "REST API") >> database

    # Dynamic view selects the REST relationship by technology
    DynamicView(
        key='sync-flow',
        scope=system,
        steps=[
            webapp >> ("Synchronizes data via", "REST API") >> database,
        ],
    )
    ```

    If no model relationship matches the specified technology, a `ValueError` is raised.

### Example

```python
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    ContainerView,
    DynamicView,
)

with Workspace('Online Book Store') as w:
    customer = Person('Customer')

    with SoftwareSystem('Online Book Store') as bookstore:
        webapp = Container('Web Application')
        database = Container('Database')

    # Define static relationships (the "can do" relationships)
    customer >> "Browses and makes purchases using" >> webapp
    webapp >> "Reads from and writes to" >> database

    # Static container view showing the structure
    ContainerView(
        software_system_selector=bookstore,
        key='containers',
        description='Container view',
        auto_layout='lr',
    )

    # Dynamic view 1: Show the "request past orders" flow
    DynamicView(
        key='request-past-orders',
        description='Request past orders feature',
        scope=bookstore,
        steps=[
            customer >> "Requests past orders from" >> webapp,
            webapp >> "Queries order history using" >> database,
        ],
        auto_layout='lr',
    )

    # Dynamic view 2: Show the "browse top books" flow
    DynamicView(
        key='browse-top-books',
        description='Browse top 20 books feature',
        scope=bookstore,
        steps=[
            customer >> "Requests top 20 books from" >> webapp,
            webapp >> "Queries bestsellers using" >> database,
        ],
        auto_layout='lr',
    )

    w.save(path='workspace.json')
```

### Scope Options

The `scope` parameter determines what level of detail your dynamic view shows:

- **`None`** (default): Landscape level --- shows interactions between software systems and people
- **`SoftwareSystem`**: Container level --- shows interactions between containers within a system
- **`Container`**: Component level --- shows interactions between components within a container

```python
# norun
# Landscape level - systems talking to systems
DynamicView(
    key='system-integration',
    steps=[system_a >> "Sends data to" >> system_b],
)

# Container level - containers within a system
DynamicView(
    key='api-flow',
    scope=my_system,
    steps=[webapp >> "Calls" >> api, api >> "Queries" >> db],
)

# Component level - components within a container
DynamicView(
    key='request-handling',
    scope=api_container,
    steps=[controller >> "Delegates to" >> service],
)
```

## Custom View

The `CustomView` provides a flexible way to create diagrams that mix custom elements (`Element`) with standard C4 elements. It's particularly useful when you're modeling hardware components, business processes, or anything that doesn't fit neatly into the Person/SoftwareSystem/Container/Component hierarchy --- but you still want to show how they relate to your software architecture.

!!! tip "Custom Elements in Any View"
    Custom elements (`Element`) can be displayed in **any** view type, not just `CustomView`. You can include them in `SystemLandscapeView`, `SystemContextView`, and other views using the `include_elements` parameter. `CustomView` simply provides another canvas where you have full control over what's displayed.

!!! note "Schema Note"
    The official Structurizr JSON schema at [https://github.com/structurizr/json](https://github.com/structurizr/json) does **not** include `customElements` or `customViews` fields. However, the Structurizr CLI and DSL fully support these features. The `buildzr` implementation is based on testing with [`structurizr.sh export`](https://docs.structurizr.com/cli/export) to discover the actual JSON structure.

```python
# norun
CustomView(
    key='hardware-architecture',
    description='Hardware component interactions',
    title='Hardware Architecture',  # Optional
    auto_layout='lr'
)
```

### Example

```python
from buildzr.dsl import Workspace, Element, CustomView

with Workspace('IoT System') as w:
    # Define custom elements for hardware/non-software components
    gateway = Element("IoT Gateway", metadata="Hardware", description="Central gateway device")
    sensor_a = Element("Temperature Sensor", metadata="Sensor", description="Measures ambient temperature")
    sensor_b = Element("Humidity Sensor", metadata="Sensor", description="Measures humidity levels")
    cloud = Element("Cloud Platform", metadata="Service", description="Data processing backend")

    # Define relationships
    sensor_a >> "sends readings to" >> gateway
    sensor_b >> "sends readings to" >> gateway
    gateway >> ("uploads data to", "MQTT") >> cloud

    # Create a custom view to display these elements
    CustomView(
        key='iot-hardware',
        description='IoT Hardware Architecture',
        title='IoT Device Layout',
        auto_layout='tb'
    )

    w.save(path='workspace.json')
```

### CustomView Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | `str` | Unique identifier for this view (required) |
| `description` | `str` | Description of what this view shows |
| `title` | `str` | Display title for the view (optional) |
| `auto_layout` | `str` | Layout direction: `'tb'`, `'bt'`, `'lr'`, or `'rl'` |
| `include_elements` | `list` | Additional elements to include (must be `Element` type) |
| `exclude_elements` | `list` | Elements to exclude from the view |
| `include_relationships` | `list` | Additional relationships to include |
| `exclude_relationships` | `list` | Relationships to exclude |
| `properties` | `dict` | Arbitrary key-value properties |

## Auto Layout

Views without layout are just random boxes scattered across a canvas like a toddler's finger painting. The `auto_layout` parameter tells `buildzr` how to arrange elements so humans can actually understand them. You've got four directions to choose from:

- `'tb'` - Top to bottom (default) - Classic hierarchy style
- `'bt'` - Bottom to top - For when you want to be contrarian
- `'lr'` - Left to right - Great for process flows and timelines
- `'rl'` - Right to left - For RTL languages or just mixing things up

```python
# norun
SystemContextView(
    software_system_selector=system,
    key='context-horizontal',
    auto_layout='lr'  # Left to right
)
```

!!! tip "Choosing the Right Direction"
    Use `'tb'` for hierarchical relationships (user → app → database). Use `'lr'` for sequential processes (request → auth → process → response). Use `'bt'` if you're feeling rebellious. Use `'rl'` if... well, probably just stick with the first two. Or if you speak Arabic.

## Including/Excluding Elements

Sometimes your view has too much clutter. Maybe there's an internal admin system that's technically part of the architecture but would just confuse the audience. Or maybe you only want to highlight specific critical components. That's where including and excluding elements comes in --- it's like Photoshopping your ex out of vacation photos, but for architecture diagrams.

### Exclude Specific Elements

Remove the stuff you don't want anyone to see (for now):

```python
# norun
SystemContextView(
    software_system_selector=system,
    key='context',
    exclude_elements=[internal_admin, test_system]  # Pretend these don't exist
)
```

### Include Specific Elements

Or flip it around --- to include additional containers that otherwise have not have been included in the view:

```python
# norun
# critical_container is not part of system, but we want to include it in the
# view too!
ContainerView(
    software_system_selector=system,
    key='containers',
    include_elements=[critical_container]
)
```

## View Best Practices

### Create Multiple Views

You need more than one view. Different people need different levels of detail. Your CEO doesn't want to see your repository pattern implementation, and your backend developer doesn't care about the landscape view. Create views for your audience:

```python
# High-level for executives who ask "what does it do?"
SystemLandscapeView(key='landscape')

# Mid-level for architects who ask "how does it work?"
SystemContextView(software_system_selector=system, key='context')

# Detailed for developers who ask "where's the bug?"
ContainerView(software_system_selector=system, key='containers')
ComponentView(container_selector=api, key='components')
```

### Use Descriptive Keys and Descriptions

Future you (or worse, someone else) will thank you for clear, descriptive names. Don't be cryptic:

```python
# Good - clear and informative
SystemContextView(
    software_system_selector=payment_system,
    key='payment-system-context',
    description='Payment System and External Dependencies'
)

# Bad - might as well be lorem ipsum
SystemContextView(
    software_system_selector=payment_system,
    key='view1',
    description='System View'
)
```

### Choose Appropriate Layouts

Match your layout direction to your diagram's natural flow:

```python
# norun
# Hierarchical flow - use top-to-bottom
ContainerView(
    software_system_selector=system,
    key='containers',
    auto_layout='tb'  # User at top, database at bottom
)

# Process flow - use left-to-right
SystemContextView(
    software_system_selector=system,
    key='context',
    auto_layout='lr'  # Request flows left to right, like reading
)
```

## Complete Example

Let's bring it all together with a full example that creates multiple views of an e-commerce system. Notice how we define the models once, then create different views for different audiences.

!!! note "Enable `implied_relationships`"
    The example below uses implied relationships. Otherwise, the `SystemLandscapeView` won't show any relationships between the `SoftwareSystem`s and the `Person`!

```python
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Component,
    Group,
    SystemLandscapeView,
    SystemContextView,
    ContainerView,
    ComponentView,
)

with Workspace('multi-view-example', implied_relationships=True) as w:
    # Model
    with Group("Users"):
        customer = Person('Customer')

    with Group("E-Commerce"):
        ecommerce = SoftwareSystem('E-Commerce Platform')

        with ecommerce:
            web = Container('Web App', technology='React')
            api = Container('API', technology='Node.js')

            with api:
                order_ctrl = Component('Order Controller')
                order_svc = Component('Order Service')
                order_repo = Component('Order Repository')

            db = Container('Database', technology='MongoDB')

    with Group("External"):
        payment = SoftwareSystem('Payment Gateway')

    # Relationships
    customer >> "Browses and purchases" >> web
    web >> ("Calls", "REST") >> api
    api >> ("Stores", "MongoDB") >> db
    order_ctrl >> "Uses" >> order_svc
    order_svc >> "Uses" >> order_repo
    order_repo >> "Queries" >> db
    api >> ("Processes payments", "REST") >> payment

    # Multiple views for different audiences
    SystemLandscapeView(
        key='landscape',
        description='All Systems'
    )

    SystemContextView(
        software_system_selector=ecommerce,
        key='ecommerce-context',
        description='E-Commerce System Context',
        auto_layout='tb'
    )

    ContainerView(
        software_system_selector=ecommerce,
        key='ecommerce-containers',
        description='E-Commerce Containers',
        auto_layout='tb'
    )

    ComponentView(
        container_selector=api,
        key='api-components',
        description='API Components',
        auto_layout='lr'
    )

    w.save(path='workspace.json')
```

## Next Steps

- [Styles](styles.md)
- [API Reference](../api/dsl.md)
