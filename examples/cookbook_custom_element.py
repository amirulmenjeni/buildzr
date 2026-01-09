"""
Custom Element Example

This example demonstrates the custom Element feature in buildzr DSL,
based on the Structurizr DSL cookbook example:
https://docs.structurizr.com/dsl/cookbook/element/

Custom elements allow you to model things that don't fit neatly into the
standard C4 model hierarchy (Person, SoftwareSystem, Container, Component).
Common use cases include hardware devices, business processes, external
services, or any abstract concept you want to visualize in your architecture.

Custom elements:
- Are defined at the workspace level (not inside a SoftwareSystem)
- Can have relationships with other custom elements and C4 elements
- Can be displayed in CustomView and other view types
- Support metadata, tags, and properties like other elements
"""

from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Element,
    SystemLandscapeView,
    CustomView,
)

with Workspace('Custom Element Example') as w:

    # Standard C4 elements
    user = Person('User', description="A user of the system")

    with SoftwareSystem('Software System') as system:
        pass

    # Custom elements (outside C4 model)
    # These represent things that don't fit into Person/SoftwareSystem/Container/Component
    element_a = Element(
        'Element A',
        metadata='Custom Type',
        description='A custom element of type A',
    )

    element_b = Element(
        'Element B',
        metadata='Custom Type',
        description='A custom element of type B',
    )

    # Relationships between custom elements
    element_a >> "Relationship to" >> element_b

    # Relationships between custom elements and C4 elements
    user >> "Uses" >> element_a
    element_b >> "Interacts with" >> system

    # System landscape view - includes all elements (Person, SoftwareSystem, and custom Elements)
    SystemLandscapeView(
        key='landscape',
        description='System landscape showing all elements including custom elements',
        auto_layout='tb',
    )

    # Custom view - provides a canvas for any combination of elements
    CustomView(
        key='custom',
        description='A custom view showing custom elements and their relationships',
        title='Custom Elements View',
        auto_layout='lr',
    )

    w.save(path='cookbook_custom_element.json', pretty=True)
