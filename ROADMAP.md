# Structurizr DSL Feature Roadmap

This roadmap tracks the implementation status of Structurizr DSL features in buildzr.

## Core Language Constructs

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Workspace](https://docs.structurizr.com/dsl/language#workspace) | ✅ | Top-level construct and wrapper for model and views |
| [Model](https://docs.structurizr.com/dsl/language#model) | ✅ | Container for architecture elements and relationships |
| [Configuration](https://docs.structurizr.com/dsl/language#configuration) | ✅ | Workspace-level configuration settings |

## Model Elements

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Person](https://docs.structurizr.com/dsl/language#person) | ✅ | Represents users, actors, roles, or personas |
| [Software System](https://docs.structurizr.com/dsl/language#softwaresystem) | ✅ | Represents a software system |
| [Container](https://docs.structurizr.com/dsl/language#container) | ✅ | Deployable/runnable unit within a system |
| [Component](https://docs.structurizr.com/dsl/language#component) | ✅ | Modular part of a container |
| [Group](https://docs.structurizr.com/dsl/language#group) | ✅ | Named grouping of elements |

## Deployment Model Elements

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Deployment Environment](https://docs.structurizr.com/dsl/language#deploymentenvironment) | ✅ | Defines deployment context (e.g., Development, Production) |
| [Deployment Node](https://docs.structurizr.com/dsl/language#deploymentnode) | ✅ | Represents infrastructure/runtime environment |
| [Deployment Group](https://docs.structurizr.com/dsl/language#deploymentgroup) | ✅ | Groups deployment instances |
| [Infrastructure Node](https://docs.structurizr.com/dsl/language#infrastructurenode) | ✅ | Represents supporting infrastructure components |
| [Software System Instance](https://docs.structurizr.com/dsl/language#softwaresysteminstance) | ✅ | Deployed instance of a software system |
| [Container Instance](https://docs.structurizr.com/dsl/language#containerinstance) | ✅ | Deployed instance of a container |

## Relationships

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Relationship](https://docs.structurizr.com/dsl/language#relationship) | ✅ | Defines relationships between elements |
| [Implied Relationships](https://docs.structurizr.com/dsl/language#impliedrelationships) | ✅ | Automatic relationship inference |

## Views

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [System Landscape View](https://docs.structurizr.com/dsl/language#systemlandscapeview) | ✅ | High-level overview of all systems |
| [System Context View](https://docs.structurizr.com/dsl/language#systemcontextview) | ✅ | System and its immediate interactions |
| [Container View](https://docs.structurizr.com/dsl/language#containerview) | ✅ | System's internal container structure |
| [Component View](https://docs.structurizr.com/dsl/language#componentview) | ✅ | Container's internal component composition |
| [Deployment View](https://docs.structurizr.com/dsl/language#deploymentview) | ✅ | Infrastructure and deployment details |
| [Dynamic View](https://docs.structurizr.com/dsl/language#dynamicview) | ❌ | Interaction sequences and collaboration |
| [Filtered View](https://docs.structurizr.com/dsl/language#filteredview) | ❌ | Subset of another view based on filters |
| [Custom View](https://docs.structurizr.com/dsl/language#customview) | ❌ | User-defined custom diagram |
| [Image View](https://docs.structurizr.com/dsl/language#image) | ❌ | External diagram integration |

## Styling and Theming

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Styles](https://docs.structurizr.com/dsl/language#styles) | ✅ | Visual styling for elements and relationships |
| [Element Style](https://docs.structurizr.com/dsl/language#element) | ✅ | Style individual elements by tag |
| [Relationship Style](https://docs.structurizr.com/dsl/language#relationship-1) | ✅ | Style relationships by tag |
| [Theme](https://docs.structurizr.com/dsl/language#theme) | ❌ | Apply predefined visual themes |
| [Branding](https://docs.structurizr.com/dsl/language#branding) | ❌ | Customize logo and fonts |

## Advanced Features

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Auto Layout](https://docs.structurizr.com/dsl/language#autolayout) | ✅ | Automatic diagram layout |
| [Properties](https://docs.structurizr.com/dsl/language#properties) | ✅ | Custom key-value metadata |
| [Tags](https://docs.structurizr.com/dsl/language#tags) | ✅ | Categorize and style elements |
| [URL](https://docs.structurizr.com/dsl/language#url) | ❌ | Associate URLs with elements |
| [Perspectives](https://docs.structurizr.com/dsl/language#perspectives) | ❌ | Multiple viewpoints on elements |
| [Archetypes](https://docs.structurizr.com/dsl/archetypes) | ❌ | User-defined element types |

## DSL Language Features

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Identifiers](https://docs.structurizr.com/dsl/identifiers) | ✅ | Reference elements like variables |
| [Expressions](https://docs.structurizr.com/dsl/expressions) | ✅ | Include/exclude elements in views |
| [!include](https://docs.structurizr.com/dsl/language#include) | ❌ | Import external DSL files |
| [!constant (!const)](https://docs.structurizr.com/dsl/language#constant) | ❌ | Define reusable constants |
| [!ref](https://docs.structurizr.com/dsl/language#ref) | ❌ | Reference elements from extended workspaces |
| [!docs](https://docs.structurizr.com/dsl/language#docs) | ❌ | Attach documentation |
| [!adrs](https://docs.structurizr.com/dsl/language#adrs) | ❌ | Add architectural decision records |
| [!script](https://docs.structurizr.com/dsl/language#script) | ❌ | Run scripting languages (Groovy, Kotlin, etc.) |
| [!plugin](https://docs.structurizr.com/dsl/language#plugin) | ❌ | Extend functionality with plugins |

## Workspace Features

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Workspace Extension](https://docs.structurizr.com/dsl/language#extends) | ❌ | Extend existing workspaces |
| [Description](https://docs.structurizr.com/dsl/language#description) | ✅ | Set descriptions on elements and views |
| [Technology](https://docs.structurizr.com/dsl/language#technology) | ✅ | Specify technology for containers/components |

## Additional Features

| Feature | Completed | Documentation |
|---------|-----------|---------------|
| [Scope](https://docs.structurizr.com/dsl/language#scope) | ✅ | Define workspace context (landscape/software system) |
| [Users](https://docs.structurizr.com/dsl/language#users) | ❌ | Define workspace permissions |

---

## Legend

- ✅ **Completed**: Feature is fully implemented in buildzr
- ❌ **Not Implemented**: Feature is not yet available in buildzr

## Notes

- buildzr uses a Pythonic DSL approach rather than the text-based Structurizr DSL
- Some features may be partially implemented or have Python-specific equivalents
- Check individual feature documentation links for detailed specifications
