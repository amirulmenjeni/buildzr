"""
Buildzr equivalent of cookbook_custom_element.dsl

This script creates the exact same model as the DSL file for comparison purposes.

DSL content:
    workspace {
        model {
            a = softwareSystem "A"
            b = element "B" "Hardware System"
            a -> b "Sends control signals to"
        }
        views {
            systemContext a "Diagram1" {
                include *
                autoLayout lr
            }
        }
    }
"""

from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Element,
    SystemContextView,
)

with Workspace('Name') as w:
    # Model - matching DSL exactly
    a = SoftwareSystem('A')
    b = Element('B', metadata='Hardware System')

    # Relationships - matching DSL exactly
    a >> "Sends control signals to" >> b

    # Views - matching DSL exactly
    SystemContextView(
        software_system_selector=a,
        key='Diagram1',
        description='Diagram1',
        auto_layout='lr',
    )

    # Export
    w.save(path='cookbook_custom_element_buildzr.json', pretty=True)
    print(f"Generated: cookbook_custom_element_buildzr.json")
