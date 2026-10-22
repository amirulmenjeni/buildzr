"""The 'custom' fixture (``tests/site/fixtures/custom``): custom elements and custom views beside C4 views."""

from __future__ import annotations

from buildzr.dsl import (
    Container,
    ContainerView,
    CustomView,
    Element,
    Person,
    SoftwareSystem,
    StyleElements,
    SystemLandscapeView,
    Workspace,
)


def custom_workspace() -> Workspace:
    """A factory: two people, a MES (two containers) and an ERP next to hardware that is not software.

    Custom elements: PLC and Sensor (metadata "Hardware"), Conveyor (no metadata) and Spare Part (in no view).
    Views: a landscape and the containers of the MES (custom elements in standard views), and two custom views,
    one with all the devices and one with the PLC and the Sensor only. The landscape leaves the spare part out.
    """
    with Workspace("Factory", description="Software next to the machines it controls.", scope=None,
                   implied_relationships=True) as w:
        operator = Person("Operator", description="Runs the line.")
        supervisor = Person("Supervisor", description="Reviews the shift report.")
        with SoftwareSystem("MES", description="Manufacturing execution system.") as mes:
            dashboard = Container("Dashboard", technology="TypeScript")
            collector = Container("Collector", technology="Python")
        erp = SoftwareSystem("ERP", description="Plans production orders.", tags={"External"})
        plc = Element("PLC", metadata="Hardware", description="Controls the line.", tags={"Device"})
        sensor = Element("Sensor", metadata="Hardware", description="Measures the belt speed.", tags={"Device"})
        conveyor = Element("Conveyor", description="Moves the parts.")
        spare = Element("Spare Part", metadata="Stock", description="Not on any diagram.")

        operator >> ("Watches", "HTTPS") >> dashboard
        supervisor >> ("Reads reports from", "HTTPS") >> dashboard
        collector >> "Receives orders from" >> erp
        dashboard >> "Reads from" >> collector
        collector >> ("Polls", "OPC UA") >> plc
        plc >> "Reads" >> sensor
        plc >> "Drives" >> conveyor

        StyleElements(on=["Device"], background="#1f6f5c", color="#ffffff", shape="Hexagon")
        SystemLandscapeView(key="landscape", description="", title="System landscape", exclude_elements=[spare])
        ContainerView(mes, key="mes-containers", description="", title="MES containers")
        CustomView(key="devices", description="Every device on the line.", title="Devices",
                   exclude_elements=[spare])
        CustomView(key="sensing", description="", title="Sensing", exclude_elements=[conveyor, spare])
    return w
