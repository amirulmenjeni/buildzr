# Structurizr Java Investigation Skill

Use this skill when you need to understand how Structurizr for Java implements specific features, validation rules, or behaviors. This is useful when:

- Implementing equivalent functionality in buildzr
- Understanding why certain operations fail or are restricted
- Finding the source of error messages
- Understanding the Java API for the workspace converter

## Key Repositories

- **structurizr/java** - Main Structurizr Java library
  - GitHub: https://github.com/structurizr/java
  - Raw files: https://raw.githubusercontent.com/structurizr/java/master/

- **structurizr/export** - Export functionality (PlantUML, Mermaid, etc.)
  - GitHub: https://github.com/structurizr/export

## Important Source Paths

### Core Model Classes
- `structurizr-core/src/main/java/com/structurizr/model/Model.java` - Main model, relationship validation
- `structurizr-core/src/main/java/com/structurizr/model/Element.java` - Base element class
- `structurizr-core/src/main/java/com/structurizr/model/StaticStructureElement.java` - uses(), delivers(), interactsWith()
- `structurizr-core/src/main/java/com/structurizr/model/Person.java` - Person element
- `structurizr-core/src/main/java/com/structurizr/model/SoftwareSystem.java` - Software system
- `structurizr-core/src/main/java/com/structurizr/model/Container.java` - Container
- `structurizr-core/src/main/java/com/structurizr/model/Component.java` - Component
- `structurizr-core/src/main/java/com/structurizr/model/Relationship.java` - Relationships

### Views
- `structurizr-core/src/main/java/com/structurizr/view/ViewSet.java` - View management
- `structurizr-core/src/main/java/com/structurizr/view/SystemContextView.java`
- `structurizr-core/src/main/java/com/structurizr/view/ContainerView.java`
- `structurizr-core/src/main/java/com/structurizr/view/ComponentView.java`

### Styles
- `structurizr-core/src/main/java/com/structurizr/view/Styles.java` - Style management
- `structurizr-core/src/main/java/com/structurizr/view/ElementStyle.java`
- `structurizr-core/src/main/java/com/structurizr/view/RelationshipStyle.java`

## Investigation Process

1. **Search for error messages**: If you have an error message, search for it in the source code
   ```
   WebSearch: structurizr java "error message here" site:github.com
   ```

2. **Fetch specific source files**: Use WebFetch to get the raw source
   ```
   WebFetch: https://raw.githubusercontent.com/structurizr/java/master/structurizr-core/src/main/java/com/structurizr/model/Model.java
   ```

3. **Look for method implementations**: Check the class that likely contains the logic
   - Relationship validation → Model.java
   - Element hierarchy → Element.java, StaticStructureElement.java
   - View creation → ViewSet.java
   - Style management → Styles.java

4. **Check for validation logic**: Look for `throw new IllegalArgumentException` or similar

## Common Patterns Found

### Parent-Child Relationship Check (Model.java)
```java
if (isChildOf(source, destination) || isChildOf(destination, source)) {
    throw new IllegalArgumentException("Relationships cannot be added between parents and children.");
}
```

### Relationship Methods (StaticStructureElement.java)
- `uses(Element, description, technology)` - For relationships to Container/Component/SoftwareSystem
- `delivers(Person, description, technology)` - For relationships TO a Person
- `interactsWith(Person, description, technology)` - For Person-to-Person relationships

### Duplicate View Key Check (ViewSet.java)
```java
if (getViewWithKey(key) != null) {
    throw new IllegalArgumentException("A view with the key " + key + " already exists.");
}
```

## Example Queries

When asked to investigate something, use these patterns:

1. "How does Structurizr validate relationships?"
   → Fetch Model.java, look for addRelationship method

2. "What methods can Person use to create relationships?"
   → Fetch Person.java and StaticStructureElement.java

3. "How are implied relationships created?"
   → Search for "implied" in the codebase, check ImpliedRelationshipsStrategy

4. "Why can't I add a style with the same tag?"
   → Fetch Styles.java, look for addElementStyle method
