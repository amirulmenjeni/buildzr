from typing import Optional
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Component,
    SystemContextView,
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
            )\
            .where(lambda u, email_system, business_app, _git_repo: [
                u >> "Uses" >> business_app,
                business_app >> "Notifies users using" >> email_system,
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