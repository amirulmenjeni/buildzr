import os
import json
import inspect
import pytest
from typing import Optional, Type
from types import TracebackType

from buildzr.encoders import JsonEncoder
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    Component,
    Group,
    Views,
    desc,
)


def test_context_manager_workspace() -> None:
    """Test the basic context manager functionality of the Workspace class."""
    with Workspace('w') as w:
        pass

    assert w.model.name == 'w'
    assert w.model.model is not None
    assert isinstance(w.model.model.people, list)
    assert isinstance(w.model.model.softwareSystems, list)


def test_context_manager_group() -> None:
    """Test the Group context manager in a Workspace."""
    with Workspace('w') as w:
        with Group('My Company') as g:
            u = Person('User')
            s = SoftwareSystem('System')

    assert u.model.group == 'My Company'
    assert s.model.group == 'My Company'
    assert u in w.children
    assert s in w.children
    assert u.parent == w
    assert s.parent == w


def test_context_manager_nested_groups() -> None:
    """Test the Group context manager with multiple groups."""
    with Workspace('w') as w:
        with Group('Group 1') as g1:
            s1 = SoftwareSystem('System 1')

        with Group('Group 2') as g2:
            s2 = SoftwareSystem('System 2')

    assert s1.model.group == 'Group 1'
    assert s2.model.group == 'Group 2'
    assert s1 in w.children
    assert s2 in w.children


def test_context_manager_software_system_container() -> None:
    """Test the Container creation method on SoftwareSystem."""
    with Workspace('w') as w:
        ss = SoftwareSystem('My System')
        c = ss.Container('My Container')

    assert c.parent == ss
    assert c in ss.children
    assert c.model.name == 'My Container'


def test_context_manager_relations() -> None:
    """Test relationships in context manager style."""
    with Workspace('w') as w:
        u = Person('User')
        s = SoftwareSystem('System')

        # Simple relationship
        u >> "Uses" >> s

    assert u.model.relationships is not None
    assert len(u.model.relationships) == 1
    assert u.model.relationships[0].sourceId == u.model.id
    assert u.model.relationships[0].destinationId == s.model.id
    assert u.model.relationships[0].description == "Uses"


def test_context_manager_multiple_relations() -> None:
    """Test multiple relationships in context manager style."""
    with Workspace('w') as w:
        u = Person('User')
        s1 = SoftwareSystem('System 1')
        s2 = SoftwareSystem('System 2')

        # Multiple relationships
        u >> [
            desc("Uses web interface of") >> s1,
            desc("Uses API of") >> s2
        ]

    assert u.model.relationships is not None
    assert len(u.model.relationships) == 2
    assert u.model.relationships[0].description == "Uses web interface of"
    assert u.model.relationships[1].description == "Uses API of"
    assert u.model.relationships[0].destinationId == s1.model.id
    assert u.model.relationships[1].destinationId == s2.model.id


def test_context_manager_nested_containers() -> None:
    """Test nested containers with the new Container method."""
    with Workspace('w') as w:
        ss = SoftwareSystem('System')
        web = ss.Container('Web Application')
        db = ss.Container('Database')

        api = web.Component('API Layer')
        ui = web.Component('UI Layer')

        # Define relationships between components
        api >> "Reads and writes data from/to" >> db

    assert web.parent == ss
    assert db.parent == ss
    assert api.parent == web
    assert ui.parent == web
    assert api.model.relationships is not None
    assert len(api.model.relationships) == 1
    assert api.model.relationships[0].description == "Reads and writes data from/to"
    assert api.model.relationships[0].destinationId == db.model.id


def test_context_manager_views() -> None:
    """Test the Views context manager."""
    with Workspace('w') as w:
        u = Person('User')
        ss = SoftwareSystem('System')
        db = ss.Container('Database')

        u >> "Uses" >> ss

        with Views() as views:
            views.SystemContextView(
                ss,
                key='system_context_view',
                description='System Context View',
                auto_layout='lr'
            )

            views.ContainerView(
                ss,
                key='container_view',
                description='Container View',
                auto_layout='lr'
            )

    assert w.model.views is not None
    assert w.model.views.systemContextViews is not None
    assert len(w.model.views.systemContextViews) == 1
    assert w.model.views.containerViews is not None
    assert len(w.model.views.containerViews) == 1
    assert w.model.views.containerViews[0].key == 'container_view'


def test_context_manager_excluding_elements() -> None:
    """Test excluding elements from views."""
    with Workspace('w') as w:
        u = Person('User')
        ss = SoftwareSystem('System')

        u >> "Uses" >> ss

        with Views() as views:
            views.SystemContextView(
                ss,
                key='system_context_view',
                description='System Context View',
                auto_layout='lr',
                exclude_elements=[u]
            )

    # View is created successfully with excluded elements
    assert w.model.views is not None
    assert w.model.views.systemContextViews is not None
    assert len(w.model.views.systemContextViews) == 1


def test_complex_context_manager_architecture() -> None:
    """Test a complete architecture using the context manager style."""
    with Workspace('Banking System') as w:
        with Group('Customers') as g:
            customer = Person('Banking Customer')

        with Group('Banking System') as g:
            internet_banking = SoftwareSystem('Internet Banking System')
            mainframe = SoftwareSystem('Mainframe Banking System')

            web_app = internet_banking.Container('Web Application')
            mobile_app = internet_banking.Container('Mobile App')
            database = internet_banking.Container('Database')

            # Container relationships
            web_app >> "Reads from and writes to" >> database
            mobile_app >> "Reads from and writes to" >> database

        # System relationships
        customer >> [
            desc("Views account information using") >> internet_banking,
            desc("Transfers money using") >> internet_banking
        ]

        internet_banking >> "Gets account information from" >> mainframe

        with Views() as views:
            views.SystemContextView(
                internet_banking,
                key='internet_banking_context',
                description='Internet Banking System Context',
                auto_layout='tb'
            )

            views.ContainerView(
                internet_banking,
                key='internet_banking_containers',
                description='Internet Banking System Containers',
                auto_layout='tb'
            )

    # Verify the structure was created correctly
    assert customer in w.children
    assert internet_banking in w.children
    assert mainframe in w.children
    assert web_app in internet_banking.children
    assert mobile_app in internet_banking.children
    assert database in internet_banking.children

    # Verify relationships
    assert len(customer.model.relationships) == 2
    assert internet_banking.model.relationships is not None
    assert len(internet_banking.model.relationships) == 1
    assert web_app.model.relationships is not None
    assert len(web_app.model.relationships) == 1
    assert mobile_app.model.relationships is not None
    assert len(mobile_app.model.relationships) == 1

    # Verify views
    assert w.model.views is not None
    assert w.model.views.systemContextViews is not None
    assert len(w.model.views.systemContextViews) == 1
    assert w.model.views.containerViews is not None
    assert len(w.model.views.containerViews) == 1


def test_json_output() -> None:
    """Test outputting the context manager-based architecture to JSON."""
    output_path = "context_test.json"

    with Workspace('w') as w:
        with Group('My Company') as g:
            u = Person('Web Application User')
            webapp = SoftwareSystem('Corporate Web App')
            db = webapp.Container('database')
            api = webapp.Container('api')

            api >> "Reads and writes data from/to" >> db

        with Group('Microsoft') as g:
            email_system = SoftwareSystem('Microsoft 365')

        u >> [
            desc("Reads and writes email using") >> email_system,
            desc("Create work order using") >> webapp
        ]

        with Views() as view:
            view.SystemContextView(
                webapp,
                key='web_app_system_context_00',
                description='Web App System Context',
                auto_layout='lr',
                exclude_elements=[u]
            )

            view.ContainerView(
                webapp,
                key='web_app_container_view_00',
                auto_layout='lr',
                description='Web App Container View'
            )

    # Write to JSON file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(w.model, f, ensure_ascii=False, indent=4, cls=JsonEncoder)

    # Verify file was created
    assert os.path.exists(output_path)

    # Clean up
    os.remove(output_path)


def test_compatibility_with_old_syntax() -> None:
    """Test that the context manager syntax is compatible with the old fluent syntax."""

    # Create with context manager syntax
    with Workspace('w') as w_context:
        u1 = Person('User 1')
        s1 = SoftwareSystem('System 1')
        u1 >> "Uses" >> s1

    # Create with fluent syntax
    w_fluent = Workspace('w')\
        .contains(
            Person('User 1'),
            SoftwareSystem('System 1')
        )\
        .where(lambda w: [
            w.person().user_1 >> "Uses" >> w.software_system().system_1
        ])\
        .get_workspace()

    # Compare core structure
    assert w_context.model.name == w_fluent.model.name

    # Verify both workspaces have the expected elements by name
    context_person_names = {p.model.name for p in w_context.children if isinstance(p, Person)}
    fluent_person_names = {p.model.name for p in w_fluent.children if isinstance(p, Person)}
    assert context_person_names == fluent_person_names

    context_system_names = {s.model.name for s in w_context.children if isinstance(s, SoftwareSystem)}
    fluent_system_names = {s.model.name for s in w_fluent.children if isinstance(s, SoftwareSystem)}
    assert context_system_names == fluent_system_names

    # Compare relationships
    context_persons = [p for p in w_context.children if isinstance(p, Person) and p.model.name == 'User 1']
    fluent_persons = [p for p in w_fluent.children if isinstance(p, Person) and p.model.name == 'User 1']

    assert len(context_persons[0].model.relationships) == len(fluent_persons[0].model.relationships)
    assert context_persons[0].model.relationships[0].description == fluent_persons[0].model.relationships[0].description