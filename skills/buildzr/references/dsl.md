# The buildzr DSL: reference and complete examples

Every block on this page is a complete model file. Save one as `workspaces/<name>.py` and run `buildzr build`: it builds without errors. All names come from `buildzr.dsl` unless the import says otherwise.

## Elements

| Write | Creates | Notes |
|---|---|---|
| `Person(name, description='', tags=set(), properties={})` | a person | |
| `SoftwareSystem(name, description='', tags=set(), properties={})` | a software system | `with system:` to add containers |
| `Container(name, description='', technology='', tags=set(), properties={})` | a container | only inside `with <SoftwareSystem>:`; `with container:` to add components |
| `Component(name, description='', technology='', tags=set(), properties={})` | a component | only inside `with <Container>:` |
| `with Group('Name'):` | a boundary around the elements created inside it | groups can be nested |
| `DeploymentEnvironment(name)` | a deployment environment | `with` it to add deployment nodes |
| `DeploymentNode(name, description='', technology='', tags=set(), instances='1')` | a server, cluster, region... | nest them; only inside an environment or another node |
| `InfrastructureNode(name, description='', technology='', tags=set(), properties={})` | a load balancer, DNS, firewall... | inside a deployment node |
| `ContainerInstance(container)`, `SoftwareSystemInstance(system)` | the container (system) running on the enclosing node | inside a deployment node |

- Every element is created inside the `with Workspace(...)` block, so it belongs to that workspace.
- Elements nest by `with`: `with SoftwareSystem('Shop') as shop:` then `Container(...)` inside it.
- Tags are a set of strings: `tags={'Database'}`. Every element also gets its type tags (`Element`, `Person`, `Software System`, `Container`, `Component`, ...).

## Relationships

| Write | Means |
|---|---|
| `a >> b` | a uses b, without a description |
| `a >> "Reads from" >> b` | with a description |
| `a >> ("Reads from", "SQL/TLS") >> b` | with a description and a technology |
| `a >> "Calls" >> b \| With(tags={'async'}, properties={'k': 'v'})` | with tags or properties |
| `a >> [desc("Reads", "SQL") >> b, desc("Writes") >> c, d]` | one source, several destinations; use `desc(...)` inside the list |
| `a.uses(b, "Reads from", "SQL", tags={'x'})` | the same as `>>`, as a method call |

- Allowed: between people, software systems, containers and components; `DeploymentNode >> DeploymentNode`; `InfrastructureNode >>` a node, an infrastructure node or an instance; an instance `>> InfrastructureNode`.
- A relationship between two containers is copied to their instances in every deployment environment automatically: do not write instance-to-instance relationships.
- `Workspace(name, implied_relationships=True)` also adds the relationships between the parents (container to container implies system to system). The viewer draws the rollup anyway, so leave it off unless the JSON must contain them.

## Views

| Write | Draws | Required arguments |
|---|---|---|
| `SystemLandscapeView(key, description)` | every person and software system | |
| `SystemContextView(software_system_selector=system, key=..., description=...)` | one system and what is around it | `software_system_selector` |
| `ContainerView(software_system_selector=system, key=..., description=...)` | the containers of one system | `software_system_selector` |
| `ComponentView(container_selector=container, key=..., description=...)` | the components of one container | `container_selector` |
| `DynamicView(key=..., description=..., scope=system_or_container_or_None, steps=[a >> "Does" >> b, ...])` | an ordered flow | `steps`, each one matching an existing relationship |
| `DeploymentView(environment=env, key=..., software_system_selector=system, description=...)` | what runs where in one environment: nodes as nested boxes, with the instances inside | `environment` (the `DeploymentEnvironment` object, not its name) |

- `key` is lower case with `-`: it becomes the link `/<workspace>/#/v/<key>`. Keys must be unique in a workspace.
- Optional on every view: `auto_layout='tb'` (`'bt'`, `'lr'`, `'rl'`), `title=`, `include_elements=[...]`, `exclude_elements=[...]`, `include_relationships=[...]`, `exclude_relationships=[...]`.
- A dynamic step names a relationship that already exists; its description can differ. A step without a technology matches the relationship whatever its technology. Only when two relationships with different technologies join the same two elements, add the technology to pick one (`webapp >> ("Charges the card through", "HTTPS") >> payments`); without it, a `ValueError` lists both. A step that matches no relationship raises `ValueError: No existing relationship found between ...`.

## Styles and themes

| Write | Does |
|---|---|
| `StyleElements(on=['Database'], shape='Cylinder')` | styles every element with the tag `Database` |
| `StyleElements(on=[user, admin], shape='Person', background='#08427b', color='#ffffff')` | styles these elements |
| `StyleElements(on=[Container], background='#438dd5')` | styles every element of a type: `Person`, `SoftwareSystem`, `Container`, `Component` |
| `StyleRelationships(on=['async'], dashed=True, color='#707070')` | styles relationships by tag; `on=None` styles all of them |
| `StyleElements(on=[api], **AWS.LAMBDA)` | an icon from a theme: `from buildzr.themes import AWS` (also `AZURE`, `GOOGLE_CLOUD`, `KUBERNETES`, `ORACLE_CLOUD`) |

- Element style arguments: `shape`, `icon`, `width`, `height`, `background`, `color`, `stroke`, `stroke_width`, `font_size`, `border` (`'solid'`, `'dashed'`, `'dotted'`), `opacity`.
- Shapes: `Box`, `RoundedBox`, `Circle`, `Ellipse`, `Hexagon`, `Cylinder`, `Component`, `Person`, `Robot`, `Folder`, `WebBrowser`, `MobileDevicePortrait`, `MobileDeviceLandscape`, `Pipe`.
- Relationship style arguments: `thickness`, `color`, `routing` (`'Direct'`, `'Orthogonal'`, `'Curved'`), `font_size`, `width`, `dashed`, `position`, `opacity`.
- Colours are `'#rrggbb'` strings or `(r, g, b)` tuples.

## Example 1: system context, container and component views

```python
from buildzr.dsl import (
    Workspace, Person, SoftwareSystem, Container, Component, Group, With, desc,
    SystemLandscapeView, SystemContextView, ContainerView, ComponentView,
    StyleElements, StyleRelationships,
)

with Workspace('Internet Banking', description='The internet banking system and its neighbours') as w:
    customer = Person('Customer', description='A customer of the bank')
    with Group('Big Bank plc'):
        staff = Person('Support Staff', description='Answers customer questions')
        mainframe = SoftwareSystem('Mainframe', description='Stores accounts and transactions', tags={'Existing'})
        email = SoftwareSystem('E-mail System', description='Sends e-mails', tags={'Existing'})
        with SoftwareSystem('Internet Banking', description='Lets customers view their accounts') as banking:
            web = Container('Web Application', description='Delivers the single-page app', technology='Java, Spring MVC')
            spa = Container('Single-Page App', description='Banking in the browser', technology='TypeScript, React')
            with Container('API Application', description='Banking over JSON/HTTPS', technology='Java, Spring Boot') as api:
                signin = Component('Sign In Controller', technology='Spring MVC Rest Controller')
                accounts = Component('Accounts Controller', technology='Spring MVC Rest Controller')
                security = Component('Security Component', technology='Spring Bean')
                facade = Component('Mainframe Facade', technology='Spring Bean')
            db = Container('Database', description='Stores users and sessions', technology='PostgreSQL', tags={'Database'})

    customer >> "Visits" >> web
    customer >> "Views accounts with" >> spa
    web >> "Delivers" >> spa
    spa >> [
        desc("Signs in through", "JSON/HTTPS") >> signin,
        desc("Reads accounts through", "JSON/HTTPS") >> accounts,
    ]
    signin >> "Uses" >> security
    accounts >> "Uses" >> facade
    security >> ("Reads from and writes to", "SQL/TLS") >> db
    facade >> ("Calls", "XML/HTTPS") >> mainframe
    api >> "Sends e-mails with" >> email | With(tags={'async'})
    email >> "Sends e-mails to" >> customer | With(tags={'async'})
    staff.uses(mainframe, "Looks up accounts in")

    SystemLandscapeView(key='landscape', description='Everything around the bank')
    SystemContextView(software_system_selector=banking, key='banking-context',
                      description='Internet Banking and its neighbours')
    ContainerView(software_system_selector=banking, key='banking-containers',
                  description='The containers of Internet Banking', auto_layout='lr')
    ComponentView(container_selector=api, key='api-components',
                  description='The components of the API Application')

    StyleElements(on=[customer, staff], shape='Person', background='#08427b', color='#ffffff')
    StyleElements(on=['Existing'], background='#999999', color='#ffffff')
    StyleElements(on=['Database'], shape='Cylinder')
    StyleElements(on=[Container], background='#438dd5', color='#ffffff')
    StyleRelationships(on=['async'], dashed=True)
```

## Example 2: a dynamic view

```python
from buildzr.dsl import (
    Workspace, Person, SoftwareSystem, Container, ContainerView, DynamicView, StyleElements,
)

with Workspace('Book Store') as w:
    customer = Person('Customer')
    with SoftwareSystem('Book Store') as store:
        webapp = Container('Web Application', technology='Python, Django')
        database = Container('Database', technology='PostgreSQL', tags={'Database'})
    payments = SoftwareSystem('Payment Provider')

    customer >> "Browses and buys books with" >> webapp
    webapp >> ("Reads from and writes to", "SQL") >> database
    webapp >> ("Takes payments through", "HTTPS") >> payments

    ContainerView(software_system_selector=store, key='store-containers', description='The containers of the store')
    DynamicView(
        key='checkout',
        description='A customer buys a book',
        scope=store,
        steps=[
            customer >> "Submits the order to" >> webapp,
            webapp >> "Charges the card through" >> payments,
            webapp >> "Saves the order in" >> database,
        ],
        auto_layout='lr',
    )

    StyleElements(on=[customer], shape='Person')
    StyleElements(on=['Database'], shape='Cylinder')
```

## Example 3: a deployment view

`buildzr build` builds both views. In the viewer, the deployment view draws AWS, eu-west-1, ECS Cluster and RDS as nested boxes, the instances inside them, and `×2` on the ECS Cluster. A deployment node holds something only when an instance or an infrastructure node is inside it: the view leaves out a node with nothing in it. Each deployment element gets an id under `deploy/<environment>/`, for example `deploy/production/aws/eu-west-1/ecs-cluster/api`; link to it with `#/v/production?sel=<id>`.

```python
from buildzr.dsl import (
    Workspace, Person, SoftwareSystem, Container,
    DeploymentEnvironment, DeploymentNode, InfrastructureNode, ContainerInstance,
    ContainerView, DeploymentView, StyleElements,
)
from buildzr.themes import AWS

with Workspace('Shop Deployment') as w:
    customer = Person('Customer')
    with SoftwareSystem('Shop') as shop:
        api = Container('API', technology='Python, FastAPI')
        db = Container('Database', technology='PostgreSQL', tags={'Database'})
    customer >> ("Buys from", "HTTPS") >> api
    api >> ("Reads from and writes to", "SQL") >> db

    with DeploymentEnvironment('Production') as production:
        with DeploymentNode('AWS', technology='Amazon Web Services'):
            with DeploymentNode('eu-west-1', technology='AWS region'):
                lb = InfrastructureNode('Load Balancer', technology='Elastic Load Balancer')
                with DeploymentNode('ECS Cluster', technology='Amazon ECS', instances='2'):
                    api_instance = ContainerInstance(api)
                with DeploymentNode('RDS', technology='Amazon RDS'):
                    ContainerInstance(db)
                lb >> ("Forwards requests to", "HTTPS") >> api_instance

    ContainerView(software_system_selector=shop, key='shop-containers', description='The containers of the shop')
    DeploymentView(environment=production, key='production', software_system_selector=shop,
                   description='The shop in production')

    StyleElements(on=[customer], shape='Person')
    StyleElements(on=['Database'], shape='Cylinder')
    StyleElements(on=[lb], **AWS.ELASTIC_LOAD_BALANCING)
```
