"""
Workspace Extension Example

This example demonstrates how to extend an existing workspace.json file,
similar to Structurizr DSL's `workspace extends ...` syntax.

See: https://docs.structurizr.com/dsl/cookbook/workspace-extension/

The parent workspace (system_landscape.json) defines:
- Software System A
- Software System B
- A relationship: A -> B "Gets data X from"

This child workspace extends it by:
- Adding containers (Web Application, Database) to System A
- Creating relationships between the new containers and System B
"""

import os
from buildzr.dsl import (
    Workspace,
    Container,
    SystemContextView,
    ContainerView,
)

# Get the path to the parent workspace
parent_workspace = os.path.join(os.path.dirname(__file__), 'system_landscape.json')

# Extend the parent workspace - parent elements are accessible directly on w
with Workspace('Extended Workspace', extend=parent_workspace) as w:

    # Access parent elements via software_system() method for typed access
    # (normalized names: lowercase, underscores replace spaces)
    system_a = w.software_system().a
    system_b = w.software_system().b

    # Add containers to System A (from the parent workspace)
    with system_a:
        webapp = Container('Web Application', 'The web application')
        database = Container('Database', 'Stores data', technology='PostgreSQL')

        # Create relationships
        webapp >> "Gets data X from" >> system_b
        webapp >> "Reads from and writes to" >> database

    # Add views
    SystemContextView(
        software_system_selector=system_a,
        key='A-SystemContext',
        description='System Context for A',
        auto_layout='lr',
    )

    ContainerView(
        software_system_selector=system_a,
        key='A-Containers',
        description='Container view for A',
        auto_layout='tb',
    )

    # Export the merged workspace
    output_path = os.path.join(os.path.dirname(__file__), 'workspace_extension.json')
    w.save(path=output_path, pretty=True)
    print(f"Exported to: {output_path}")
