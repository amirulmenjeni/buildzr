# Core Concepts

Think of architecture documentation as cartography for software. Just as maps use different scales --- world atlas, country map, city guide, street view --- software architecture needs multiple levels of detail to tell its story. `buildzr` helps you create these maps using a simple but powerful idea: **zoom in progressively** from the big picture to the fine details.

## The C4 Model: Architecture at Four Scales

`buildzr` is built around the [C4 model](https://c4model.com/), which provides a hierarchical approach to software architecture diagrams. The name "C4" comes from its four levels of abstraction:

**Context** → **Containers** → **Components** → **Code**

Think of it like Google Maps for your system:

- **Context**: The 10,000-foot view. Who uses your system? What other systems does it talk to? This is the boardroom-friendly view that even your CEO can understand.
- **Containers**: Zoom in to see the major technical building blocks --- web apps, databases, mobile apps, microservices. Not Docker containers, but rather anything that runs or stores data.
- **Components**: Zoom further to see how a container is internally structured --- its major modules, packages, or meaningful groupings of functionality.
- **Code**: The street-level view showing actual classes and interfaces. Often just UML diagrams (and honestly, you might not need this one unless you're really into UML).

`buildzr`'s approach to building C4 Models is _Models as Code_, as opposed to just _Diagrams as Code_.

The brilliance of Models as Code is that you get to define your architecture model once, then create different views at different zoom levels for different audiences. You create different views to tell different stories about your software architectures, to work with different audiences, while using the same models.

## The Building Blocks

### Workspace: Your Architecture Universe

A **Workspace** is where everything lives. It's the top-level container for your entire architecture model --- think of it as the canvas on which you'll paint your system's story.

A workspace contains three types of things:

1. **Models**: The elements of your architecture (people, systems, containers, components) and how they relate
2. **Views**: Different perspectives on those models --- what you actually turn into diagrams
3. **Styles**: Visual styling to make your diagrams readable and beautiful

The basic structure looks like this:

```python
# norun
from buildzr.dsl import Workspace, Person, SoftwareSystem, Container

with Workspace('my-architecture') as w:
    # Define your elements and relationships
    # Create views to visualize them
    # Apply styles to make them pretty
```

Check out [Workspace](workspace.md) for more info on `Workspace`.

### Elements: The Vocabulary of Architecture

Architecture diagrams use a small vocabulary with big expressive power. There are just four core element types, each representing a different level of abstraction:

#### Person

The humans (or bots pretending to be humans) who interact with your systems. Could be end users, administrators, or even external API clients represented as actors.

Example:

```python
# norun
user = Person('Customer', description='Buys products from our store')
```

Learn more about defining people and other static models in the [Models guide](models.md#person).

#### Software System

The highest level of abstraction --- a complete system that delivers value to its users. This is usually "your system" or one of the neighboring systems it talks to.

Example:

```python
# norun
checkout = SoftwareSystem('Checkout System', description='Processes orders and payments')
```

See how software systems work in the [Models guide](models.md#software-system).

#### Container

A separately runnable or deployable unit within a software system. Web applications, mobile apps, databases, message queues --- if it runs independently or stores data, it's probably a container. (Yes, the name is confusing if you're thinking Docker containers. Just roll with it.)

Example:

```python
# norun
api = Container('REST API', technology='Python/FastAPI')
```

Dive into containers in the [Models guide](models.md#container).

#### Component

A grouping of related functionality within a container. Controllers, services, repositories --- the major structural building blocks of your code.

Example:
```python
# norun
auth = Component('Authentication Service', description='Handles login and tokens')
```

Explore components further in the [Models guide](models.md#component).

### Relationships: The Conversations

Elements in isolation are just boxes. Relationships give them meaning --- they show who talks to whom, what they're saying, and how they're saying it (REST API? Message queue? Smoke signals?).

The syntax is simple:

```python
# norun
source >> "description" >> destination
```

You can add technical details, tags, properties, and handle complex scenarios like one-to-many relationships. The relationship system is flexible enough for real-world complexity while staying readable.

Example:

```python
# norun
user >> "Places orders through" >> checkout_api
checkout_api >> ("Stores orders in", "JDBC") >> database
```

For a bit more in-depth guide on relationship, see [Relationships](relationships.md).

### Groups: Organizing Chaos

As your architecture grows, you'll want to organize related elements together. Groups let you cluster systems by team ownership, functional area, or any other logical grouping.

Example:

```python
# norun
with Group("Internal Systems"): ...
```

Groups can nest, giving you as much organizational structure as you need. Learn more in the [Workspace guide](workspace.md#groups).

### Views: Choosing What to Show

Here's where the magic happens. You've defined your architecture model --- all the elements and their relationships. Now you create **views** to show different perspectives to different audiences.

Available view types:

- **System Landscape View**: The complete organizational map --- all systems and users
- **System Context View**: One system and its immediate neighborhood
- **Container View**: Zoom into a system to see its containers
- **Component View**: Zoom into a container to see its components
- **Deployment View**: Show where and how things run in production

Each view is a lens focused on a specific part of your model. You define your architecture once, then create multiple views to tell different parts of the story.

Example:

```python
# norun
SystemContextView(software_system_selector=checkout, key='checkout-context')
```

Learn more about views in [Views](views.md).

## The Python Perspective

`buildzr` leverages Python's context managers (`with` statements) to create hierarchical structures that mirror your architecture's natural nesting:

```python
# norun
with Workspace('e-commerce') as w:
    with SoftwareSystem('Shop') as shop:
        api = Container('API')
        with api:
            auth = Component('Auth Service')
```

This isn't just syntactic sugar --- it makes the code structure reflect the architecture structure. When you nest a container inside a system with a `with` block, you're explicitly showing that containment relationship.

You can add tags and properties to categorize and annotate your architecture:

```python
# norun
critical_system = SoftwareSystem(
    'Payment Processing',
    tags=['critical', 'pci-compliant'],
    properties={'Owner': 'Platform Team', 'SLA': '99.99%'}
)
```

Tags are particularly powerful when combined with styling --- apply visual styles to all elements with a specific tag. See the [Styling guide](styles.md) for details.

## See Also

- [Workspace](workspace.md)
- [Models](models.md)
- [Relationships](relationships.md)
- [Views](views.md)
