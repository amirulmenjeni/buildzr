import pytest
from typing import Optional
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Component,
    SystemLandscapeView,
    SystemContextView,
    ContainerView,
    ComponentView,
)

@pytest.mark.parametrize("use_context", [True, False])
def test_system_landscape_view(use_context: bool) -> Optional[None]:

    with Workspace('workspace', scope='landscape') as w:
        user = Person("User")
        system_a = SoftwareSystem("System A")
        system_b = SoftwareSystem("System B")
        user >> "Uses" >> system_a
        system_a >> "Interacts with" >> system_b

        if use_context:
            SystemLandscapeView(
                key="system_landscape_view_00",
                description="System Landscape View Test",
            )

    if not use_context:
        w.apply_views(
            SystemLandscapeView(
                key="system_landscape_view_00",
                description="System Landscape View Test",
            ),
        )

    assert any(w.model.views.systemLandscapeViews)
    assert len(w.model.views.systemLandscapeViews) == 1

    user = w.person().user
    system_a = w.software_system().system_a
    system_b = w.software_system().system_b

    element_ids = list(map(lambda x: x.id, w.model.views.systemLandscapeViews[0].elements))
    relationship_ids = list(map(lambda x: x.id, w.model.views.systemLandscapeViews[0].relationships))

    assert len(element_ids) == 3
    assert {
        user.model.id,
        system_a.model.id,
        system_b.model.id,
    }.issubset(set(element_ids))

    assert len(relationship_ids) == 2
    assert {
        user.model.relationships[0].id,
        system_a.model.relationships[0].id,
    }.issubset(set(relationship_ids))

@pytest.mark.parametrize("use_context", [True, False])
def test_system_context_view(use_context: bool) -> Optional[None]:
    with Workspace('w') as w:
        Person('u')
        with SoftwareSystem('email_system') as email_system:
            Container('email_c1')
            Container('email_c2')
            email_system.email_c1 >> "Uses" >> email_system.email_c2
        with SoftwareSystem('business_app') as business_app:
            Container('business_app_c1')
            Container('business_app_c2')
            business_app.business_app_c1 >> "Gets data from" >> business_app.business_app_c2
        SoftwareSystem('git_repo')
        SoftwareSystem('external_system')
        w.person().u >> "Uses" >> w.software_system().business_app
        w.person().u >> "Hacks" >> w.software_system().git_repo
        w.software_system().business_app >> "Notifies users using" >> w.software_system().email_system
        w.software_system().git_repo >> "Uses" >> w.software_system().external_system

        if use_context:
            SystemContextView(
                software_system_selector=business_app,
                key="ss_business_app",
                description="The business app",
            )

    if not use_context:
        w.apply_views(
            SystemContextView(
                software_system_selector=lambda w: w.software_system().business_app,
                key="ss_business_app",
                description="The business app",
            )
        )

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

@pytest.mark.parametrize("use_context", [True, False])
def test_system_context_view_with_exclude_user(use_context: bool) -> Optional[None]:
    with Workspace('w') as w:
        user = Person('u')
        with SoftwareSystem('email_system') as email_system:
            Container('email_c1')
            Container('email_c2')
            email_system.email_c1 >> "Uses" >> email_system.email_c2
        with SoftwareSystem('business_app') as business_app:
            Container('business_app_c1')
            Container('business_app_c2')
            business_app.business_app_c1 >> "Gets data from" >> business_app.business_app_c2
        SoftwareSystem('git_repo')
        SoftwareSystem('external_system')
        w.person().u >> "Uses" >> w.software_system().business_app
        w.person().u >> "Hacks" >> w.software_system().git_repo
        w.software_system().business_app >> "Notifies users using" >> w.software_system().email_system
        w.software_system().git_repo >> "Uses" >> w.software_system().external_system

        if use_context:
            SystemContextView(
                software_system_selector=business_app,
                key="ss_business_app",
                description="The business app",
                exclude_elements=[
                   user,
                ]
            )

    if not use_context:
        w.apply_views(
            SystemContextView(
                software_system_selector=lambda w: w.software_system().business_app,
                key="ss_business_app",
                description="The business app",
                exclude_elements=[
                    lambda w, e: e == w.person().u,
                ]
            )
        )

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

@pytest.mark.parametrize("use_context", [True, False])
def test_container_view(use_context: bool) -> Optional[None]:
    with Workspace('w') as w:
        Person('user')
        with SoftwareSystem('app') as app:
            Container('web_application')
            Container('database')
            app.web_application >> "Reads from and writes to" >> app.database
        SoftwareSystem('git_repo')
        SoftwareSystem('external_system')
        w.person().user >> "Uses" >> w.software_system().app.web_application
        w.person().user >> "Hacks" >> w.software_system().git_repo
        w.software_system().git_repo >> "Uses" >> w.software_system().external_system

        if use_context:
            ContainerView(
                software_system_selector=app,
                key="ss_business_app",
                description="The business app",
            )

    if not use_context:
        w.apply_views(
            ContainerView(
                software_system_selector=lambda w: w.software_system().app,
                key="ss_business_app",
                description="The business app",
            )
        )

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

@pytest.mark.parametrize("use_context", [True, False])
def test_component_view(use_context: bool) -> Optional[None]:
    with Workspace('workspace') as w:
        Person('User')
        with SoftwareSystem("Software System") as ss:
            with Container("Web Application") as webapp:
                Component("Component 1")
                Component("Component 2")
                webapp.component_1 >> "Uses" >> webapp.component_2
            db = Container("Database")
            webapp.component_2 >> "Reads from and writes to" >> db
        w.person().user >> "Uses" >> w.software_system().software_system.web_application.component_1

        if use_context:
            ComponentView(
                container_selector=webapp,
                key="web_application_container_00",
                description="Component View Test",
            )

    if not use_context:
        w.apply_views(
            ComponentView(
                container_selector=lambda w: w.software_system().software_system.web_application,
                key="web_application_container_00",
                description="Component View Test",
            )
        )

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

@pytest.mark.parametrize("use_context", [True, False])
def test_component_view_with_exclude_user(use_context: bool) -> Optional[None]:
    with Workspace('workspace') as w:
        Person('User')
        with SoftwareSystem("Software System") as ss:
            with Container("Web Application") as webapp:
                Component("Component 1")
                Component("Component 2")
                webapp.component_1 >> "Uses" >> webapp.component_2
            db = Container("Database")
            webapp.component_2 >> "Reads from and writes to" >> db
        w.person().user >> "Uses" >> w.software_system().software_system.web_application.component_1

        if use_context:
            ComponentView(
                container_selector=webapp,
                key="web_application_container_00",
                description="Component View Test",
                exclude_elements=[
                    lambda w, e: e == w.person().user
                ]
            )

    if not use_context:
        w.apply_views(
            ComponentView(
                container_selector=lambda w: w.software_system().software_system.web_application,
                key="web_application_container_00",
                description="Component View Test",
                exclude_elements=[
                    lambda w, e: e == w.person().user
                ]
            )
        )

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

@pytest.mark.parametrize("use_context", [True, False])
def test_container_view_with_multiple_software_systems(use_context: bool) -> Optional[None]:
    with Workspace('workspace') as w:
        with SoftwareSystem("App1") as app1:
            Container("c1")
        with SoftwareSystem("App2") as app2:
            Container("c2")
        w.software_system().app1.c1 >> "uses" >> w.software_system().app2.c2

        if use_context:
            ContainerView(
                key="container_view_00",
                description="Container View Test",
                software_system_selector=app1,
            )

    if not use_context:
        w.apply_views(
            ContainerView(
                key="container_view_00",
                description="Container View Test",
                software_system_selector=lambda w: w.software_system().app1,
            ),
        )

    assert any(w.model.views.containerViews)
    assert len(w.model.views.containerViews) == 1

    app1 = w.software_system().app1
    app2 = w.software_system().app2
    c1 = app1.c1
    c2 = app2.c2

    element_ids =  list(map(lambda x: x.id, w.model.views.containerViews[0].elements))
    relationship_ids =  list(map(lambda x: x.id, w.model.views.containerViews[0].relationships))

    assert len(element_ids) == 2
    assert {
        c1.model.id,
        c2.model.id,
    }.issubset(set(element_ids))

    assert len(relationship_ids) == 1
    assert {
        c1.model.relationships[0].id,
    }.issubset(set(relationship_ids))