"""The 'dynamic' fixture (``tests/site/fixtures/dynamic``): dynamic views to step through in the viewer."""

from __future__ import annotations

from buildzr.dsl import (
    Container,
    ContainerView,
    DynamicView,
    Person,
    SoftwareSystem,
    Workspace,
)


def dynamic_workspace() -> Workspace:
    """A factory: the Shop system with three containers and a Payments system.

    - ``checkout`` has five steps; steps 2 and 5 are the same pair (Web App -> API), drawn as two arrows.
    - ``sign-in`` has two steps, to switch between dynamic views.
    - ``shop-containers`` is a container view: no step controls there.
    - Shop has a tag of its own, so the tag filter tests of the viewer find two tags that do not cover the landscape.
    """
    with Workspace("Dynamic steps", scope=None) as w:
        customer = Person("Customer")
        with SoftwareSystem("Shop", tags={"Internal"}) as shop:
            web = Container("Web App")
            api = Container("API")
            db = Container("Database")
        payments = SoftwareSystem("Payments")
        customer >> "Uses" >> web
        web >> "Calls" >> api
        api >> "Reads from and writes to" >> db
        api >> "Charges cards using" >> payments

        ContainerView(software_system_selector=shop, key="shop-containers", description="The containers of the Shop")
        DynamicView(
            key="checkout", title="Checkout", description="A customer checks out", scope=shop,
            steps=[
                customer >> "Submits an order using" >> web,
                web >> "Posts the order to" >> api,
                api >> "Saves the order in" >> db,
                api >> "Charges the card with" >> payments,
                web >> "Polls the order status from" >> api,
            ],
        )
        DynamicView(
            key="sign-in", title="Sign in", description="A customer signs in", scope=shop,
            steps=[
                customer >> "Signs in using" >> web,
                web >> "Checks the password with" >> api,
            ],
        )
    return w
