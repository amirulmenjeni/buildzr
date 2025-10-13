# Relationships
Relationships connect elements in your architecture model and describe how they interact and work together to bring value. Without relationships, your architecture diagrams aren't really helpful. With that in mind, let's dive into how we can establish and maintain a healthy relationship with `buildzr`.

## Basic Syntax

To define a relationship between two models, use the `>>` operator.

```python
from buildzr.dsl import Workspace, Person, SoftwareSystem

with Workspace('w') as w:

    user = Person('User')
    system = SoftwareSystem('System')

    # Simple relationship
    user >> system
```

## Adding Descriptions

To describe what kind of relationship exists between `user` and `system`, simply pass a string like so:

```python
from buildzr.dsl import Workspace, Person, SoftwareSystem

with Workspace('w') as w:

    user = Person('User')
    system = SoftwareSystem('System')

    user >> "Uses" >> system
```

## Technology/Protocol

If you need to add the technology detail, pass a tuple instead of a string. The first element of the tuple is the description, while the second is the technology.

```python
from buildzr.dsl import Workspace, SoftwareSystem, Container

with Workspace('w') as w:

    with SoftwareSystem('s') as s:
        api = Container('API')
        database = Container('Database')

    # Relationship with description and technology
    api >> ("Reads from and writes to", "JDBC/SSL") >> database
```

## Adding Tags and Properties to a Relationship

Like element models, you can also add tags and properties to relationships by piping (`|`) the relationship to a `With`:

```python
from buildzr.dsl import Workspace, SoftwareSystem, Container, With

with Workspace('w') as w:

    with SoftwareSystem('s') as s:
        api = Container('API')
        database = Container('Database')

    # Relationship with description and technology
    api >> ("Reads from and writes to", "JDBC/SSL") >> database | With(
        tags={'sensitive'},
        properties={
            'driver': 'mysql-connector-java-5.1.18-bin.jar',
        }
    )
```

## One-to-Many Relationships

It is also possible to define a one-to-many relationships by collecting the right-hand hand side of the `>>` in a list (`[ ... ]`):

```python
from buildzr.dsl import Workspace, Person, SoftwareSystem, With, desc

with Workspace('w') as w:
    user = Person('user')
    system_a = SoftwareSystem('a')
    system_b = SoftwareSystem('b')
    auth_system = SoftwareSystem('auth')

    user >> [
        desc("Reads from") >> system_a,
        desc("Writes to", "HTTPS") >> system_b | With(
            tags={'encrypted'},
        ),
        auth_system,
    ]
```

You can see that we've combined different ways to define a relationship for each relationship between `user` and `system_a`, `system_b`, and `auth_system`!

!!! note
    Use `desc` when describing relationships in a one-to-many relationships definition.
    This is required, unless you don't need to put a relationship description like with `auth_system` above!


## Bidirectional Relationships

Sometimes relationships go both ways. When system A talks to system B *and* system B talks back to system A, you've got a bidirectional relationship.

You can create relationships in both directions by defining each direction separately:

```python
from buildzr.dsl import Workspace, Person, SoftwareSystem, With, desc

with Workspace('w') as w:
    system_a = SoftwareSystem('a')
    system_b = SoftwareSystem('b')

    system_a >> "Calls" >> system_b

    system_b >> "Sends events to" >> system_a
```

!!! tip
    Just because you *can* make relationships bidirectional doesn't mean they are. Only add the reverse relationship if it actually exists in your system.

    For example, if there's a "data flow" from system A to system B, ask yourself (or your fellow architects): Is system A calling a procedure to system B to upload/ingest the data into system B? Or is system B running a query against system A? The latter relationship is not the same as the former!

## Implied Relationships

Sometimes you don't need to say the obvious. If your `frontend` container talks to someone else's `api` container, it's pretty clear that your system talks to their system too. These are implied relationships - connections that exist by logical necessity, not because you explicitly wrote them down.

```python
from buildzr.dsl import Workspace, Person, SoftwareSystem, Container

# ⚠️ Make sure to enable `implied_relationships` for the workspace!
with Workspace('w', implied_relationships=True) as w:
    user = Person('user')
    with SoftwareSystem('s') as s:
        app = Container('app')

    # This will also imply that `user >> s`.
    user >> app
```

If you run the code above and inspect the JSON output, you'll see that `user` has two relationships:

- The first one with `app`, which was explicitly created, and
- The second one with `s`, which was implied

!!! info "Why This Matters"
    Implied relationships save you from maintaining duplicate relationship definitions across different abstraction levels. Define the detailed container-to-container relationship once, and the system-to-system relationship is inferred automatically.

!!! info "Implied Relationships are Bidirectional"
    If we have software systems `a` and `b`, each with containers `ca` and `cb` respectively, the following holds:
    - `a.ca >> b` implies `a >> b`
    - `a >> b.cb` implies `a >> b`

## Legal Relationships

As you may know, not all relationships are legal.

`buildzr` helps you know if you're creating a legal relationship by using [Mypy](https://mypy-lang.org/), a static type checker for Python.

For example, if you try to create a relationship between a `Person` and an `DeploymentNode` (ew!), Mypy will complain:

```python
# norun
with Workspace('w') as w:
    user = Person('user')
    region = DeploymentNode('region')
    user >> region # Illegal: Mypy will complain!
```

Mypy complaints will read something like this:

```
No overload variant of "__rshift__" of "DslElementRelationOverrides" matches argument type "DeploymentNode".

Possible overload variants:
    def __rshift__(self, Union[Person, SoftwareSystem, Container, Component], /) -> _Relationship[Person, Union[Person, SoftwareSystem, Container, Component]]
    def __rshift__(self, Tuple[str, str], /) -> _UsesFrom[Person, Union[Person, SoftwareSystem, Container, Component]]
    def __rshift__(self, str, /) -> _UsesFrom[Person, Union[Person, SoftwareSystem, Container, Component]]
    def __rshift__(self, _RelationshipDescription[Union[Person, SoftwareSystem, Container, Component]], /) -> _UsesFrom[Person, Union[Person, SoftwareSystem, Container, Component]]
    def __rshift__(self, List[Union[Person, SoftwareSystem, Container, Component, _UsesFromLate[Union[Person, SoftwareSystem, Container, Component]]]], /) -> List[_Relationship[Person, Union[Person, SoftwareSystem, Container, Component]]]
```

The following table shows the allowed relationships between which element types, and from which source to which destination (taken from [Structurizr DSL Language Reference](https://docs.structurizr.com/dsl/language#relationship)):

|Source|Destination|
|---|---|
|`Person`|`Person`, `SoftwareSystem`, `Container`, `Component`|
|`SoftwareSystem`|`Person`, `SoftwareSystem`, `Container`, `Component`|
|`Container`|`Person`, `SoftwareSystem`, `Container`, `Component`|
|`Component`|`Person`, `SoftwareSystem`, `Container`, `Component`|
|`DeploymentNode`|`DeploymentNode`|
|`InfrastructureNode`|`DeploymentNode`, `InfrastructureNode`, `SoftwareSystemInstance`, `ContainerInstance`|
|`SoftwareSystemInstance`|`InfrastructureNode`|
|`ContainerInstance`|`InfrastructureNode`|

Note that the table shows that `SoftwareSystemInstance` and `ContainerInstance` can only have a relationship with `InfrastructureNode`. Behind the scene, though, when you create a relationship, say, between two `Container`s, `buildzr` will create the implied instance relationships between the instances of the two `ContainerInstance`s if they exists. For an example of this, see the [Deployment Group example](./models.md#deployment-group). (This is a different feature, not to be confused with from what's described in [Implied Relationships](#implied-relationships).)


## Next Steps

- [Models](models.md)
- [Views](views.md)