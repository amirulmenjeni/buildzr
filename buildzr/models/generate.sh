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