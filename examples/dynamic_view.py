"""
Dynamic View Example

This example demonstrates the DynamicView feature in buildzr DSL,
based on the Structurizr DSL cookbook example:
https://docs.structurizr.com/dsl/cookbook/dynamic-view/

Dynamic views show ordered interactions between elements for specific
use cases, stories, or features. They display instances of relationships
in a specific sequence, illustrating how elements collaborate at runtime.
"""

from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    ContainerView,
    DynamicView,
)

with Workspace('Online Book Store') as w:

    # Define the model
    customer = Person('Customer')

    with SoftwareSystem('Online Book Store') as online_book_store:
        webapp = Container('Web Application')
        database = Container('Database')

    # Define static relationships
    customer >> "Browses and makes purchases using" >> webapp
    webapp >> "Reads from and writes to" >> database

    # Container view showing the static structure
    ContainerView(
        software_system_selector=online_book_store,
        key='online-book-store-containers',
        description="The container view for the Online Book Store",
        auto_layout='lr',
    )

    # Dynamic view 1: Request past orders feature
    # Shows the sequence of interactions when a customer requests their past orders
    DynamicView(
        key='request-past-orders',
        description="Request past orders feature",
        title="Request past orders feature",
        scope=online_book_store,
        steps=[
            customer >> "Requests past orders from" >> webapp,
            webapp >> "Queries for orders using" >> database,
        ],
        auto_layout='lr',
    )

    # Dynamic view 2: Browse top 20 books feature
    # Shows the sequence of interactions when a customer browses top books
    DynamicView(
        key='browse-top-books',
        description="Browse top 20 books feature",
        title="Browse top 20 books feature",
        scope=online_book_store,
        steps=[
            customer >> "Requests the top 20 books from" >> webapp,
            webapp >> "Queries the top 20 books using" >> database,
        ],
        auto_layout='lr',
    )

    w.to_json('dynamic_view.json', pretty=True)