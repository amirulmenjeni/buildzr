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
    Views,
)

# Using the new context manager-based syntax
with Workspace('w') as w:
    with Group('My Company') as g:
        u = Person('Web Application User')
        u.labeled('u')
        webapp = SoftwareSystem('Corporate Web App')
        webapp.labeled('webapp')

        db = webapp.Container('database')
        api = webapp.Container('api')

        # Define relationship between containers
        api >> "Reads and writes data from/to" >> db

    with Group('Microsoft') as g:
        email_system = SoftwareSystem('Microsoft 365')
        email_system.labeled('email_system')

    # Define relationships at workspace level
    u >> [
        desc("Reads and writes email using") >> email_system,
        desc("Create work order using") >> webapp
    ]

    webapp >> "sends notification using" >> email_system

    # Define views
    with Views() as views:
        views.SystemContextView(
            webapp,
            key='web_app_system_context_00',
            description="Web App System Context",
            auto_layout='lr',
            exclude_elements=[
                u  # Direct reference to element
            ]
        )

        views.ContainerView(
            webapp,
            key='web_app_container_view_00',
            auto_layout='lr',
            description="Web App Container View",
        )

# Writes the Workspace model to a JSON file.
with open(os.path.join(os.path.curdir, f"{__file__.split('.')[0]}.json"), 'w', encoding='utf-8') as f:
    json.dump(w.model, f, ensure_ascii=False, indent=4, cls=JsonEncoder)