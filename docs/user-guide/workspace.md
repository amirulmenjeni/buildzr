# Workspace

## Configurations

- Name
- Implied Relationships
- Scope

## Hierarchical Structure

Use context managers to create nested structures:

```python
with Workspace('w') as w:
    # Software System level
    ecommerce = SoftwareSystem('E-Commerce')

    with ecommerce:
        # Container level
        api = Container('API')

        with api:
            # Component level
            auth = Component('Auth Service')
            payment = Component('Payment Service')
```

## Groups

Organize related elements into named groups.

```python
with Group("Internal Systems"):
    crm = SoftwareSystem('CRM')
    erp = SoftwareSystem('ERP')

with Group("External Systems"):
    payment = SoftwareSystem('Payment Gateway')
    email = SoftwareSystem('Email Service')
```

Groups can be nested too.

```python
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
```