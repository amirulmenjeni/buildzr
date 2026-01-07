# Structurizr Java Investigation

Investigate how Structurizr for Java implements a specific feature or behavior.

## Usage

```
/query-structurizr <question or topic>
```

## Examples

```
/query-structurizr How does it validate relationships between elements?
/query-structurizr What error is thrown for duplicate view keys?
/query-structurizr How does the isChildOf method work in Model.java?
/query-structurizr What methods does Person have for creating relationships?
```

## Instructions

When this command is invoked:

1. **Understand the question**: Parse what aspect of Structurizr Java the user wants to understand

2. **Identify relevant source files**: Based on the topic, determine which Java files to examine:
   - Model/relationships → `Model.java`, `StaticStructureElement.java`
   - Views → `ViewSet.java`, specific view classes
   - Styles → `Styles.java`, `ElementStyle.java`
   - Elements → `Element.java`, `Person.java`, `SoftwareSystem.java`, etc.

3. **Fetch the source code**: Use WebFetch to get the raw source from GitHub:
   ```
   https://raw.githubusercontent.com/structurizr/java/master/structurizr-core/src/main/java/com/structurizr/...
   ```

4. **Search if needed**: Use WebSearch to find specific error messages or method names:
   ```
   site:github.com/structurizr/java "search term"
   ```

5. **Analyze and explain**:
   - Show the relevant code snippets
   - Explain how the logic works
   - Note any implications for buildzr implementation

6. **Provide actionable insights**: Suggest how this knowledge can be applied to buildzr

## Key Repository URLs

- Main repo: https://github.com/structurizr/java
- Core module: `structurizr-core/src/main/java/com/structurizr/`
- Model classes: `.../model/`
- View classes: `.../view/`

## Arguments

$ARGUMENTS - The question or topic to investigate about Structurizr Java implementation
