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

w = Workspace('w')\
        .contains(
            Group(
                "My Company",
                Person('Web Application User').labeled('u'),
                SoftwareSystem('Corporate Web App').labeled('webapp')
                    .contains(
                        Container('database'),
                        Container('api'),
                    )\
                    .where(lambda s: [
                        s.api >> "Reads and writes data from/to" >> s.database,
                    ])
            ),
            Group(
                "Microsoft",
                SoftwareSystem('Microsoft 365').labeled('email_system'),
            )
        )\
        .where(lambda w: [
            w.person().u >> [
                desc("Reads and writes email using") >> w.software_system().email_system,
                desc("Create work order using") >> w.software_system().webapp,
            ],
            w.software_system().webapp >> "sends notification using" >> w.software_system().email_system,
        ])\
        .with_views(
            SystemContextView(
                lambda w: w.software_system().webapp,
                key='web_app_system_context_00',
                description="Web App System Context",
                auto_layout='lr',
                exclude_elements=[
                    lambda w, e: w.person().user == e,
                ]
            ),
            ContainerView(
                lambda w: w.software_system().webapp,
                key='web_app_container_view_00',
                auto_layout='lr',
                description="Web App Container View",
            )
        )\
        .get_workspace()

# Writes the Workspace model to a JSON file.
with open(os.path.join(os.path.curdir, f"{__file__.split('.')[0]}.json"), 'w', encoding='utf-8') as f:
    json.dump(w.model, f, ensure_ascii=False, indent=4, cls=JsonEncoder)