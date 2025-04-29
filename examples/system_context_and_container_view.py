import os
import json

from buildzr.encoders import JsonEncoder

from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    SystemContextView,
    ContainerView,
    desc,
    Group,
)

with Workspace('w') as w:
    with Group("My Company"):
        u = Person('Web Application User').labeled('u')
        webapp = SoftwareSystem('Corporate Web App').labeled('webapp')
        with webapp:
            database = Container('database')
            api = Container('api')
            api >> "Reads and writes data from/to" >> database
    with Group("Microsoft"):
        email_system = SoftwareSystem('Microsoft 365').labeled('email_system')

    u >> [
        desc("Reads and writes email using") >> email_system,
        desc("Create work order using") >> webapp,
    ]
    webapp >> "sends notification using" >> email_system

    w.with_views(
        SystemContextView(
            lambda w: w.software_system().webapp,
            key='web_app_system_context_00',
            description="Web App System Context",
            auto_layout='lr',
            exclude_elements=[
                lambda w, e: w.person().u == e,
            ]
        ),
        ContainerView(
            lambda w: w.software_system().webapp,
            key='web_app_container_view_00',
            auto_layout='lr',
            description="Web App Container View",
        )
    )

# Writes the Workspace model to a JSON file.
with open(os.path.join(os.path.curdir, f"{__file__.split('.')[0]}.json"), 'w', encoding='utf-8') as f:
    json.dump(w.model, f, ensure_ascii=False, indent=4, cls=JsonEncoder)