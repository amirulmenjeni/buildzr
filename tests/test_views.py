from typing import Optional
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Component,
    SystemContextView,
    ContainerView,
    ComponentView,
)

def test_system_context_view() -> Optional[None]:

    w = Workspace('w')\
            .contains(
                Person('u'),
                SoftwareSystem('email_system')\
                    .contains(
                        Container('email_c1'),
                        Container('email_c2'),
                    )\
                    .where(lambda c1, c2: [
                        c1 >> "Uses" >> c2,
                    ]),
                SoftwareSystem('business_app')
                    .contains(
                        Container('business_app_c1'),
                        Container('business_app_c2'),
                    )
                    .where(lambda c1, c2: [
                        c1 >> "Gets data from" >> c2,
                    ]),
                SoftwareSystem('git_repo'), # Unrelated!
                SoftwareSystem('external_system'), # Also unrelated!
            )\
            .where(lambda u, email_system, business_app, git_repo, external_system: [
                u >> "Uses" >> business_app,
                u >> "Hacks" >> git_repo,
                business_app >> "Notifies users using" >> email_system,
                git_repo >> "Uses" >> external_system,
            ])\
            .with_views(
                SystemContextView(
                    software_system_selector=lambda w: w.software_system().business_app,
                    key="ss_business_app",
                    description="The business app",
                )
            )\
            .get_workspace()

    element_ids =  list(map(lambda x: x.id, w.model.views.systemContextViews[0].elements))
    relationship_ids =  list(map(lambda x: x.id, w.model.views.systemContextViews[0].relationships))

    print('element ids:', element_ids)
    print('person id:', w.person().u.model.id)
    print('email system id:', w.software_system().email_system.model.id)
    print('business app id:', w.software_system().business_app.model.id)
    print('git repo id:', w.software_system().git_repo.model.id)

    assert any(w.model.views.systemContextViews)
    assert len(w.model.views.systemContextViews) == 1
    assert len(element_ids) == 3
    assert len(relationship_ids) == 2
    assert w.person().u.model.id in element_ids
    assert w.software_system().business_app.model.id in element_ids
    assert w.software_system().email_system.model.id in element_ids
    assert w.software_system().git_repo.model.id not in element_ids
    assert w.software_system().business_app.business_app_c1.model.id not in element_ids
    assert w.software_system().business_app.business_app_c2.model.id not in element_ids
    assert w.software_system().email_system.email_c1.model.id not in element_ids
    assert w.software_system().email_system.email_c2.model.id not in element_ids
    assert w.software_system().business_app.model.relationships[0].id in relationship_ids
    assert w.software_system().business_app.model.relationships[0].sourceId == w.software_system().business_app.model.id
    assert w.software_system().business_app.model.relationships[0].destinationId == w.software_system().email_system.model.id
    assert w.person().u.model.relationships[0].id in relationship_ids
    assert w.person().u.model.relationships[0].sourceId == w.person().u.model.id
    assert w.person().u.model.relationships[0].destinationId == w.software_system().business_app.model.id

def test_system_context_view_with_exclude_user() -> Optional[None]:

    w = Workspace('w')\
            .contains(
                Person('u'),
                SoftwareSystem('email_system')\
                    .contains(
                        Container('email_c1'),
                        Container('email_c2'),
                    )\
                    .where(lambda c1, c2: [
                        c1 >> "Uses" >> c2,
                    ]),
                SoftwareSystem('business_app')
                    .contains(
                        Container('business_app_c1'),
                        Container('business_app_c2'),
                    )
                    .where(lambda c1, c2: [
                        c1 >> "Gets data from" >> c2,
                    ]),
                SoftwareSystem('git_repo'), # Unrelated!
                SoftwareSystem('external_system'), # Also unrelated!
            )\
            .where(lambda u, email_system, business_app, git_repo, external_system: [
                u >> "Uses" >> business_app,
                u >> "Hacks" >> git_repo,
                business_app >> "Notifies users using" >> email_system,
                git_repo >> "Uses" >> external_system,
            ])\
            .with_views(
                SystemContextView(
                    software_system_selector=lambda w: w.software_system().business_app,
                    key="ss_business_app",
                    description="The business app",
                    exclude_elements=[
                        lambda w, e: e == w.person().u,
                    ]
                )
            )\
            .get_workspace()

    element_ids =  list(map(lambda x: x.id, w.model.views.systemContextViews[0].elements))
    relationship_ids =  list(map(lambda x: x.id, w.model.views.systemContextViews[0].relationships))

    print('element ids:', element_ids)
    print('person id:', w.person().u.model.id)
    print('email system id:', w.software_system().email_system.model.id)
    print('business app id:', w.software_system().business_app.model.id)
    print('git repo id:', w.software_system().git_repo.model.id)

    assert any(w.model.views.systemContextViews)
    assert len(w.model.views.systemContextViews) == 1
    assert len(element_ids) == 2
    assert len(relationship_ids) == 1
    assert w.person().u.model.id not in element_ids
    assert w.software_system().business_app.model.id in element_ids
    assert w.software_system().email_system.model.id in element_ids
    assert w.software_system().git_repo.model.id not in element_ids
    assert w.software_system().business_app.business_app_c1.model.id not in element_ids
    assert w.software_system().business_app.business_app_c2.model.id not in element_ids
    assert w.software_system().email_system.email_c1.model.id not in element_ids
    assert w.software_system().email_system.email_c2.model.id not in element_ids
    assert w.software_system().business_app.model.relationships[0].id in relationship_ids
    assert w.software_system().business_app.model.relationships[0].sourceId == w.software_system().business_app.model.id
    assert w.software_system().business_app.model.relationships[0].destinationId == w.software_system().email_system.model.id

    # We're excluding the user in the view. Its relationship with the software
    # system shouldn't be shown as well.
    assert w.person().u.model.relationships[0].id not in relationship_ids
    assert w.person().u.model.relationships[0].sourceId == w.person().u.model.id
    assert w.person().u.model.relationships[0].destinationId == w.software_system().business_app.model.id

def test_container_view() -> Optional[None]:

    w = Workspace('w')\
            .contains(
                Person('user'),
                SoftwareSystem('app')
                    .contains(
                        Container('web_application'),
                        Container('database'),
                    )
                    .where(lambda web_application, database: [
                        web_application >> "Reads from and writes to" >> database,
                    ]),
                SoftwareSystem('git_repo'), # Unrelated!
                SoftwareSystem('external_system'), # Also unrelated!
            )\
            .where(lambda user, app, git_repo, external_system: [
                user >> "Uses" >> app.web_application,
                user >> "Hacks" >> git_repo,
                git_repo >> "Uses" >> external_system,
            ])\
            .with_views(
                ContainerView(
                    software_system_selector=lambda w: w.software_system().app,
                    key="ss_business_app",
                    description="The business app",
                )
            )\
            .get_workspace()

    element_ids =  list(map(lambda x: x.id, w.model.views.containerViews[0].elements))
    relationship_ids =  list(map(lambda x: x.id, w.model.views.containerViews[0].relationships))

    print('element ids:', element_ids)
    print('person id:', w.person().user.model.id)
    print('app id:', w.software_system().app.model.id)
    print('  web application id:', w.software_system().app.web_application.model.id)
    print('  database id:', w.software_system().app.database.model.id)
    print('git repo id:', w.software_system().git_repo.model.id)
    print('external system id:', w.software_system().external_system.model.id)

    assert any(w.model.views.containerViews)
    assert len(w.model.views.containerViews) == 1
    assert len(element_ids) == 3 # Only the two containers of the selected software system + the user
    assert len(relationship_ids) == 2 # Only the one relationship between the two containers + with the user
    assert w.person().user.model.id in element_ids
    assert w.software_system().app.model.id not in element_ids
    assert w.software_system().git_repo.model.id not in element_ids
    assert w.software_system().app.web_application.model.id in element_ids
    assert w.software_system().app.database.model.id in element_ids
    assert w.person().user.model.relationships[0].id in relationship_ids

def test_component_view() -> Optional[None]:

    w = Workspace('workspace')\
        .contains(
            Person('User'),
            SoftwareSystem("Software System")\
            .contains(
                Container("Web Application")\
                .contains(
                    Component("Component 1"),
                    Component("Component 2"),
                )\
                .where(lambda c1, c2: [
                    c1 >> "Uses" >> c2,
                ]),
                Container("Database"),
            )\
            .where(lambda web_application, database: [
                web_application.component_2 >> "Reads from and writes to" >> database,
            ]),
        )\
        .where(lambda user, software_system: [
            user >> "Uses" >> software_system.web_application.component_1,
        ])\
        .with_views(
            ComponentView(
                container_selector=lambda w: w.software_system().software_system.web_application,
                key="web_application_container_00",
                description="Component View Test",
            )
        )\
        .get_workspace()

    element_ids =  list(map(lambda x: x.id, w.model.views.componentViews[0].elements))
    relationship_ids =  list(map(lambda x: x.id, w.model.views.componentViews[0].relationships))

    print("user id:", w.person().user.model.id)
    print("software system id", w.software_system().software_system.model.id)
    print("  web application id", w.software_system().software_system.web_application.model.id)
    print("    component 1 id", w.software_system().software_system.web_application.component_1.model.id)
    print("    component 2 id", w.software_system().software_system.web_application.component_2.model.id)
    print("  database id", w.software_system().software_system.database.model.id)

    assert any(w.model.views.componentViews)
    assert len(w.model.views.componentViews) == 1

    assert w.person().user.model.id in element_ids
    assert w.software_system().software_system.web_application.component_1.model.id in element_ids
    assert w.software_system().software_system.web_application.component_2.model.id in element_ids
    assert w.software_system().software_system.database.model.id in element_ids

    assert w.person().user.model.relationships[0].id in relationship_ids
    assert w.person().user.model.relationships[0].sourceId in element_ids
    assert w.person().user.model.relationships[0].destinationId in element_ids
    assert w.software_system().software_system.web_application.component_1.model.relationships[0].id in relationship_ids
    assert w.software_system().software_system.web_application.component_2.model.relationships[0].id in relationship_ids
    assert w.software_system().software_system.web_application.component_2.model.relationships[0].sourceId in element_ids
    assert w.software_system().software_system.web_application.component_2.model.relationships[0].destinationId in element_ids

def test_component_view_with_exclude_user() -> Optional[None]:

    w = Workspace('workspace')\
        .contains(
            Person('User'),
            SoftwareSystem("Software System")\
            .contains(
                Container("Web Application")\
                .contains(
                    Component("Component 1"),
                    Component("Component 2"),
                )\
                .where(lambda c1, c2: [
                    c1 >> "Uses" >> c2,
                ]),
                Container("Database"),
            )\
            .where(lambda web_application, database: [
                web_application.component_2 >> "Reads from and writes to" >> database,
            ]),
        )\
        .where(lambda user, software_system: [
            user >> "Uses" >> software_system.web_application.component_1,
        ])\
        .with_views(
            ComponentView(
                container_selector=lambda w: w.software_system().software_system.web_application,
                key="web_application_container_00",
                description="Component View Test",
                exclude_elements=[
                    lambda w, e: e == w.person().user
                ]
            )
        )\
        .get_workspace()

    element_ids =  list(map(lambda x: x.id, w.model.views.componentViews[0].elements))
    relationship_ids =  list(map(lambda x: x.id, w.model.views.componentViews[0].relationships))

    print("user id:", w.person().user.model.id)
    print("software system id", w.software_system().software_system.model.id)
    print("  web application id", w.software_system().software_system.web_application.model.id)
    print("    component 1 id", w.software_system().software_system.web_application.component_1.model.id)
    print("    component 2 id", w.software_system().software_system.web_application.component_2.model.id)
    print("  database id", w.software_system().software_system.database.model.id)

    assert any(w.model.views.componentViews)
    assert len(w.model.views.componentViews) == 1

    assert w.person().user.model.id not in element_ids
    assert w.software_system().software_system.web_application.component_1.model.id in element_ids
    assert w.software_system().software_system.web_application.component_2.model.id in element_ids
    assert w.software_system().software_system.database.model.id in element_ids

    assert w.person().user.model.relationships[0].id not in relationship_ids
    assert w.person().user.model.relationships[0].sourceId not in element_ids
    assert w.person().user.model.relationships[0].destinationId in element_ids
    assert w.software_system().software_system.web_application.component_1.model.relationships[0].id in relationship_ids
    assert w.software_system().software_system.web_application.component_2.model.relationships[0].id in relationship_ids
    assert w.software_system().software_system.web_application.component_2.model.relationships[0].sourceId in element_ids
    assert w.software_system().software_system.web_application.component_2.model.relationships[0].destinationId in element_ids