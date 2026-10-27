# Structurizr compatibility

This page tracks which [Structurizr DSL](https://docs.structurizr.com/dsl/language) features the buildzr Python DSL supports today.

!!! note "Compatibility is not the roadmap"
    A feature marked ❌ or 🟡 here is not necessarily planned, and its position on this page says nothing about priority. For what we are working on and what comes next, see the [Roadmap](https://buildzr.dev/roadmap/).

> **Note**: buildzr uses a Pythonic DSL approach rather than the text-based Structurizr DSL. Features marked as ✅ have Python equivalents, while ❌ indicates no current support. Some features have partial support (🟡) with model-level definitions but no DSL wrapper.

## Core Language Constructs

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Workspace](https://docs.structurizr.com/dsl/language#workspace) | ✅ | Top-level construct and wrapper for model and views |
| [Model](https://docs.structurizr.com/dsl/language#model) | ✅ | Container for architecture elements and relationships |
| [Configuration](https://docs.structurizr.com/dsl/language#configuration) | ✅ | Workspace-level configuration settings |
| [Workspace Extension](https://docs.structurizr.com/dsl/language#extends) | ✅ | Extend existing workspaces via file or URL |
| [Visibility](https://docs.structurizr.com/dsl/language#visibility) | ❌ | Control workspace access level (private/public) |

## Model Elements

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Person](https://docs.structurizr.com/dsl/language#person) | ✅ | Represents users, actors, roles, or personas. Supports name, description, tags, properties |
| [Software System](https://docs.structurizr.com/dsl/language#softwaresystem) | ✅ | Represents a software system. Can contain containers. Supports `labeled()` for aliases |
| [Container](https://docs.structurizr.com/dsl/language#container) | ✅ | Deployable/runnable unit. Supports name, description, technology, tags, properties |
| [Component](https://docs.structurizr.com/dsl/language#component) | ✅ | Modular part of a container. Leaf element with no children |
| [Group](https://docs.structurizr.com/dsl/language#group) | ✅ | Named grouping with configurable separator (default `/`). Supports hierarchical nesting |
| [Element](https://docs.structurizr.com/dsl/language#element) | ✅ | Custom element type outside the standard C4 hierarchy. Supports name, metadata, description, tags, properties. The web viewer draws it in the views that list it |

## Deployment Model Elements

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Deployment Environment](https://docs.structurizr.com/dsl/language#deploymentenvironment) | ✅ | Named environments (e.g., "Development", "Live"). Context manager support |
| [Deployment Node](https://docs.structurizr.com/dsl/language#deploymentnode) | ✅ | Hierarchical nodes. Supports instance counts/ranges (e.g., "1..N", "3") |
| [Deployment Group](https://docs.structurizr.com/dsl/language#deploymentgroup) | ✅ | Groups deployment instances for relationship filtering |
| [Infrastructure Node](https://docs.structurizr.com/dsl/language#infrastructurenode) | ✅ | Load balancers, firewalls, DNS, etc. Supports name, description, technology, tags |
| [Software System Instance](https://docs.structurizr.com/dsl/language#softwaresysteminstance) | ✅ | Deployed instance of a software system. Supports deployment groups |
| [Container Instance](https://docs.structurizr.com/dsl/language#containerinstance) | ✅ | Deployed instance of a container. Supports deployment groups |
| [Health Check](https://docs.structurizr.com/dsl/language#healthcheck) | 🟡 | Model support (HttpHealthCheck) exists but no DSL wrapper |

## Relationships

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Relationship](https://docs.structurizr.com/dsl/language#relationship) | ✅ | Multiple syntax options: `>>` operator, `desc()` helper, `.uses()` method |
| [Implied Relationships](https://docs.structurizr.com/dsl/language#impliedrelationships) | ✅ | Automatic parent-level relationship creation. Enable via `implied_relationships=True` |
| Relationship Description | ✅ | Via `source >> "Uses" >> dest` or `desc("Uses")` |
| Relationship Technology | ✅ | Via `source >> ("Uses", "HTTP") >> dest` or `desc("Uses", "HTTP")` |
| Relationship Tags | ✅ | Via `With(tags={"tag1"})` modifier |
| Relationship Properties | ✅ | Via `With(properties={"key": "value"})` modifier |
| Relationship URL | ✅ | Via `With(url="...")` modifier |
| "this" keyword | N/A | Not needed - reference element variables directly (e.g., `system >> "calls" >> system`) |

## Views

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [System Landscape View](https://docs.structurizr.com/dsl/language#systemlandscapeview) | ✅ | Shows all Person and SoftwareSystem elements. Supports include/exclude filters |
| [System Context View](https://docs.structurizr.com/dsl/language#systemcontextview) | ✅ | System with direct relationships. Lambda selector support for dynamic selection |
| [Container View](https://docs.structurizr.com/dsl/language#containerview) | ✅ | Containers of a software system. Shows related elements automatically |
| [Component View](https://docs.structurizr.com/dsl/language#componentview) | ✅ | Components of a container. Shows related elements automatically |
| [Deployment View](https://docs.structurizr.com/dsl/language#deploymentview) | ✅ | Nodes and instances per environment. Respects deployment groups |
| [Dynamic View](https://docs.structurizr.com/dsl/language#dynamicview) | ✅ | Ordered interaction sequences. Supports description override, technology selector |
| [Filtered View](https://docs.structurizr.com/dsl/language#filteredview) | 🟡 | Model exists but no DSL wrapper. Filters views by tags |
| [Custom View](https://docs.structurizr.com/dsl/language#customview) | ✅ | Displays custom elements (Element type). Supports include/exclude filters, auto-layout. The web viewer draws it |
| [Image View](https://docs.structurizr.com/dsl/language#image) | 🟡 | Model exists but no DSL wrapper. PlantUML/Mermaid/Kroki integration |

## View Operations

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| include_elements | ✅ | Add elements via DslElement, callables, element types, or strings |
| exclude_elements | ✅ | Remove elements using same selector types as include |
| include_relationships | ✅ | Add relationships via DslRelationship or callable predicates |
| exclude_relationships | ✅ | Remove relationships using callable predicates |
| [Animation](https://docs.structurizr.com/dsl/language#animation) | 🟡 | Model has AnimationStep but no DSL support. Step-by-step reveal |
| title | ✅ | Optional view title |
| properties | ✅ | Arbitrary key-value metadata on views |

## Styling and Theming

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Styles](https://docs.structurizr.com/dsl/language#styles) | ✅ | Visual styling for elements and relationships |
| [Element Style](https://docs.structurizr.com/dsl/language#element) | ✅ | Style by DslElement, Group, callable, element type, or tag string |
| [Relationship Style](https://docs.structurizr.com/dsl/language#relationship-1) | ✅ | Style by DslRelationship, Group, callable, or tag string |
| [Theme](https://docs.structurizr.com/dsl/language#theme) | 🟡 | `Workspace.apply_theme`; the viewer applies the [themes buildzr ships](user-guide/themes.md#using-a-theme), with their icons [fetched at build time](user-guide/themes.md#theme-icons-at-build-time) from one pinned commit, and does not download others |
| [Branding](https://docs.structurizr.com/dsl/language#branding) | ✅ | `Workspace.apply_branding`; the viewer shows the logo and sets the diagrams in the font, but does not load a font URL ([Branding](user-guide/themes.md#branding)) |
| [Terminology](https://docs.structurizr.com/dsl/language#terminology) | 🟡 | Model supports custom type names but no DSL wrapper |

### Element Style Properties

| Property | Supported | Notes |
|----------|-----------|-------|
| shape | ✅ | Box, RoundedBox, Circle, Ellipse, Hexagon, Cylinder, Pipe, Person, Robot, Folder, WebBrowser, MobileDevicePortrait, MobileDeviceLandscape, Component |
| icon | ✅ | Base64 data URI |
| width | ✅ | In pixels |
| height | ✅ | In pixels |
| background | ✅ | Hex (#RGB, #RRGGBB), rgb(r,g,b), named colors, or tuples |
| color | ✅ | Text/foreground color |
| stroke | ✅ | Border color |
| stroke_width | ✅ | Border thickness |
| font_size | ✅ | Text size |
| border | ✅ | solid, dashed, dotted |
| opacity | ✅ | 0-100 |
| metadata | ✅ | Show element metadata |
| description | ✅ | Show element description |

### Relationship Style Properties

| Property | Supported | Notes |
|----------|-----------|-------|
| thickness | ✅ | Line width |
| color | ✅ | Line color |
| routing | ✅ | Direct, Orthogonal, Curved |
| font_size | ✅ | Label text size |
| width | ✅ | Annotation width |
| dashed | ✅ | Boolean |
| position | ✅ | 0-100 along line |
| opacity | ✅ | 0-100 |

### Color Support

| Format | Example |
|--------|---------|
| Named colors | black, white, red, green, blue, yellow, cyan, magenta, gray, orange, purple, pink, brown, lime, navy, teal, olive, maroon, silver, gold |
| Hex | `#RRGGBB` or `#RGB` |
| RGB | `rgb(r, g, b)` |
| Tuple | `(r, g, b)` |

## Advanced Features

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Auto Layout](https://docs.structurizr.com/dsl/language#autolayout) | ✅ | Directions: tb, bt, lr, rl. Configurable rank/node separation. Graphviz or Dagre |
| [Properties](https://docs.structurizr.com/dsl/language#properties) | ✅ | Arbitrary key-value metadata on all elements and relationships |
| [Tags](https://docs.structurizr.com/dsl/language#tags) | ✅ | Via constructor or `add_tags()`. Automatic type tags (e.g., "Element", "Person") |
| [URL](https://docs.structurizr.com/dsl/language#url) | ✅ | On relationships via `With(url="...")`. Elements support via properties |
| [Perspectives](https://docs.structurizr.com/dsl/language#perspectives) | 🟡 | Model support exists but no DSL wrapper |
| [Archetypes](https://docs.structurizr.com/dsl/archetypes) | ❌ | User-defined element types with preset descriptions, tags, properties |
| [!extend / !element](https://docs.structurizr.com/dsl/language#extend) | ❌ | Modify existing elements via identifiers or expressions |
| [!relationship / !relationships](https://docs.structurizr.com/dsl/language#relationships) | ❌ | Find and extend relationships |

### Auto Layout Options

| Option | Default | Description |
|--------|---------|-------------|
| direction | `tb` | Layout direction: `tb` (top-bottom), `bt` (bottom-top), `lr` (left-right), `rl` (right-left) |
| rank_separation | 300 | Distance between ranks (node levels) |
| node_separation | 300 | Distance between nodes on same rank |
| implementation | Graphviz | Graphviz (default) or Dagre |

## DSL Language Features

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Identifiers](https://docs.structurizr.com/dsl/identifiers) | ✅ | Auto-generated IDs. Access via `workspace.person().name` or `labeled()` aliases |
| [Expressions](https://docs.structurizr.com/dsl/expressions) | ✅ | Python Expression API with predicates for filtering elements/relationships |
| [!identifiers](https://docs.structurizr.com/dsl/language#identifiers) | ❌ | Switch between hierarchical and flat identifier scoping |
| [!include](https://docs.structurizr.com/dsl/language#include) | ❌ | Import external DSL files. Use Python imports instead |
| [!constant (!const)](https://docs.structurizr.com/dsl/language#constant) | ❌ | Define reusable constants. Use Python variables instead |
| [!ref](https://docs.structurizr.com/dsl/language#ref) | ❌ | Reference elements from extended workspaces |
| [!docs](https://docs.structurizr.com/dsl/language#docs) | ❌ | Attach Markdown/AsciiDoc documentation |
| [!adrs](https://docs.structurizr.com/dsl/language#adrs) | ❌ | Add architectural decision records |
| [!script](https://docs.structurizr.com/dsl/language#script) | N/A | Native Python - use Python directly |
| [!plugin](https://docs.structurizr.com/dsl/language#plugin) | N/A | Native Python - extend with Python code |

### Expression API

The Expression API provides filtering capabilities similar to Structurizr expressions:

| Property | Description |
|----------|-------------|
| `e.id` | Element ID |
| `e.type` | Element type (Person, SoftwareSystem, etc.) |
| `e.tags` | Element tags |
| `e.name` | Element name |
| `e.technology` | Element technology |
| `e.metadata` | Element metadata (for custom elements) |
| `e.parent` | Parent element |
| `e.children` | Child elements |
| `e.sources` | Elements with relationships pointing to this element |
| `e.destinations` | Elements this element has relationships to |
| `e.properties` | Element properties dict |
| `e.group` | Element's group |
| `e.environment` | Deployment environment (for deployment elements) |

## Workspace Features

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Description](https://docs.structurizr.com/dsl/language#description) | ✅ | Set descriptions on elements and views |
| [Technology](https://docs.structurizr.com/dsl/language#technology) | ✅ | Specify technology for containers, components, infrastructure nodes |
| [Scope](https://docs.structurizr.com/dsl/language#scope) | ✅ | `'landscape'`, `'software_system'`, or `None` |
| Group Separator | ✅ | Configurable separator for hierarchical groups (default `/`) |
| [Users](https://docs.structurizr.com/dsl/language#users) | ❌ | Define workspace read/write permissions |

## Python-Specific Features

These features leverage Python's native capabilities as alternatives to Structurizr DSL constructs:

| Feature | Description |
|---------|-------------|
| Dynamic Attribute Access | Access elements via `workspace.software_system().system_name` |
| Lambda Selectors | Use callables for dynamic element/relationship selection in views |
| Context Managers | Use `with` statements for scoped element creation (Group, DeploymentEnvironment) |
| Type Hints | Full type annotation support for IDE integration |
| Native Imports | Use Python imports instead of `!include` |
| Variables | Use Python variables instead of `!const` |
| Explorer API | `walk_elements()` and `walk_relationships()` for traversal |

## Utility APIs

| Feature | Location | Description |
|---------|----------|-------------|
| Explorer | `buildzr.dsl.explorer` | Depth-first element and relationship traversal |
| Expression | `buildzr.dsl.expression` | Filtering predicates for views |
| Color | `buildzr.dsl.color` | Named colors, hex, rgb, and tuple support |
| Relations | `buildzr.dsl.relations` | `desc()`, `With()` helpers for relationships |

---

## Legend

- ✅ **Completed**: Feature is fully implemented with Python DSL equivalent
- 🟡 **Partial**: Model support exists but no DSL wrapper
- ❌ **Not Implemented**: Feature is not yet available
- N/A **Not Applicable**: Python provides a native alternative

## Notes

- buildzr uses a Pythonic DSL approach rather than the text-based Structurizr DSL
- Model classes support all Structurizr JSON schema fields even when DSL wrappers aren't available
- Features marked 🟡 can be accessed by manipulating the underlying model directly
- Check individual feature documentation links for detailed Structurizr specifications
