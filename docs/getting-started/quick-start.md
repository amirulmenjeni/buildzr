# Quick Start

Let's start creating your first architecture diagram with `buildzr`!

TL;DR:

1. Click **Run Code** in the [Complete Example](#complete-example)
2. Copy the JSON output
3. Head over to [https://structurizr.com/json](https://structurizr.com/json), paste the JSON output, and hit **Render**

## Your First Workspace

### Step 1: Import from `buildzr.dsl`

All `buildzr` DSL classes and methods can be found here. If you need something to create a C4 model construct, you'll find them in `buildzr.dsl`.

For now, let's import the DSL constructs that we need to follow this quick-start guide:

```python
# norun
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    StyleElements,
    SystemContextView,
)
```

### Step 2: Create a Workspace

A workspace is the top-level container for your architecture model.

All your models, styling, and view defintions should go under your `Workspace` context, as we'll see later.

```python
# norun
with Workspace('my-workspace') as w:
    # Your models, stylings, views goes here.
    pass
```

### Step 3: Define Your Models

Inside the workspace context, you can define the elements and their relationships.

```python
# norun
with Workspace('my-workspace') as w:
    # Define a person (user)
    user = Person('User', description='A user of the system')

    # Define a software system
    system = SoftwareSystem(
        'Web Application',
        description='Our main web application'
    )

    # Define the relationship
    user >> "Uses" >> system
```

### Step 4: Style your Elements

Here, we use `StyleElements` to directly apply a styling to the `user` element, so that it has a `Person` shape (instead of just a boring rectangle!)

```python hl_lines="12-15"
# norun
with Workspace('my-workspace') as w:
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
```

### Step 5: Create a View

So far, we've only created the models (the elements and their relationship), and the styling to be applied to a model. To finally be able to put a nice picture to the models and style descriptions, we need to create a view.

For now, we'll just create one simple `SystemContextView`.

```python hl_lines="15-20"
# norun
with Workspace('my-workspace') as w:
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
        auto_layout='tb'  # top-to-bottom layout
    )
```

### Step 6: Export to JSON, or optionally PlantUML

Finally, export your workspace to a JSON file (or PlantUML files).

```python hl_lines="24-25"
# norun
with Workspace('my-workspace') as w:
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

    # Export to JSON file
    w.save(path='workspace.json')

    # Requires `pip install buildzr[export-plantuml]` and Java 11+
    w.save(format='plantuml', path='path/to/output/folder')
```

### Step 7: Run your Code

You can simply save the code in a `.py` file, and run it with `python`.

For example, if you save the code in a file called `workspace.py`:

```bash
python workspace.py
```

You'll see a new file being created: `workspace.json`.

See [Viewing Your Diagram](#viewing-your-diagram) on how you can use the content of `workspace.json` to render the architecture diagram.

!!! tip
    You can click the "Run Code" button in the [Complete Example](#complete-example) section below and copy the JSON output.

## Complete Example

Here's the complete code:

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    StyleElements,
    SystemContextView,
)

with Workspace('my-workspace') as w:
    # Define models
    user = Person('User', description='A user of the system')
    system = SoftwareSystem(
        'Web Application',
        description='Our main web application'
    )

    # Define relationships
    user >> "Uses" >> system

    # Style the `user` element to make it `Person` shaped.
    StyleElements(
        on=[user],
        shape='Person'
    )

    # Create view
    SystemContextView(
        software_system_selector=system,
        key='system-context',
        description='System Context View',
        auto_layout='tb'
    )

    # Export to JSON file
    w.save(path='workspace.json')
```

## Viewing Your Diagram

The generated JSON file follows the [Structurizr JSON schema](https://github.com/structurizr/json). You can visualize it using:

1. **Online**: Upload to [https://structurizr.com/json](https://structurizr.com/json)
2. **[Structurizr Lite](https://docs.structurizr.com/lite)**: Run a local instance
   ```bash
   docker run -it --rm -p 8080:8080 -v $PWD:/usr/local/structurizr structurizr/lite
   ```
3. **[Structurizr CLI](https://docs.structurizr.com/cli)**: Convert to other formats (PlantUML, Mermaid, etc.)

Or if you've used `save(format='plantuml')`, you can view the generated `.puml` files using a [C4PlantUML](https://github.com/plantuml-stdlib/C4-PlantUML) viewer. For example, you can try copy and paste the contents of the generated `.puml` in this [PlantUML Web Editor](https://www.plantuml.com/plantuml/uml/ZOvFIyGm4CNl-HIrfowupSMJfvNrk6BnprccwT069fEGcI3zzhO5YoAAf_VcmVlDEub2rXB8N7bsL0Qi9jKajzPcU6z7hrFfYs1saHLPMnU3JGIyTewY0_dUdc-EtHgzFbni057CI_HsNXhW6NERLhxfC4la9croHnxakgelq2FLYtbCwYC3LVSeBlljgWzcXpJkq_selg2RE58Svpz0pxCeXaOs-UztyuJqVV3lAtR4bpa7Sq8UIg0F)

## Next Steps

Now that you've created your first diagram, explore more:

- [Core Concepts](../user-guide/core-concepts.md): Understand the fundamentals
- [Models](../user-guide/models.md): Learn about different model types
- [Relationships](../user-guide/relationships.md): Learn more about defining relationships between elements
- [Views](../user-guide/views.md): Create different types of views