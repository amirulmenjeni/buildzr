"""JSON loader for deserializing workspace.json files into buildzr models."""

from __future__ import annotations

import dataclasses
import json
import sys
import urllib.request
from enum import Enum
from typing import Any, Dict, List, Optional, Type, TypeVar, Union, get_type_hints, get_origin, get_args

import buildzr.models

# Python 3.10+ uses types.UnionType for X | Y syntax
if sys.version_info >= (3, 10):
    import types
    UnionTypes = (Union, types.UnionType)
else:
    UnionTypes = (Union,)

T = TypeVar('T')


class JsonLoader:
    """
    Loads a Structurizr workspace.json file and deserializes it into buildzr models.

    Supports loading from:
    - Local file paths
    - HTTP/HTTPS URLs
    """

    def load(self, source: str) -> buildzr.models.Workspace:
        """
        Load a workspace from a local file or URL.

        Args:
            source: Path to local file or URL (http:// or https://)

        Returns:
            A deserialized Workspace model
        """
        if source.startswith(('http://', 'https://')):
            data = self._fetch_url(source)
        else:
            data = self._read_file(source)

        return self._deserialize(data, buildzr.models.Workspace)

    def _read_file(self, path: str) -> Dict[str, Any]:
        """Read and parse JSON from a local file."""
        with open(path, 'r') as f:
            return json.load(f) # type: ignore

    def _fetch_url(self, url: str) -> Dict[str, Any]:
        """Fetch and parse JSON from a URL."""
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode('utf-8')) # type: ignore[no-any-return]

    def _deserialize(self, data: Any, cls: Type[T]) -> T:
        """
        Recursively deserialize a dict into a dataclass instance.

        Handles:
        - Nested dataclasses
        - Optional fields
        - List fields
        - Enum fields
        - Dict fields
        """
        if data is None:
            return None

        # Handle non-dict primitives
        if not isinstance(data, dict):
            # Check if we need to convert to enum
            if isinstance(cls, type) and issubclass(cls, Enum):
                return cls(data)
            return data  # type: ignore[no-any-return]

        # Get type hints for the dataclass
        if not dataclasses.is_dataclass(cls):
            # If it's not a dataclass, just return the dict
            return data  # type: ignore

        type_hints = get_type_hints(cls)
        kwargs: Dict[str, Any] = {}

        for field in dataclasses.fields(cls):
            field_name = field.name
            if field_name not in data:
                continue

            field_value = data[field_name]
            field_type = type_hints.get(field_name, field.type)

            kwargs[field_name] = self._deserialize_field(field_value, field_type)

        return cls(**kwargs)

    def _deserialize_field(self, value: Any, field_type: Any) -> Any:
        """Deserialize a single field value based on its type."""
        if value is None:
            return None

        # Get the origin type (e.g., List, Optional, Dict)
        origin = get_origin(field_type)
        args = get_args(field_type)

        # Handle Optional[X] (which is Union[X, None]) and X | None (Python 3.10+)
        # Check for typing.Union or types.UnionType
        is_union = origin is Union
        if sys.version_info >= (3, 10):
            is_union = is_union or isinstance(origin, type) and issubclass(origin, types.UnionType)

        if is_union:
            # Filter out NoneType
            non_none_args = [arg for arg in args if arg is not type(None)]
            if len(non_none_args) == 1:
                return self._deserialize_field(value, non_none_args[0])
            # If multiple non-None types, try each one
            for arg in non_none_args:
                try:
                    return self._deserialize_field(value, arg)
                except (TypeError, ValueError):
                    continue
            return value

        # Handle List[X]
        if origin is list:
            if not isinstance(value, list):
                return value
            item_type = args[0] if args else Any
            return [self._deserialize_field(item, item_type) for item in value]

        # Handle Dict[K, V]
        if origin is dict:
            if not isinstance(value, dict):
                return value
            # For Dict types, just return the dict as-is
            return value

        # Handle Enum types
        if isinstance(field_type, type) and issubclass(field_type, Enum):
            try:
                return field_type(value)
            except ValueError:
                # Try to find enum by name if value doesn't match
                for member in field_type:
                    if member.name == value or member.value == value:
                        return member
                return value

        # Handle dataclass types
        if dataclasses.is_dataclass(field_type) and isinstance(field_type, type) and isinstance(value, dict):
            return self._deserialize(value, field_type)

        return value

    def get_max_element_id(self, workspace: buildzr.models.Workspace) -> int:
        """
        Find the highest numeric element ID in the workspace.

        This is used to set the ID counter offset when extending a workspace,
        ensuring new elements don't have colliding IDs.

        Args:
            workspace: The loaded workspace model

        Returns:
            The highest numeric ID found, or 0 if none found
        """
        max_id = 0

        if workspace.model is None:
            return max_id

        # Check software systems
        if workspace.model.softwareSystems:
            for ss in workspace.model.softwareSystems:
                max_id = self._update_max_id(max_id, ss.id)

                # Check relationships
                if ss.relationships:
                    for rel in ss.relationships:
                        max_id = self._update_max_id(max_id, rel.id)

                # Check containers
                if ss.containers:
                    for container in ss.containers:
                        max_id = self._update_max_id(max_id, container.id)

                        if container.relationships:
                            for rel in container.relationships:
                                max_id = self._update_max_id(max_id, rel.id)

                        # Check components
                        if container.components:
                            for component in container.components:
                                max_id = self._update_max_id(max_id, component.id)

                                if component.relationships:
                                    for rel in component.relationships:
                                        max_id = self._update_max_id(max_id, rel.id)

        # Check people
        if workspace.model.people:
            for person in workspace.model.people:
                max_id = self._update_max_id(max_id, person.id)

                if person.relationships:
                    for rel in person.relationships:
                        max_id = self._update_max_id(max_id, rel.id)

        # Check deployment nodes
        if workspace.model.deploymentNodes:
            max_id = self._get_max_deployment_node_id(workspace.model.deploymentNodes, max_id)

        return max_id

    def _get_max_deployment_node_id(self, nodes: List[buildzr.models.DeploymentNode], current_max: int) -> int:
        """Recursively find max ID in deployment nodes."""
        for node in nodes:
            current_max = self._update_max_id(current_max, node.id)

            if node.relationships:
                for rel in node.relationships:
                    current_max = self._update_max_id(current_max, rel.id)

            if node.infrastructureNodes:
                for infra in node.infrastructureNodes:
                    current_max = self._update_max_id(current_max, infra.id)

                    if infra.relationships:
                        for rel in infra.relationships:
                            current_max = self._update_max_id(current_max, rel.id)

            if node.softwareSystemInstances:
                for instance in node.softwareSystemInstances:
                    current_max = self._update_max_id(current_max, instance.id)

                    if instance.relationships:
                        for rel in instance.relationships:
                            current_max = self._update_max_id(current_max, rel.id)

            if node.containerInstances:
                for container_instance in node.containerInstances:
                    current_max = self._update_max_id(current_max, container_instance.id)

                    if container_instance.relationships:
                        for rel in container_instance.relationships:
                            current_max = self._update_max_id(current_max, rel.id)

            # Recurse into child deployment nodes
            if node.children:
                current_max = self._get_max_deployment_node_id(node.children, current_max)

        return current_max

    def _update_max_id(self, current_max: int, id_value: Optional[str]) -> int:
        """Update max ID if the given ID is numeric and larger."""
        if id_value is None:
            return current_max
        try:
            numeric_id = int(id_value)
            return max(current_max, numeric_id)
        except ValueError:
            # ID is not numeric, ignore
            return current_max
