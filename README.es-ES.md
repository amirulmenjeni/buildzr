

# Structurizr para `buildzr` 🧱⚒️

`buildzr` es una herramienta de creación para [Structurizr](https://structurizr.com/) dirigida a programadores en Python. Le permite diseñar modelos y diagramas de Structurizr de manera declarativa o procedimental.

Si no está familiarizado con Structurizr, es tanto un estándar abierto (consulte el [esquema JSON de Structurizr](https://github.com/structurizr/json)) como un [conjunto de herramientas](https://docs.structurizr.com/usage) para crear diagramas de arquitectura de software como código. Structurizr basa su paradigma de modelado de arquitectura en el [modelo C4](https://c4model.com/), el lenguaje de modelado utilizado para describir arquitecturas de software y sus relaciones.

En Structurizr, primero se definen los modelos de arquitectura y sus relaciones. Luego, puede reutilizar esos modelos para presentar múltiples perspectivas, vistas e historias sobre su arquitectura.

`buildzr` potencia este flujo de trabajo con azúcar sintáctico pythonico y APIs intuitivas que hacen que el modelado como código sea más divertido y productivo.

## Instalación

```bash
pip install buildzr
```

## Ejemplo Rápido

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    SystemContextView,
    ContainerView,
    desc,
    Group,
    StyleElements,
)
from buildzr.themes import AWS

with Workspace('w') as w:

    # Define your models (architecture elements and their relationships).

    with Group("My Company") as my_company:
        u = Person('Web Application User')
        webapp = SoftwareSystem('Corporate Web App')
        with webapp:
            database = Container('database')
            api = Container('api')
            api >> ("Reads and writes data from/to", "http/api") >> database
    with Group("Microsoft") as microsoft:
        email_system = SoftwareSystem('Microsoft 365')

    u >> [
        desc("Reads and writes email using") >> email_system,
        desc("Create work order using") >> webapp,
    ]
    webapp >> "sends notification using" >> email_system

    # Define the views.

    SystemContextView(
        software_system_selector=webapp,
        key='web_app_system_context_00',
        description="Web App System Context",
        auto_layout='lr',
    )

    ContainerView(
        software_system_selector=webapp,
        key='web_app_container_view_00',
        auto_layout='lr',
        description="Web App Container View",
    )

    # Stylize the views, and apply AWS theme icons.

    StyleElements(on=[u], **AWS.USER)
    StyleElements(on=[api], **AWS.LAMBDA)
    StyleElements(on=[database], **AWS.RDS)

    # Export to JSON, PlantUML, or SVG.

    w.save()                                  # JSON to {workspace_name}.json

    # Requires `pip install buildzr[export-plantuml]`
    w.save(format='plantuml', path='output/') # PlantUML files
    w.save(format='svg', path='output/')      # SVG files
```

![Vista de sistema de software de ejemplo](./docs/images/quick_example/web_app_system_context_00.svg)
![Vista de contenedor de ejemplo](./docs/images/quick_example/web_app_container_view_00.svg)

## Primeros pasos

¿Listo para sumergirse? Consulte el [Tutorial de Inicio Rápido](https://buildzr.dev/getting-started/quick-start/) y las [Guías de Usuario](https://buildzr.dev/user-guide/core-concepts/).

## ¿Por qué usar `buildzr`?

✅ **Sintaxis pythonica intuitiva**: Utilice los administradores de contexto de Python (sentencias `with`) para crear estructuras anidadas que reflejen naturalmente la jerarquía de su arquitectura. Consulte el [example](#quick-example).

✅ **Creación programática**: Use las APIs DSL de `buildzr` para crear diagramas de arquitectura del modelo C4 de manera programática. ¡Ideal para automatización!

✅ **Estilos avanzados**: Aplique estilos a los elementos más allá de las simples etiquetas: diríjase por referencia directa, tipo, pertenencia a grupo o predicados personalizados para un control visual detallado. ¡Solo eche un vistazo a [Styles](https://buildzr.dev/user-guide/styles/)!

✅ **Temas de proveedores de nube**: Agregue iconos de AWS, Azure, Google Cloud, Kubernetes y Oracle Cloud a sus diagramas con constantes descubribles por el IDE. ¡Adiós a memorizar cadenas de etiquetas! Consulte [Themes](https://buildzr.dev/user-guide/themes/).

✅ **Seguridad de tipos**: Escriba diagramas de Structurizr con mayor seguridad utilizando extensos indicadores de tipo (type hints) y soporte para [Mypy](https://mypy-lang.org).

✅ **Cumple con estándares**: Se mantiene fiel a los estándares del [esquema JSON de Structurizr](https://github.com/structurizr/json). `buildzr` utiliza [datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator) para generar automáticamente la representación de bajo nivel del modelo de Workspace.

✅ **Cadena de herramientas completa**: Utiliza el conocido lenguaje de programación Python y su rico ecosistema de herramientas para escribir modelos y diagramas de arquitectura de software.


## Enlaces del Proyecto

- [GitHub Repository](https://github.com/amirulmenjeni/buildzr)
- [Issue Tracker](https://github.com/amirulmenjeni/buildzr/issues)
- [Roadmap](https://buildzr.dev/roadmap/)
- [Contributing Guide](https://buildzr.dev/contributing/)
