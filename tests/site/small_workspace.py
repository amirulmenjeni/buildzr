"""The 'small' interface fixture (``tests/site/fixtures/small``) written as a DSL workspace."""

from __future__ import annotations

from buildzr.dsl import (
    Component,
    Container,
    ContainerView,
    Person,
    SoftwareSystem,
    StyleElements,
    SystemLandscapeView,
    Workspace,
)


def small_workspace() -> Workspace:
    """Two people, three systems; Billing has three containers, Billing API three components."""
    with Workspace("Small fixture", description="Hand-written v4 interface fixture.", scope=None,
                   implied_relationships=True) as w:
        customer = Person("Customer", description="Pays invoices online.")
        agent = Person("Support Agent", description="Handles refunds.")
        with SoftwareSystem("Billing", description="Invoices customers and takes payments.",
                            properties={"owner": "payments-team"}) as billing:
            web = Container("Web", description="Customer billing portal.", technology="TypeScript, React")
            with Container("API", description="Invoicing and payment API.", technology="Go") as api:
                invoicer = Component("Invoicer", description="Builds monthly invoices.", technology="Go")
                payments = Component("Payments", description="Charges cards.", technology="Go", tags={"PCI"})
                ledger = Component("Ledger Repo", description="Ledger persistence.", technology="Go, sqlc")
            db = Container("DB", description="Invoices and ledger.", technology="PostgreSQL",
                           tags={"Database"})
        crm = SoftwareSystem("CRM", description="Customer records.", tags={"External"})
        email = SoftwareSystem("Email", description="Sends e-mail.", tags={"External"})

        customer >> ("Uses", "HTTPS") >> web
        customer >> ("Pays", "HTTPS") >> web
        web >> ("Calls", "JSON/HTTPS") >> api
        web >> ("Submits payment", "JSON/HTTPS") >> payments
        invoicer >> ("Reads customers", "HTTPS") >> crm
        invoicer >> ("Sends invoices", "SMTP") >> email
        invoicer >> "Charges" >> payments
        payments >> ("Writes payments", "SQL") >> db
        ledger >> ("Reads and writes", "SQL") >> db
        crm >> ("Requests refunds", "HTTPS") >> api
        agent >> ("Uses", "HTTPS") >> crm

        StyleElements(on=["External"], background="#999999")
        StyleElements(on=["Database"], shape="Cylinder")
        SystemLandscapeView(key="Landscape", description="", title="System landscape")
        ContainerView(billing, key="Billing-Containers", description="", title="Billing - containers",
                      exclude_elements=[email])
    return w
