import pytest
from typing import Optional
from buildzr.dsl import (
    Workspace,
    With,
    Color,
    Group,
    Person,
    SoftwareSystem,
    Container,
    Component,
    SoftwareSystemInstance,
    ContainerInstance,
    SystemLandscapeView,
    SystemContextView,
    ContainerView,
    ComponentView,
    DeploymentEnvironment,
    DeploymentGroup,
    DeploymentNode,
    InfrastructureNode,
    DeploymentView,
    StyleElements,
    StyleRelationships,
)
from buildzr.dsl.explorer import Explorer

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
        w.apply_view(
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

    element_ids = [x.id for x in w.model.views.systemLandscapeViews[0].elements]
    relationship_ids = [x.id for x in w.model.views.systemLandscapeViews[0].relationships]

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
        w.apply_view(
            SystemContextView(
                software_system_selector=lambda w: w.software_system().business_app,
                key="ss_business_app",
                description="The business app",
            )
        )

    element_ids =  [x.id for x in w.model.views.systemContextViews[0].elements]
    relationship_ids =  [x.id for x in w.model.views.systemContextViews[0].relationships]

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
        w.apply_view(
            SystemContextView(
                software_system_selector=lambda w: w.software_system().business_app,
                key="ss_business_app",
                description="The business app",
                exclude_elements=[
                    lambda w, e: e == w.person().u,
                ]
            )
        )

    element_ids = [x.id for x in w.model.views.systemContextViews[0].elements]
    relationship_ids = [x.id for x in w.model.views.systemContextViews[0].relationships]

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
        w.apply_view(
            ContainerView(
                software_system_selector=lambda w: w.software_system().app,
                key="ss_business_app",
                description="The business app",
            )
        )

    element_ids = [x.id for x in w.model.views.containerViews[0].elements]
    relationship_ids = [x.id for x in w.model.views.containerViews[0].relationships]

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
        w.apply_view(
            ComponentView(
                container_selector=lambda w: w.software_system().software_system.web_application,
                key="web_application_container_00",
                description="Component View Test",
            )
        )

    element_ids = [x.id for x in w.model.views.componentViews[0].elements]
    relationship_ids = [x.id for x in w.model.views.componentViews[0].relationships]

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
        w.apply_view(
            ComponentView(
                container_selector=lambda w: w.software_system().software_system.web_application,
                key="web_application_container_00",
                description="Component View Test",
                exclude_elements=[
                    lambda w, e: e == w.person().user
                ]
            )
        )

    element_ids = [x.id for x in w.model.views.componentViews[0].elements]
    relationship_ids = [x.id for x in w.model.views.componentViews[0].relationships]

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
        w.apply_view(
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

    element_ids = [x.id for x in w.model.views.containerViews[0].elements]
    relationship_ids = [x.id for x in w.model.views.containerViews[0].relationships]

    assert len(element_ids) == 2
    assert {
        c1.model.id,
        c2.model.id,
    }.issubset(set(element_ids))

    assert len(relationship_ids) == 1
    assert {
        c1.model.relationships[0].id,
    }.issubset(set(relationship_ids))

def test_software_system_instances_carry_over_relationships() -> Optional[None]:

    with Workspace('w') as w:
        with SoftwareSystem('s1') as s1:
            api = Container('API')
            db = Container('Database')
        with SoftwareSystem('s2') as s2:
            api2 = Container('API2')
            db2 = Container('Database2')

        s2 >> "Uses" >> s1

        with DeploymentEnvironment('env') as env:
            with DeploymentNode('Server') as server:
                s1_instance = SoftwareSystemInstance(s1)
                s2_instance = SoftwareSystemInstance(s2)

    assert len(w.model.model.deploymentNodes) == 1
    assert w.model.model.deploymentNodes[0].environment == env.name
    assert len(w.model.model.deploymentNodes[0].softwareSystemInstances) == 2
    assert w.model.model.deploymentNodes[0].softwareSystemInstances[0].id == s1_instance.model.id
    assert w.model.model.deploymentNodes[0].softwareSystemInstances[1].id == s2_instance.model.id
    assert len(w.model.model.deploymentNodes[0].softwareSystemInstances[1].relationships) == 1
    assert w.model.model.deploymentNodes[0].softwareSystemInstances[1].relationships[0].id == s2_instance.model.relationships[0].id
    assert w.model.model.deploymentNodes[0].softwareSystemInstances[1].relationships[0].sourceId == s2_instance.model.id
    assert w.model.model.deploymentNodes[0].softwareSystemInstances[1].relationships[0].destinationId == s1_instance.model.id
    assert w.model.model.deploymentNodes[0].softwareSystemInstances[1].relationships[0].linkedRelationshipId == s2.model.relationships[0].id

def test_container_instances_carry_over_relationships() -> Optional[None]:
    with Workspace('w') as w:
        with SoftwareSystem('Software System') as s:
            api = Container('API')
            db = Container('Database')
            api >> db

        with DeploymentEnvironment('env') as env:
            with DeploymentNode('Server') as server:
                with DeploymentNode('Docker') as docker:
                    api_instance = ContainerInstance(api)
                    db_instance = ContainerInstance(db)

    assert len(w.model.model.deploymentNodes) == 1
    assert w.model.model.deploymentNodes[0].environment == env.name
    assert len(w.model.model.deploymentNodes[0].children) == 1
    assert w.model.model.deploymentNodes[0].name == 'Server'
    assert w.model.model.deploymentNodes[0].children[0].name == 'Docker'

    assert len(w.model.model.deploymentNodes[0].children[0].containerInstances) == 2
    assert w.model.model.deploymentNodes[0].children[0].containerInstances[0].id == api_instance.model.id
    assert w.model.model.deploymentNodes[0].children[0].containerInstances[1].id == db_instance.model.id
    assert w.model.model.deploymentNodes[0].children[0].containerInstances[0].relationships[0].id == api_instance.model.relationships[0].id
    assert w.model.model.deploymentNodes[0].children[0].containerInstances[0].relationships[0].sourceId == api_instance.model.id
    assert w.model.model.deploymentNodes[0].children[0].containerInstances[0].relationships[0].destinationId == db_instance.model.id
    assert w.model.model.deploymentNodes[0].children[0].containerInstances[0].relationships[0].linkedRelationshipId == api.model.relationships[0].id

def test_multiple_views() -> Optional[None]:

    with Workspace("w", scope='landscape', group_separator="/") as w:
        with Group("Company 1") as company1:
            with Group("Department 1"):
                a = SoftwareSystem("A")
            with Group("Department 2") as c1d2:
                b = SoftwareSystem("B")
        with Group("Company 2") as company2:
            with Group("Department 1"):
                c = SoftwareSystem("C")
            with Group("Department 2") as c2d2:
                d = SoftwareSystem("D")
        a >> b
        c >> d
        b >> c

        SystemLandscapeView(
            key='nested-groups',
            description="Nested Groups Sample"
        )

        SystemContextView(
            software_system_selector=b,
            key='nested-groups-context-0',
            description="Nested Groups Sample Context",
            include_elements=[c, d],
        )

        SystemContextView(
            software_system_selector=c,
            key='nested-groups-context-1',
            description="Nested Groups Sample Context",
            include_elements=[b, d],
        )

        StyleElements(
            on=[a, b],
            shape='Box',
        )

        StyleElements(
            on=[c, d],
            shape='RoundedBox',
        )

        StyleElements(
            on=[company1],
            stroke='yellow',
            border='dotted',
        )

        StyleElements(
            on=[c1d2, c2d2],
            color='green',
        )

    assert w.model.views.systemLandscapeViews is not None
    assert w.model.views.systemContextViews is not None

    assert len(w.model.views.systemLandscapeViews) == 1
    assert len(w.model.views.systemContextViews) == 2

    assert w.model.views.systemLandscapeViews[0].key == 'nested-groups'
    assert w.model.views.systemContextViews[0].key == 'nested-groups-context-0'
    assert w.model.views.systemContextViews[1].key == 'nested-groups-context-1'

def test_deployment_view_without_software_instance() -> Optional[None]:

    with Workspace('w') as w:

        with SoftwareSystem('Software System') as s:
            api = Container('API')
            db = Container('Database')
            api >> db

        with DeploymentEnvironment('env-without-software-instance') as env1:
            with DeploymentNode('Server') as server1:
                with DeploymentNode('Docker') as docker1:
                    api_instance_1 = ContainerInstance(api)
                    db_instance_1 = ContainerInstance(db)

        with DeploymentEnvironment("env-without-software-instance-2") as env2:
            with DeploymentNode('Server') as server2:
                with DeploymentNode('VM') as vm2:
                    with DeploymentNode('Docker') as docker2:
                        api_instance_2 = ContainerInstance(api)
                        db_instance_2 = ContainerInstance(db)
        # 0
        DeploymentView(
            environment=env1,
            key='deployment-view-without-software-instance-all',
            description="Deployment View without Software System Instance",
            software_system_selector=None,
        )

        # 1
        DeploymentView(
            environment=env1,
            key='deployment-view-without-software-instance-specific-software-system',
            description="Deployment View with Software System Instance",
            software_system_selector=s,
        )

        # 2
        DeploymentView(
            environment=env2,
            key='deployment-view-without-software-instance-2',
            description="Deployment View without Software System Instance 2",
            software_system_selector=None,
        )

        # 3
        DeploymentView(
            environment=env2,
            key='deployment-view-without-software-instance-2',
            description="Deployment View without Software System Instance 2",
            software_system_selector=s,
        )

    # Include all elements in the environment where there's no
    # `SoftwareSystemInstance` defined.
    assert w.model.views.deploymentViews[0].environment == env1.name
    assert w.model.views.deploymentViews[0].softwareSystemId is None
    assert len(w.model.views.deploymentViews[0].elements) == 4
    assert w.model.views.deploymentViews[0].elements[0].id == server1.model.id
    assert w.model.views.deploymentViews[0].elements[1].id == docker1.model.id
    assert w.model.views.deploymentViews[0].elements[2].id == api_instance_1.model.id
    assert w.model.views.deploymentViews[0].elements[3].id == db_instance_1.model.id

    # Include only a specific software system in the environment where
    # there's no `SoftwareSystemInstance` defined (only its
    # `ContainerInstance`s are defined).
    assert w.model.views.deploymentViews[1].key == 'deployment-view-without-software-instance-specific-software-system'
    assert w.model.views.deploymentViews[1].environment == env1.name
    assert w.model.views.deploymentViews[1].softwareSystemId == s.model.id
    assert len(w.model.views.deploymentViews[1].elements) == 4
    assert w.model.views.deploymentViews[1].elements[0].id == server1.model.id
    assert w.model.views.deploymentViews[1].elements[1].id == docker1.model.id
    assert w.model.views.deploymentViews[1].elements[2].id == api_instance_1.model.id
    assert w.model.views.deploymentViews[1].elements[3].id == db_instance_1.model.id

    assert w.model.views.deploymentViews[2].key == 'deployment-view-without-software-instance-2'
    assert w.model.views.deploymentViews[2].environment == env2.name
    assert w.model.views.deploymentViews[2].softwareSystemId is None
    assert len(w.model.views.deploymentViews[2].elements) == 5
    assert w.model.views.deploymentViews[2].elements[0].id == server2.model.id
    assert w.model.views.deploymentViews[2].elements[1].id == vm2.model.id
    assert w.model.views.deploymentViews[2].elements[2].id == docker2.model.id
    assert w.model.views.deploymentViews[2].elements[3].id == api_instance_2.model.id
    assert w.model.views.deploymentViews[2].elements[4].id == db_instance_2.model.id

    assert w.model.views.deploymentViews[3].key == 'deployment-view-without-software-instance-2'
    assert w.model.views.deploymentViews[3].environment == env2.name
    assert w.model.views.deploymentViews[3].softwareSystemId == s.model.id
    assert len(w.model.views.deploymentViews[3].elements) == 5
    assert w.model.views.deploymentViews[3].elements[0].id == server2.model.id
    assert w.model.views.deploymentViews[3].elements[1].id == vm2.model.id
    assert w.model.views.deploymentViews[3].elements[2].id == docker2.model.id
    assert w.model.views.deploymentViews[3].elements[3].id == api_instance_2.model.id
    assert w.model.views.deploymentViews[3].elements[4].id == db_instance_2.model.id

def test_deployment_view_with_software_instance() -> Optional[None]:

    with Workspace('w') as w:

        with SoftwareSystem('Software System') as s:
            api = Container('API')
            db = Container('Database')
            print("api id:", api.model.id)
            print("db id:", db.model.id)
            api >> db

        with DeploymentEnvironment('env-with-software-instance') as env1:
            with DeploymentNode('Server') as server1:
                s_instance_1 = SoftwareSystemInstance(s)
                print("server1 id:", server1.model.id)
                print("s_instance_1 id:", s_instance_1.model.id)
                with DeploymentNode('Docker') as docker1:
                    print("docker1 id:", docker1.model.id)
                    api_instance_1 = ContainerInstance(api)
                    db_instance_1 = ContainerInstance(db)

        with DeploymentEnvironment('env-with-software-instance-1') as env2:
            with DeploymentNode('Server') as server2:
                with DeploymentNode('Docker') as docker2:
                    s_instance_2 = SoftwareSystemInstance(s)
                    api_instance_2 = ContainerInstance(api)
                    db_instance_2 = ContainerInstance(db)

        with DeploymentEnvironment('env-with-software-instance-2') as env3:
            with DeploymentNode('Server') as server3:
                with DeploymentNode('VM') as vm3:
                    s_instance_3 = SoftwareSystemInstance(s)
                    with DeploymentNode('Docker') as docker4:
                        api_instance_3 = ContainerInstance(api)
                        db_instance_3 = ContainerInstance(db)

        # 0
        DeploymentView(
            environment=env1,
            key='deployment-view-with-software-instance',
            description="Deployment View with Software System Instance",
            software_system_selector=None,
        )

        # 1
        DeploymentView(
            environment=env1,
            key='deployment-view-with-software-instance',
            description="Deployment View with Software System Instance",
            software_system_selector=s,
        )

        # 2
        DeploymentView(
            environment=env2,
            key='deployment-view-with-software-instance-1',
            description="Deployment View with Software System Instance 1",
            software_system_selector=None,
        )

        # 3
        DeploymentView(
            environment=env2,
            key='deployment-view-with-software-instance-1',
            description="Deployment View with Software System Instance 1",
            software_system_selector=s,
        )

        # 4
        DeploymentView(
            environment=env3,
            key='deployment-view-with-software-instance-2',
            description="Deployment View with Software System Instance 2",
            software_system_selector=None,
        )

        # 5
        DeploymentView(
            environment=env3,
            key='deployment-view-with-software-instance-2',
            description="Deployment View with Software System Instance 2",
            software_system_selector=s,
        )

    # Include all elements in the environment where there's a
    # `SoftwareSystemInstance` defined at the root `DeploymentNode`.
    # There are also `ContainerInstance`s defined for the containers
    # in the second-level `DeploymentNode`, but these should be ignored,
    # along with the `DeploymentNode` that hosts them, since we're not
    # targeting a specific `SoftwareSystem`.
    assert w.model.views.deploymentViews[0].key == 'deployment-view-with-software-instance'
    assert w.model.views.deploymentViews[0].environment == env1.name
    assert w.model.views.deploymentViews[0].softwareSystemId is None
    assert len(w.model.views.deploymentViews[0].elements) == 2
    assert w.model.views.deploymentViews[0].elements[0].id == server1.model.id
    assert w.model.views.deploymentViews[0].elements[1].id == s_instance_1.model.id

    # Include only a specific software system in the environment where
    # there's a `SoftwareSystemInstance` defined at the root
    # `DeploymentNode`.
    #
    # There are also `ContainerInstance`s defined for the
    # containers in the second-level `DeploymentNode`. Since the specific
    # `SoftwareSystem` is specified, we should only include the
    # `ContainerInstance`s with the rest of the `InfrastructureNode`s that
    # has a relationship with the `ContainerInstance`s. But the
    # `SoftwareSystemInstance` itself should be excluded.
    assert w.model.views.deploymentViews[1].key == 'deployment-view-with-software-instance'
    assert w.model.views.deploymentViews[1].environment == env1.name
    assert w.model.views.deploymentViews[1].softwareSystemId == s.model.id
    assert len(w.model.views.deploymentViews[1].elements) == 4
    assert w.model.views.deploymentViews[1].elements[0].id == server1.model.id
    assert w.model.views.deploymentViews[1].elements[1].id == docker1.model.id
    assert w.model.views.deploymentViews[1].elements[2].id == api_instance_1.model.id
    assert w.model.views.deploymentViews[1].elements[3].id == db_instance_1.model.id

    # == Software system instance defined at the second-level DeploymentNode ==

    # Similar to the previous one, except that the `SoftwareSystemInstance`
    # is defined at the second-level where the `ContainerInstance`s are
    # defined.
    #
    # Since no `SoftwareSystem` is specified, we should just include the
    # `SoftwareSystemInstance`.
    assert w.model.views.deploymentViews[2].key == 'deployment-view-with-software-instance-1'
    assert w.model.views.deploymentViews[2].environment == env2.name
    assert w.model.views.deploymentViews[2].softwareSystemId is None
    assert len(w.model.views.deploymentViews[2].elements) == 3
    assert w.model.views.deploymentViews[2].elements[0].id == server2.model.id
    assert w.model.views.deploymentViews[2].elements[1].id == docker2.model.id
    assert w.model.views.deploymentViews[2].elements[2].id == s_instance_2.model.id

    # Since we're specifying a specific `SoftwareSystem`, we should
    # include the `ContainerInstance`s without including the
    # `SoftwareSystemInstance`.
    assert w.model.views.deploymentViews[3].key == 'deployment-view-with-software-instance-1'
    assert w.model.views.deploymentViews[3].environment == env2.name
    assert w.model.views.deploymentViews[3].softwareSystemId == s.model.id
    assert len(w.model.views.deploymentViews[3].elements) == 4
    assert w.model.views.deploymentViews[3].elements[0].id == server2.model.id
    assert w.model.views.deploymentViews[3].elements[1].id == docker2.model.id
    assert w.model.views.deploymentViews[3].elements[2].id == api_instance_2.model.id
    assert w.model.views.deploymentViews[3].elements[3].id == db_instance_2.model.id

    assert w.model.views.deploymentViews[4].key == 'deployment-view-with-software-instance-2'
    assert w.model.views.deploymentViews[4].environment == env3.name
    assert w.model.views.deploymentViews[4].softwareSystemId is None
    assert len(w.model.views.deploymentViews[4].elements) == 3
    assert w.model.views.deploymentViews[4].elements[0].id == server3.model.id
    assert w.model.views.deploymentViews[4].elements[1].id == vm3.model.id
    assert w.model.views.deploymentViews[4].elements[2].id == s_instance_3.model.id

    assert w.model.views.deploymentViews[5].key == 'deployment-view-with-software-instance-2'
    assert w.model.views.deploymentViews[5].environment == env3.name
    assert w.model.views.deploymentViews[5].softwareSystemId == s.model.id
    assert len(w.model.views.deploymentViews[5].elements) == 5
    assert w.model.views.deploymentViews[5].elements[0].id == server3.model.id
    assert w.model.views.deploymentViews[5].elements[1].id == vm3.model.id
    assert w.model.views.deploymentViews[5].elements[2].id == docker4.model.id
    assert w.model.views.deploymentViews[5].elements[3].id == api_instance_3.model.id
    assert w.model.views.deploymentViews[5].elements[4].id == db_instance_3.model.id

def test_deployment_view_with_deployment_groups() -> Optional[None]:

    with Workspace('w') as w:

        with SoftwareSystem('Software System') as s:
            api = Container('API')
            db = Container('Database')
            api >> db

        with DeploymentEnvironment('Production') as production:
            service_instance_1 = DeploymentGroup("Service instance 1")
            service_instance_2 = DeploymentGroup("Service instance 2")

            with DeploymentNode('Server 1') as server1:
                ci_api_1 = ContainerInstance(api, deployment_groups=[service_instance_1])
                with DeploymentNode('Database Server 1') as db_server1:
                    ci_db_1 = ContainerInstance(db, deployment_groups=[service_instance_1])

            with DeploymentNode('Server 2') as server2:
                ci_api_2 = ContainerInstance(api, deployment_groups=[service_instance_2])
                with DeploymentNode('Database Server 2') as db_server2:
                    ci_db_2 = ContainerInstance(db, deployment_groups=[service_instance_2])

        DeploymentView(
            environment=production,
            key='deployment',
        )

    assert w.model.views.deploymentViews is not None
    assert len(w.model.views.deploymentViews) == 1
    assert w.model.views.deploymentViews[0].key == 'deployment'
    assert w.model.views.deploymentViews[0].environment == production.name

    assert len(w.model.views.deploymentViews[0].elements) == 8
    assert w.model.views.deploymentViews[0].elements[0].id == server1.model.id
    assert w.model.views.deploymentViews[0].elements[1].id == ci_api_1.model.id
    assert w.model.views.deploymentViews[0].elements[2].id == db_server1.model.id
    assert w.model.views.deploymentViews[0].elements[3].id == ci_db_1.model.id
    assert w.model.views.deploymentViews[0].elements[4].id == server2.model.id
    assert w.model.views.deploymentViews[0].elements[5].id == ci_api_2.model.id
    assert w.model.views.deploymentViews[0].elements[6].id == db_server2.model.id
    assert w.model.views.deploymentViews[0].elements[7].id == ci_db_2.model.id

    assert w.model.model.deploymentNodes[0].containerInstances[0].id == ci_api_1.model.id
    assert w.model.model.deploymentNodes[0].containerInstances[0].deploymentGroups[0] == "Service instance 1"
    assert w.model.model.deploymentNodes[0].children[0].id == db_server1.model.id
    assert w.model.model.deploymentNodes[0].children[0].containerInstances[0].id == ci_db_1.model.id
    assert w.model.model.deploymentNodes[0].children[0].containerInstances[0].deploymentGroups[0] == "Service instance 1"

    assert w.model.model.deploymentNodes[1].containerInstances[0].id == ci_api_2.model.id
    assert w.model.model.deploymentNodes[1].containerInstances[0].deploymentGroups[0] == "Service instance 2"
    assert w.model.model.deploymentNodes[1].children[0].id == db_server2.model.id
    assert w.model.model.deploymentNodes[1].children[0].containerInstances[0].id == ci_db_2.model.id
    assert w.model.model.deploymentNodes[1].children[0].containerInstances[0].deploymentGroups[0] == "Service instance 2"

def test_deployment_view_with_infrastructure_nodes() -> Optional[None]:

    with Workspace('w') as w:

        with SoftwareSystem('Software System') as s:
            with Container('Web Application') as webapp:
                pass
            with Container('Database') as db:
                pass

            webapp >> "Reads from and writes to" >> db

        with DeploymentEnvironment('Live') as live:
            with DeploymentNode('Amazon Web Services') as aws:
                with DeploymentNode('ap-southeast-1') as region:
                    dns = InfrastructureNode(
                        'DNS Router',
                        technology="Route 53",
                        description="DNS Router for the web application",
                        tags={"dns", "router"}
                    )

                    lb = InfrastructureNode(
                        'Load Balancer',
                        technology="Elastic Load Balancer",
                        description="Load Balancer for the web application",
                        tags={"load-balancer"}
                    )

                    dns >> "Forwards requests to" >> lb

                    with DeploymentNode('Auto Scaling Group') as asg:
                        with DeploymentNode('Ubuntu Server') as ubuntu:
                            webapp_instance = ContainerInstance(webapp)
                            lb >> "Forwards requests to" >> webapp_instance

                    with DeploymentNode('Amazon RDS') as rds:
                        with DeploymentNode('MySQL') as mysql:
                            ContainerInstance(db)

        DeploymentView(
            environment=live,
            key='deployment-with-infrastructure-nodes',
            description="Deployment View with Infrastructure Nodes",
            software_system_selector=s,
            auto_layout='lr',
        )

    assert w.model.views.deploymentViews is not None
    assert len(w.model.views.deploymentViews) == 1
    assert w.model.views.deploymentViews[0].key == 'deployment-with-infrastructure-nodes'
    assert w.model.views.deploymentViews[0].environment == live.name
    assert w.model.views.deploymentViews[0].softwareSystemId == s.model.id

    assert len(webapp_instance.model.relationships) == 1

    assert len(w.model.views.deploymentViews[0].elements) == 10
    assert w.model.model.deploymentNodes[0].children[0].infrastructureNodes[0].id == dns.model.id
    assert w.model.model.deploymentNodes[0].children[0].infrastructureNodes[1].id == lb.model.id
    assert w.model.model.deploymentNodes[0].children[0].infrastructureNodes[0].relationships[0].destinationId == lb.model.id
    assert w.model.model.deploymentNodes[0].children[0].infrastructureNodes[1].relationships[0].destinationId == webapp_instance.model.id

    assert len(w.model.views.deploymentViews[0].relationships) == 3
    assert { x.id for x in w.model.views.deploymentViews[0].relationships } == {
        webapp_instance.model.relationships[0].id,
        dns.model.relationships[0].id,
        lb.model.relationships[0].id,
    }

    assert { lb.model.id, dns.model.id }.issubset({
        x.id for x in w.model.views.deploymentViews[0].elements
    })

def test_style_elements_on_dslelements() -> Optional[None]:

    """
    Apply elements by directly specifying the DSL elements (Person,
    SoftwareSystem, Container, Component) to apply the styling to.
    """

    with Workspace('w') as w:
        user = Person('u')
        with SoftwareSystem('s1') as s1:
            with Container('c1') as c1:
                comp1 = Component('comp1')
                comp2 = Component('comp2')
        with SoftwareSystem('s2') as s2:
            with Container('c2') as c2:
                comp3 = Component('comp3')
                comp4 = Component('comp4')

        user >> s1
        s1 >> s2

        SystemLandscapeView(
            key='landscape',
            description="Landscape View",
        )

        StyleElements(
            on=[user],
            shape='Person',
        )

        StyleElements(
            on=[s1, s2],
            shape='WebBrowser'
        )

        StyleElements(
            on=[comp1, comp4],
            shape='Circle',
        )

        StyleElements(
            on=[comp2, comp3],
            shape='Cylinder',
        )

        styles = w.model.views.configuration.styles

        # TODO: Avoid duplicating styles.
        assert len(styles.elements) == 7

        assert styles.elements[0].tag.startswith("buildzr-styleelements-")
        assert styles.elements[0].shape.name == "Person"
        assert styles.elements[0].tag in user.tags

        assert styles.elements[1].tag.startswith("buildzr-styleelements-")
        assert styles.elements[1].shape.name == "WebBrowser"
        assert styles.elements[1].tag in s1.tags

        assert styles.elements[2].tag.startswith("buildzr-styleelements-")
        assert styles.elements[2].tag == styles.elements[1].tag
        assert styles.elements[2].shape.name == "WebBrowser"
        assert styles.elements[2].tag in s2.tags

        assert styles.elements[3].tag.startswith("buildzr-styleelements-")
        assert styles.elements[3].shape.name == "Circle"
        assert styles.elements[4].tag == styles.elements[3].tag
        assert styles.elements[4].shape.name == "Circle"
        assert styles.elements[3].tag in comp1.tags
        assert styles.elements[4].tag in comp4.tags

        assert styles.elements[5].tag.startswith("buildzr-styleelements-")
        assert styles.elements[5].shape.name == "Cylinder"
        assert styles.elements[6].tag == styles.elements[5].tag
        assert styles.elements[6].shape.name == "Cylinder"
        assert styles.elements[5].tag in comp2.tags
        assert styles.elements[6].tag in comp3.tags

def test_style_elements_on_groups() -> Optional[None]:

    """
    Apply elements by specifying the groups to apply the styling to.
    """

    with Workspace('w', scope='landscape') as w:
        with Group("Company 1") as company1:
            with Group("Department 1") as c1d1:
                a = SoftwareSystem("A")
            with Group("Department 2") as c1d2:
                b = SoftwareSystem("B")
        with Group("Company 2") as company2:
            with Group("Department 1") as c2d1:
                c = SoftwareSystem("C")
            with Group("Department 2") as c2d2:
                d = SoftwareSystem("D")

        a >> b
        c >> d
        b >> c

        SystemLandscapeView(
            key='nested-groups',
            description="Nested Groups Sample"
        )

        StyleElements(
            on=[company1],
            shape='Box',
        )

        StyleElements(
            on=[company2],
            shape='RoundedBox',
        )

        StyleElements(
            on=[c1d1, c1d2],
            color='green',
        )

        StyleElements(
            on=[c2d1, c2d2],
            color='red',
        )

    styles = w.model.views.configuration.styles

    assert len(styles.elements) == 6

    assert styles.elements[0].tag == "Group:Company 1"
    assert styles.elements[0].shape.name == "Box"

    assert styles.elements[1].tag == "Group:Company 2"
    assert styles.elements[1].shape.name == "RoundedBox"

    assert styles.elements[2].tag == "Group:Company 1/Department 1"
    assert styles.elements[2].color == Color('green').to_hex()
    assert styles.elements[3].tag == "Group:Company 1/Department 2"
    assert styles.elements[3].color == Color('green').to_hex()

    assert styles.elements[4].tag == "Group:Company 2/Department 1"
    assert styles.elements[4].color == Color('red').to_hex()
    assert styles.elements[5].tag == "Group:Company 2/Department 2"
    assert styles.elements[5].color == Color('red').to_hex()

def test_style_elements_on_dsltypes() -> Optional[None]:

    """
    Apply elements by specifying the DSL types to apply the styling to.
    """

    with Workspace('w') as w:
        Person('u')
        with SoftwareSystem('s1') as s1:
            with Container('c1') as c1:
                comp1 = Component('comp1')
                comp2 = Component('comp2')
        with SoftwareSystem('s2') as s2:
            with Container('c2') as c2:
                comp3 = Component('comp3')
                comp4 = Component('comp4')

        SystemLandscapeView(
            key='landscape',
            description="Landscape View",
        )

        StyleElements(
            on=[Person],
            shape='Person',
        )

        StyleElements(
            on=[SoftwareSystem, Container],
            shape='Folder',
        )

        StyleElements(
            on=[Component],
            shape='Circle',
        )

    styles = w.model.views.configuration.styles

    assert len(styles.elements) == 4

    assert styles.elements[0].tag == 'Person'
    assert styles.elements[0].shape.name == "Person"

    assert styles.elements[1].tag == 'SoftwareSystem'
    assert styles.elements[1].shape.name == "Folder"
    assert styles.elements[2].tag == 'Container'
    assert styles.elements[2].shape.name == "Folder"

    assert styles.elements[3].tag == 'Component'
    assert styles.elements[3].shape.name == "Circle"

def test_style_elements_on_tags() -> Optional[None]:

    """
    Apply elements by specifying the tags to apply the styling to.
    """

    with Workspace('w') as w:
        Person('u')
        with SoftwareSystem('s1', tags={'blue'}) as s1:
            with Container('c1', tags={'red'}) as c1:
                comp1 = Component('comp1', tags={'blue', 'red'})
                comp2 = Component('comp2', tags={'blue'})
        with SoftwareSystem('s2', tags={'red'}) as s2:
            with Container('c2', tags={'green'}) as c2:
                comp3 = Component('comp3', tags={'red'})
                comp4 = Component('comp4', tags={'green', 'blue'})

        SystemLandscapeView(
            key='landscape',
            description="Landscape View",
        )

        StyleElements(
            on=['blue', 'red'],
            shape='Box',
        )

        styles = w.model.views.configuration.styles

        assert len(styles.elements) == 2

        assert styles.elements[0].tag == 'blue'
        assert styles.elements[0].shape.name == "Box"

        assert styles.elements[1].tag == 'red'
        assert styles.elements[1].shape.name == "Box"

def test_style_elements_on_callable() -> Optional[None]:

    """
    Apply elements by using a `Callable[[Workspace, Element], bool]` to filter
    the elements to apply the styling to.
    """

    with Workspace('w') as w:
        Person('u')
        with SoftwareSystem('s1') as s1:
            with Container('c1') as c1:
                comp1 = Component('comp1')
                comp2 = Component('comp2')
        with SoftwareSystem('s2') as s2:
            with Container('c2') as c2:
                comp3 = Component('comp3')
                comp4 = Component('comp4')

        SystemLandscapeView(
            key='landscape',
            description="Landscape View",
        )

        StyleElements(
            on=[
                lambda w, e: e == w.software_system().s1 or e == w.software_system().s2,
            ],
            shape='WebBrowser',
        )

    styles = w.model.views.configuration.styles

    assert len(styles.elements) == 1

    assert styles.elements[0].tag.startswith("buildzr-styleelements-")
    assert styles.elements[0].shape.name == "WebBrowser"

    assert styles.elements[0].tag in w.software_system().s1.tags
    assert styles.elements[0].tag in w.software_system().s2.tags

    assert styles.elements[0].tag not in w.software_system().s1.c1.tags
    assert styles.elements[0].tag not in w.software_system().s2.c2.tags
    assert styles.elements[0].tag not in w.software_system().s1.c1.comp1.tags
    assert styles.elements[0].tag not in w.software_system().s1.c1.comp2.tags
    assert styles.elements[0].tag not in w.software_system().s2.c2.comp3.tags
    assert styles.elements[0].tag not in w.software_system().s2.c2.comp4.tags

def test_style_elements_on_callable_without_workspace() -> Optional[None]:

    """
    Apply elements by using a `Callable[[Workspace, Element], bool]` to filter
    the elements to apply the styling to.
    """

    with Workspace('w') as w:
        Person('u')
        with SoftwareSystem('s1') as s1:
            with Container('c1') as c1:
                comp1 = Component('comp1')
                comp2 = Component('comp2')
        with SoftwareSystem('s2') as s2:
            with Container('c2') as c2:
                comp3 = Component('comp3')
                comp4 = Component('comp4')

        SystemLandscapeView(
            key='landscape',
            description="Landscape View",
        )

    with pytest.raises(ValueError):
        StyleElements(
            on=[
                lambda w, e: e == w.software_system().s1 or e == w.software_system().s2,
            ],
            shape='WebBrowser',
        )

def test_style_relationships_empty() -> Optional[None]:

    """
    Apply relationships styles to all relationships when no specific
    relationships are specified.
    """

    with Workspace('w') as w:
        Person('u')
        with SoftwareSystem('s1') as s1:
            with Container('c1') as c1:
                comp1 = Component('comp1')
                comp2 = Component('comp2')
        with SoftwareSystem('s2') as s2:
            with Container('c2') as c2:
                comp3 = Component('comp3')
                comp4 = Component('comp4')

        SystemLandscapeView(
            key='landscape',
            description="Landscape View",
        )

        StyleRelationships(
            color='red',
        )

    styles = w.model.views.configuration.styles

    assert len(styles.relationships) == 1

    print(styles.relationships)

    assert styles.relationships[0].tag == "Relationship"
    assert styles.relationships[0].color == Color('red').to_hex()

def test_style_relationships_on_specific_relations() -> Optional[None]:

    """
    Apply relationships styles to specific relationships.
    """

    with Workspace('w') as w:
        user = Person('u')
        with SoftwareSystem('s1') as s1:
            with Container('c1') as c1:
                comp1 = Component('comp1')
                comp2 = Component('comp2')
        with SoftwareSystem('s2') as s2:
            with Container('c2') as c2:
                comp3 = Component('comp3')
                comp4 = Component('comp4')

        r1 = user >> "Uses" >> s1
        r2 = comp1 >> "Uses" >> comp2
        r3 = comp3 >> "Uses" >> comp4

        SystemLandscapeView(
            key='landscape',
            description="Landscape View",
        )

        StyleRelationships(
            on=[r1],
            color='green',
            dashed=False,
        )

        StyleRelationships(
            on=[r2, r3],
            color='blue',
            dashed=True,
            thickness=5
        )

    styles = w.model.views.configuration.styles
    print(styles.relationships)

    assert len(styles.relationships) == 3

    assert styles.relationships[0].tag.startswith("buildzr-stylerelationships-")
    assert styles.relationships[0].color == Color('green').to_hex()
    assert styles.relationships[0].dashed is False
    assert styles.relationships[0].tag in user.model.relationships[0].tags.split(',')

    assert styles.relationships[1].tag.startswith("buildzr-stylerelationships-")
    assert styles.relationships[1].color == Color('blue').to_hex()
    assert styles.relationships[1].dashed is True
    assert styles.relationships[1].thickness == 5
    assert styles.relationships[1].tag in comp1.model.relationships[0].tags.split(',')
    assert styles.relationships[1].tag in comp3.model.relationships[0].tags.split(',')

def test_style_relationships_on_tags() -> Optional[None]:
    """
    Apply relationships styles to specific relationships using tags.
    """

    with Workspace('w') as w:
        user = Person('u')
        with SoftwareSystem('s1') as s1:
            with Container('c1') as c1:
                comp1 = Component('comp1')
                comp2 = Component('comp2')
        with SoftwareSystem('s2') as s2:
            with Container('c2') as c2:
                comp3 = Component('comp3')
                comp4 = Component('comp4')

        r1 = user >> "Uses" >> s1
        r2 = comp1 >> "Uses" >> comp2
        r3 = comp3 >> "Uses" >> comp4 | With(tags={'mytag'})

        SystemLandscapeView(
            key='landscape',
            description="Landscape View",
        )

        StyleRelationships(
            on=['mytag'],
            color='green',
            dashed=False,
        )

    styles = w.model.views.configuration.styles

    assert len(styles.relationships) == 1

    assert styles.relationships[0].tag == 'mytag'
    assert styles.relationships[0].color == Color('green').to_hex()
    assert styles.relationships[0].dashed is False
    assert styles.relationships[0].tag in r3.tags
    assert styles.relationships[0].tag in comp3.model.relationships[0].tags.split(',')
    assert styles.relationships[0].tag not in r1.tags
    assert styles.relationships[0].tag not in r2.tags
    assert styles.relationships[0].tag not in user.model.relationships[0].tags.split(',')
    assert styles.relationships[0].tag not in comp1.model.relationships[0].tags.split(',')

def test_style_relationships_on_groups() -> Optional[None]:
    """
    Apply relationships styles to specific relationships in the specified groups.
    """

    with Workspace('w') as w:
        user = Person('u')
        with Group('g1') as g1:
            with SoftwareSystem('s1') as s1:
                with Container('c1') as c1:
                    comp1 = Component('comp1')
                    comp2 = Component('comp2')
        with Group('g2') as g2:
            with SoftwareSystem('s2') as s2:
                with Container('c2') as c2:
                    comp3 = Component('comp3')
                    comp4 = Component('comp4')
                with Container('c22') as c22:
                    comp33 = Component('comp33')
                    comp44 = Component('comp44')
        with Group('g3') as g3:
            with SoftwareSystem('s3') as s3:
                with Container('c3') as c3:
                    comp5 = Component('comp5')
                    comp6 = Component('comp6')
            pass

        r1 = user  >> "Uses" >> s1    # Not styled because only s1 is part of the group g1.
        r2 = comp1 >> "Uses" >> comp2
        r3 = comp3 >> "Uses" >> comp4
        r4 = comp5 >> "Uses" >> comp6 # Not styled because g2 is not styled.

        r22 = comp33 >> "Uses" >> comp44

        SystemLandscapeView(
            key='landscape',
            description="Landscape View",
        )

        StyleRelationships(
            on=[g1],
            color='green',
        )

        StyleRelationships(
            on=[g2],
            color='blue',
        )

        styles = w.model.views.configuration.styles

        assert len(styles.relationships) == 2
        assert styles.relationships[0].tag.startswith("buildzr-stylerelationships-")
        assert styles.relationships[0].color == Color('green').to_hex()
        assert styles.relationships[0].tag in r2.tags
        assert styles.relationships[0].tag in comp1.model.relationships[0].tags.split(',')

        assert styles.relationships[1].tag.startswith("buildzr-stylerelationships-")
        assert styles.relationships[1].color == Color('blue').to_hex()
        assert styles.relationships[1].tag in r3.tags
        assert styles.relationships[1].tag in comp3.model.relationships[0].tags.split(',')
        assert styles.relationships[1].tag in r22.tags
        assert styles.relationships[1].tag in comp33.model.relationships[0].tags.split(',')

        # Should not be styled.
        assert styles.relationships[0].tag not in r1.tags
        assert styles.relationships[0].tag not in r4.tags
        assert styles.relationships[1].tag not in r1.tags
        assert styles.relationships[1].tag not in r4.tags
        assert styles.relationships[0].tag not in user.model.relationships[0].tags.split(',')
        assert styles.relationships[0].tag not in comp5.model.relationships[0].tags.split(',')
        assert styles.relationships[1].tag not in user.model.relationships[0].tags.split(',')
        assert styles.relationships[1].tag not in comp5.model.relationships[0].tags.split(',')

def test_style_relationships_on_callables() -> Optional[None]:

    """
    Apply relationships styles to specific relationships using callables.
    """

    with Workspace('w') as w:
        user = Person('u')
        with SoftwareSystem('s1') as s1:
            with Container('c1') as c1:
                comp1 = Component('comp1')
                comp2 = Component('comp2')
        with SoftwareSystem('s2') as s2:
            with Container('c2') as c2:
                comp3 = Component('comp3')
                comp4 = Component('comp4')

        user >> "Uses" >> s1
        comp1 >> "Uses" >> comp2
        comp3 >> "Uses" >> comp4

        SystemLandscapeView(
            key='landscape',
            description="Landscape View",
        )

        StyleRelationships(
            on=[
                lambda w, r: r.source == user,
            ],
            color='green',
            dashed=False,
        )

        StyleRelationships(
            on=[
                lambda w, r: r.source.type == Component and r.destination.type == Component,
            ],
            color='blue',
            dashed=True,
            thickness=5
        )

        assert len(w.model.views.configuration.styles.relationships) == 2

        styles = w.model.views.configuration.styles

        assert styles.relationships[0].tag.startswith("buildzr-stylerelationships-")
        assert styles.relationships[0].color == Color('green').to_hex()
        assert styles.relationships[0].dashed is False
        assert styles.relationships[0].tag in user.model.relationships[0].tags.split(',')

        assert styles.relationships[1].tag.startswith("buildzr-stylerelationships-")
        assert styles.relationships[1].color == Color('blue').to_hex()
        assert styles.relationships[1].dashed is True
        assert styles.relationships[1].thickness == 5
        assert styles.relationships[1].tag in comp1.model.relationships[0].tags.split(',')
        assert styles.relationships[1].tag in comp3.model.relationships[0].tags.split(',')
        assert styles.relationships[1].tag not in user.model.relationships[0].tags.split(',')

        assert styles.relationships[0].tag in [tag for r in user.relationships for tag in r.tags]
        assert styles.relationships[0].tag not in [tag for r in s1.relationships for tag in r.tags]
        assert styles.relationships[1].tag in [tag for r in comp1.relationships for tag in r.tags]
        assert styles.relationships[1].tag not in [tag for r in comp2.relationships for tag in r.tags]
        assert styles.relationships[1].tag in [tag for r in comp3.relationships for tag in r.tags]
        assert styles.relationships[1].tag not in [tag for r in comp4.relationships for tag in r.tags]