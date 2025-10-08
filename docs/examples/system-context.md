# System Context Example

This example demonstrates creating a System Context view for a corporate web application.

## Scenario

We're documenting a corporate web application that:

- Is used by web application users
- Integrates with Microsoft 365 for email functionality
- Is part of "My Company" (internal system)

## Complete Code

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    SystemContextView,
    desc,
    Group,
)

with Workspace('corporate-webapp') as w:
    # Define elements with groups
    with Group("My Company"):
        user = Person('Web Application User')
        webapp = SoftwareSystem('Corporate Web App')

    with Group("Microsoft"):
        email_system = SoftwareSystem('Microsoft 365')

    # Define relationships
    user >> [
        desc("Reads and writes email using") >> email_system,
        desc("Creates work orders using") >> webapp,
    ]
    webapp >> "Sends notifications using" >> email_system

    # Create system context view
    SystemContextView(
        software_system_selector=webapp,
        key='web_app_system_context',
        description="Web App System Context",
        auto_layout='lr',
    )

    # Export to JSON
    w.to_json('corporate_webapp.json')
```

## Code Breakdown

### 1. Imports

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    SystemContextView,
    desc,
    Group,
)
```

We import the necessary classes for creating workspaces, systems, people, views, and groups.

### 2. Create Workspace

```python
with Workspace('corporate-webapp') as w:
    # ...
```

The workspace is the container for everything.

### 3. Define Elements with Groups

```python
with Group("My Company"):
    user = Person('Web Application User')
    webapp = SoftwareSystem('Corporate Web App')

with Group("Microsoft"):
    email_system = SoftwareSystem('Microsoft 365')
```

Groups help organize elements visually in the diagram.

### 4. Define Relationships

```python
user >> [
    desc("Reads and writes email using") >> email_system,
    desc("Creates work orders using") >> webapp,
]
webapp >> "Sends notifications using" >> email_system
```

The `>>` operator creates relationships. Use `desc()` for more readable relationship definitions.

### 5. Create View

```python
SystemContextView(
    software_system_selector=webapp,
    key='web_app_system_context',
    description="Web App System Context",
    auto_layout='lr',
)
```

The System Context view focuses on the `webapp` system and shows its immediate environment.

### 6. Export

```python
w.to_json('corporate_webapp.json')
```

Export to JSON for visualization with Structurizr tools.

## Variations

### Exclude Specific Elements

```python
SystemContextView(
    software_system_selector=webapp,
    key='web_app_system_context',
    description="Web App System Context - Internal Only",
    auto_layout='lr',
    exclude_elements=[email_system]  # Don't show external systems
)
```

### Different Layouts

```python
# Top to bottom
SystemContextView(
    software_system_selector=webapp,
    key='context_tb',
    auto_layout='tb'
)

# Bottom to top
SystemContextView(
    software_system_selector=webapp,
    key='context_bt',
    auto_layout='bt'
)
```

### Multiple Systems

```python
with Group("My Company"):
    crm = SoftwareSystem('CRM')
    erp = SoftwareSystem('ERP')
    webapp = SoftwareSystem('Web App')

webapp >> "Gets customer data from" >> crm
webapp >> "Creates invoices in" >> erp

# Create context views for each system
SystemContextView(software_system_selector=webapp, key='webapp_context')
SystemContextView(software_system_selector=crm, key='crm_context')
SystemContextView(software_system_selector=erp, key='erp_context')
```

## Viewing the Result

1. **Online viewer**: Upload `corporate_webapp.json` to [https://structurizr.com/json](https://structurizr.com/json)

2. **Structurizr Lite** (Docker):
   ```bash
   docker run -it --rm -p 8080:8080 -v $PWD:/usr/local/structurizr structurizr/lite
   ```

3. **Export to PlantUML**:
   ```bash
   structurizr-cli export -workspace corporate_webapp.json -format plantuml
   ```

## Next Steps

- [Container View Example](container-view.md) - Drill down into containers
- [Deployment Example](deployment.md) - Show infrastructure
- [Styling Guide](../user-guide/styling.md) - Customize appearance
