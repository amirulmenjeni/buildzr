# Spike: Run Code draws the diagram

!!! warning "Temporary page"
    This page belongs to the design spike `spike/run-code-render`. It is not meant to be merged.

Press **Run Code** under an example. The first press loads Python (Pyodide) and the viewer, which takes a few seconds;
later presses on this page are fast. The diagram is the same viewer that `buildzr serve` shows, drawn from the same
build steps, all in your browser.

## The Quick Start workspace

The finished `workspaces/hello.py` of the [Quick Start](getting-started/quick-start.md). It defines no element with
children, so the viewer opens on the whole landscape.

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    StyleElements,
    SystemContextView,
)

with Workspace('hello') as w:
    user = Person('User', description='A user of the system')
    system = SoftwareSystem(
        'Web Application',
        description='Our main web application'
    )

    user >> "Uses" >> system

    StyleElements(
        on=[user],
        shape='Person'
    )

    SystemContextView(
        software_system_selector=system,
        key='system-context',
        description='System Context View',
        auto_layout='tb'
    )
```

## Containers and components

The containers and components example of [Models](user-guide/models.md). It is a fragment: Run Code puts it in a
workspace. The viewer opens with the last element that has children expanded: the Web Application container.

```python
with SoftwareSystem("X") as x:

    wa = Container("Web Application", technology="Java and Spring boot")

    db = Container("Database Schema")

    wa >> "Reads from and writes to" >> db

    with wa:
        api_layer = Component("API Layer")
        db_layer = Component("Database Layer")

        api_layer >> "Runs queries/transactions on" >> db_layer
```

## Saying where the viewer opens

A snippet can name the element to show with a `# focus:` comment (hidden on the page). Here it selects the database
container, though the container that was created last is the API.

```python
# focus: shop/database
from buildzr.dsl import Workspace, Person, SoftwareSystem, Container

with Workspace('shop') as w:
    customer = Person('Customer')
    with SoftwareSystem('Shop') as shop:
        database = Container('Database', technology='PostgreSQL')
        api = Container('API', technology='Python')
        api >> ('Reads from and writes to', 'SQL') >> database
    customer >> 'Buys from' >> api
```
