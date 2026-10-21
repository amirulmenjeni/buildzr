# Run Code smoke test

A page for `tests/docs/test_runcode_browser.py`, built with a copy of the docs. Not part of the docs.

## A shop

```python
from buildzr.dsl import Workspace, Person, SoftwareSystem, Container
# focus: shop/database

with Workspace('w') as w:
    user = Person('User')
    with SoftwareSystem('Shop') as shop:
        web = Container('Web')
        db = Container('Database')
    user >> 'uses' >> web
    web >> 'reads' >> db
```

## A fragment

```python
user = Person('User')
system = SoftwareSystem('System')
user >> 'uses' >> system
```

## A mistake

```python
from buildzr.dsl import Workspace, Person
# focus: user

with Workspace('w') as w:
    user = Person('User')
    user >> 'uses' >> sytem
```

## Two workspaces

```python
from buildzr.dsl import Workspace, SoftwareSystem

with Workspace('Shop') as shop:
    SoftwareSystem('Store')

with Workspace('Billing') as billing:
    SoftwareSystem('Ledger')
```

## Not runnable

```python
# no-run
import this_module_does_not_exist
```
