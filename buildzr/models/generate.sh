schema_url=https://raw.githubusercontent.com/structurizr/json/master/structurizr.yaml

curl $schema_url > structurizr.yaml

# Change from 'long' (unsupported) to 'integer'
yq -i -y '.components.schemas.Workspace.properties.id.type = "integer"' structurizr.yaml

# Add `deploymentGroups: List[str]` to the following dataclasses:
# - `SoftwareSystemInstance`
# - `ContainerInstance`
# Because the `deploymentGroups` property is not in the schema, but it's
# something that is present in the JSON output if we convert the DSL into JSON
# (when using the `deploymentGroup` keyword).
yq -i -y '.components.schemas.ContainerInstance.properties.deploymentGroups = {"type": "array", "items": {"type": "string"}}' structurizr.yaml
yq -i -y '.components.schemas.SoftwareSystemInstance.properties.deploymentGroups = {"type": "array", "items": {"type": "string"}}' structurizr.yaml

# Add CustomElement and CustomView schemas
# Note: The official Structurizr JSON schema (https://github.com/structurizr/json) does NOT include
# customElements or customViews fields, but the Structurizr CLI and DSL fully support these features.
# The schema below was derived from testing with `structurizr.sh export`.

# Add CustomElement schema (custom element outside C4 model)
yq -i -y '.components.schemas.CustomElement = {
  "type": "object",
  "description": "A custom element that sits outside the C4 model.",
  "properties": {
    "id": {"type": "string", "description": "The ID of this element in the model."},
    "name": {"type": "string", "description": "The name of this element."},
    "metadata": {"type": "string", "description": "The metadata associated with this element."},
    "description": {"type": "string", "description": "A short description of this element."},
    "tags": {"type": "string", "description": "A comma separated list of tags associated with this element."},
    "url": {"type": "string", "description": "The URL where more information about this element can be found."},
    "properties": {"type": "object", "additionalProperties": true, "description": "A set of arbitrary name-value properties."},
    "perspectives": {"type": "array", "items": {"$ref": "#/components/schemas/Perspective"}},
    "relationships": {"type": "array", "items": {"$ref": "#/components/schemas/Relationship"}}
  }
}' structurizr.yaml

# Add CustomView schema (view for custom elements)
yq -i -y '.components.schemas.CustomView = {
  "type": "object",
  "description": "A custom view for displaying custom elements.",
  "properties": {
    "key": {"type": "string", "description": "A unique identifier for this view."},
    "order": {"type": "number", "description": "An integer representing the creation order of this view."},
    "title": {"type": "string", "description": "The title of this view (optional)."},
    "description": {"type": "string", "description": "The description of this view."},
    "properties": {"type": "object", "additionalProperties": true, "description": "A set of arbitrary name-value properties."},
    "elements": {"type": "array", "items": {"$ref": "#/components/schemas/ElementView"}},
    "relationships": {"type": "array", "items": {"$ref": "#/components/schemas/RelationshipView"}},
    "automaticLayout": {"$ref": "#/components/schemas/AutomaticLayout"}
  }
}' structurizr.yaml

# Add customElements field to Model
yq -i -y '.components.schemas.Model.properties.customElements = {"type": "array", "items": {"$ref": "#/components/schemas/CustomElement"}}' structurizr.yaml

# Add customViews field to Views
yq -i -y '.components.schemas.Views.properties.customViews = {"type": "array", "items": {"$ref": "#/components/schemas/CustomView"}, "description": "The set of custom views."}' structurizr.yaml

# Add applied field to AutomaticLayout (indicates whether auto-layout has been applied)
yq -i -y '.components.schemas.AutomaticLayout.properties.applied = {"type": "boolean", "description": "Whether automatic layout has been applied to this view."}' structurizr.yaml

# Type 'integer' doesn't support 'number' type, but supports the following:
# int32, int64, default, date-time, unix-time
# yq -i 'select(.components.schemas.*.properties.*.format=="integer" and .components.schemas.*.properties.*.type=="number") .components.schemas.*.properties.*.format="default"' structurizr.yaml

# Format 'url' isn't supported. Change the format to 'string' and type to 'uri'.
# yq -i 'select(.components.schemas.*.properties.*.format=="url" and .components.schemas.*.properties.*.type=="string") .components.schemas.*.properties.*.format="uri"' structurizr.yaml

datamodel-codegen \
    --input-file-type openapi \
    --output-model-type dataclasses.dataclass \
    --input structurizr.yaml \
    --output models.py \
    --use-schema-description \
    --use-field-description