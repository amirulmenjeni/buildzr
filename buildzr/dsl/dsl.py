from dataclasses import dataclass
from pathlib import Path
import buildzr
from .factory import GenerateId
from typing_extensions import (
    Self,
    TypeIs,
)
from collections import deque
from contextvars import ContextVar
from typing import (
    Any,
    Union,
    Tuple,
    List,
    Set,
    Dict,
    Optional,
    Generic,
    TypeVar,
    Callable,
    Iterable,
    Literal,
    cast,
    Type,
    overload
)

from buildzr.sinks.interfaces import Sink
from buildzr.dsl.interfaces import (
    DslWorkspaceElement,
    DslElement,
    DslViewElement,
    DslDeploymentEnvironment,
    DslInfrastructureNodeElement,
    DslDeploymentNodeElement,
    DslElementInstance,
)
from buildzr.dsl.relations import (
    DslElementRelationOverrides,
    DslRelationship,
    _Relationship,
)
from buildzr.dsl.color import Color

# Type alias for save() format parameter
SaveFormat = Literal['json', 'plantuml', 'svg', 'png']


def _child_name_transform(name: str) -> str:
    return name.lower().replace(' ', '_')

TypedModel = TypeVar('TypedModel')
class TypedDynamicAttribute(Generic[TypedModel]):

    def __init__(self, dynamic_attributes: Dict[str, Any]) -> None:
        self._dynamic_attributes = dynamic_attributes

    def __getattr__(self, name: str) -> TypedModel:
        return cast(TypedModel, self._dynamic_attributes.get(name))

_current_workspace: ContextVar[Optional['Workspace']] = ContextVar('current_workspace', default=None)
_current_group_stack: ContextVar[List['Group']] = ContextVar('current_group', default=[])
_current_software_system: ContextVar[Optional['SoftwareSystem']] = ContextVar('current_software_system', default=None)
_current_container: ContextVar[Optional['Container']] = ContextVar('current_container', default=None)
_current_deployment_environment: ContextVar[Optional['DeploymentEnvironment']] = ContextVar('current_deployment_environment', default=None)
_current_deployment_node_stack: ContextVar[List['DeploymentNode']] = ContextVar('current_deployment_node', default=[])

class Workspace(DslWorkspaceElement):
    """
    Represents a Structurizr workspace, which is a wrapper for a software architecture model, views, and documentation.
    """

    @property
    def model(self) -> buildzr.models.Workspace:
        return self._m

    @property
    def parent(self) -> None:
        return None

    @property
    def children(self) -> Optional[List[Union['Person', 'SoftwareSystem', 'DeploymentNode', 'Element']]]:
        return self._children

    def __init__(
            self,
            name: str,
            description: str="",
            scope: Literal['landscape', 'software_system', None]='software_system',
            implied_relationships: bool=False,
            group_separator: str='/',
            extend: Optional[str]=None,
        ) -> None:

        self._m = buildzr.models.Workspace()
        self._parent = None
        self._children: Optional[List[Union['Person', 'SoftwareSystem', 'DeploymentNode', 'Element']]] = []
        self._dynamic_attrs: Dict[str, Union['Person', 'SoftwareSystem', 'Element']] = {}
        self._use_implied_relationships = implied_relationships
        self._group_separator = group_separator

        # Workspace extension support - store extended model for merging
        self._extended_model: Optional[buildzr.models.Workspace] = None

        if extend:
            from buildzr.loaders import JsonLoader
            loader = JsonLoader()
            self._extended_model = loader.load(extend)
            # Set ID counter to avoid collisions with extended workspace IDs
            max_id = loader.get_max_element_id(self._extended_model)
            GenerateId.set_offset(max_id)

            # Wrap parent elements with DSL classes for direct access on workspace
            self._wrap_parent_elements()

        self.model.id = GenerateId.for_workspace()
        self.model.name = name
        self.model.description = description
        self.model.model = buildzr.models.Model(
            people=[],
            softwareSystems=[],
            deploymentNodes=[],
        )

        # Add documentation object (required by Structurizr for rendering)
        self.model.documentation = buildzr.models.Documentation()

        scope_mapper: Dict[
            str,
            Literal[buildzr.models.Scope.Landscape, buildzr.models.Scope.SoftwareSystem, None]
        ] = {
            'landscape': buildzr.models.Scope.Landscape,
            'software_system': buildzr.models.Scope.SoftwareSystem,
            None: None
        }

        self.model.configuration = buildzr.models.WorkspaceConfiguration(
            scope=scope_mapper[scope],
        )

        self.model.model.properties = {
            'structurizr.groupSeparator': group_separator,
        }

    def _wrap_parent_elements(self) -> None:
        """Wrap parent workspace elements with DSL classes for direct access."""
        if self._extended_model is None or self._extended_model.model is None:
            return

        # Wrap software systems from parent
        if self._extended_model.model.softwareSystems:
            for ss_model in self._extended_model.model.softwareSystems:
                ss = SoftwareSystem._from_model(ss_model)
                ss._parent = self
                self._children.append(ss)
                self._add_dynamic_attr(ss_model.name or '', ss)

        # Wrap people from parent
        if self._extended_model.model.people:
            for person_model in self._extended_model.model.people:
                person = Person._from_model(person_model)
                person._parent = self
                self._children.append(person)
                self._add_dynamic_attr(person_model.name or '', person)

    def __enter__(self) -> Self:
        """Enter the workspace context."""
        self._token = _current_workspace.set(self)
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_value: Optional[BaseException], traceback: Optional[Any]) -> None:

        if self._use_implied_relationships:
            self._imply_relationships()

        _current_workspace.reset(self._token)

    def _is_descendant_of(self, element: 'DslElement', potential_ancestor: 'DslElement') -> bool:
        """Check if element is a descendant (child, grandchild, etc.) of potential_ancestor."""
        current = element.parent
        while current is not None:
            if current is potential_ancestor:
                return True
            current = current.parent
        return False

    def _imply_relationships( self,
    ) -> None:

        """
        Process implied relationships:
        If we have relationship s >> do >> a.b, then create s >> do >> a.
        If we have relationship s.ss >> do >> a.b.c, then create s.ss >> do >> a.b and s.ss >> do >> a.
        If we have relationship s.ss >> do >> a, then create s >> do >> a.
        And so on...

        Relationships of `SoftwareSystemInstance`s and `ContainerInstance`s are
        skipped.

        This process is idempotent, which means this can be called multiple times
        without duplicating similar relationships.
        """

        if not self._use_implied_relationships:
            return

        from buildzr.dsl.explorer import Explorer

        explorer = Explorer(self)
        # Take a snapshot of relationships to avoid processing newly created ones
        relationships = list(explorer.walk_relationships())
        for relationship in relationships:
            source = relationship.source
            destination = relationship.destination
            destination_parent = destination.parent

            if isinstance(source, (SoftwareSystemInstance, ContainerInstance)) or \
               isinstance(destination, (SoftwareSystemInstance, ContainerInstance)):
                continue

            # Skip relationships that are already implied (have linkedRelationshipId)
            if relationship.model.linkedRelationshipId is not None:
                continue

            # Handle case: s >> a.b => s >> a (destination is child)
            while destination_parent is not None and \
                isinstance(source, DslElement) and \
                not isinstance(source.model, buildzr.models.Workspace) and \
                not isinstance(destination_parent, DslWorkspaceElement):

                # Stop if source is a descendant of destination_parent (parent-child relationship)
                if self._is_descendant_of(source, destination_parent):
                    break

                rels = source.model.relationships

                if rels:
                    already_exists = any(
                        r.destinationId == destination_parent.model.id and
                        r.description == relationship.model.description and
                        r.technology == relationship.model.technology
                        for r in rels
                    )
                    if not already_exists:
                        r = source.uses(
                            destination_parent,
                            description=relationship.model.description,
                            technology=relationship.model.technology,
                        )
                        r.model.linkedRelationshipId = relationship.model.id
                destination_parent = destination_parent.parent

            # Handle inverse case: s.ss >> a => s >> a (source is child)
            source_parent = source.parent
            while source_parent is not None and \
                isinstance(destination, DslElement) and \
                not isinstance(destination.model, buildzr.models.Workspace) and \
                not isinstance(source_parent.model, buildzr.models.Workspace) and \
                not isinstance(source_parent, DslWorkspaceElement):

                # Stop if destination is a descendant of source_parent (parent-child relationship)
                if self._is_descendant_of(destination, source_parent):
                    break

                rels = source_parent.model.relationships

                # The parent source relationship might be empty
                # (i.e., []).
                if rels is not None:
                    already_exists = any(
                        r.destinationId == destination.model.id and
                        r.description == relationship.model.description and
                        r.technology == relationship.model.technology
                        for r in rels
                    )
                    if not already_exists:
                        r = source_parent.uses(
                            destination,
                            description=relationship.model.description,
                            technology=relationship.model.technology,
                        )
                        r.model.linkedRelationshipId = relationship.model.id
                source_parent = source_parent.parent

    def person(self) -> TypedDynamicAttribute['Person']:
        return TypedDynamicAttribute['Person'](self._dynamic_attrs)

    def software_system(self) -> TypedDynamicAttribute['SoftwareSystem']:
        return TypedDynamicAttribute['SoftwareSystem'](self._dynamic_attrs)

    def add_model(
        self, model: Union[
            'Person',
            'SoftwareSystem',
            'DeploymentNode',
            'Element',
        ]) -> None:
        if isinstance(model, Person):
            self._m.model.people.append(model._m)
            model._parent = self
            self._add_dynamic_attr(model.model.name, model)
            self._children.append(model)
        elif isinstance(model, SoftwareSystem):
            self._m.model.softwareSystems.append(model._m)
            model._parent = self
            self._add_dynamic_attr(model.model.name, model)
            self._children.append(model)
        elif isinstance(model, DeploymentNode):
            self._m.model.deploymentNodes.append(model._m)
            model._parent = self
            self._children.append(model)
        elif isinstance(model, Element):
            if self._m.model.customElements is None:
                self._m.model.customElements = []
            self._m.model.customElements.append(model._m)
            model._parent = self
            self._add_dynamic_attr(model.model.name, model)
            self._children.append(model)
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a workspace.'.format(type(model)))

    def apply_view( self,
        view: Union[
            'SystemLandscapeView',
            'SystemContextView',
            'ContainerView',
            'ComponentView',
            'DeploymentView',
            'DynamicView',
            'CustomView',
        ]
    ) -> None:

        self._imply_relationships()

        view._on_added(self)

        if not self.model.views:
            self.model.views = buildzr.models.Views()
            # Add configuration object (required by Structurizr for rendering)
            self.model.views.configuration = buildzr.models.Configuration(
                branding=buildzr.models.Branding(),
                styles=buildzr.models.Styles(),
                terminology=buildzr.models.Terminology(),
            )

        if isinstance(view, SystemLandscapeView):
            if not self.model.views.systemLandscapeViews:
                self.model.views.systemLandscapeViews = [view.model]
            else:
                self.model.views.systemLandscapeViews.append(view.model)
        elif isinstance(view, SystemContextView):
            if not self.model.views.systemContextViews:
                self.model.views.systemContextViews = [view.model]
            else:
                self.model.views.systemContextViews.append(view.model)
        elif isinstance(view, ContainerView):
            if not self.model.views.containerViews:
                self.model.views.containerViews = [view.model]
            else:
                self.model.views.containerViews.append(view.model)
        elif isinstance(view, ComponentView):
            if not self.model.views.componentViews:
                self.model.views.componentViews = [view.model]
            else:
                self.model.views.componentViews.append(view.model)
        elif isinstance(view, DeploymentView):
            if not self.model.views.deploymentViews:
                self.model.views.deploymentViews = [view.model]
            else:
                self.model.views.deploymentViews.append(view.model)
        elif isinstance(view, DynamicView):
            if not self.model.views.dynamicViews:
                self.model.views.dynamicViews = [view.model]
            else:
                self.model.views.dynamicViews.append(view.model)
        elif isinstance(view, CustomView):
            if not self.model.views.customViews:
                self.model.views.customViews = [view.model]
            else:
                self.model.views.customViews.append(view.model)
        else:
            raise NotImplementedError("The view {0} is currently not supported", type(view))

    def apply_style( self,
        style: Union['StyleElements', 'StyleRelationships'],
    ) -> None:

        style._parent = self

        if not self.model.views:
            self.model.views = buildzr.models.Views()
        if not self.model.views.configuration:
            self.model.views.configuration = buildzr.models.Configuration()
        if not self.model.views.configuration.styles:
            self.model.views.configuration.styles = buildzr.models.Styles()

        if isinstance(style, StyleElements):
            if self.model.views.configuration.styles.elements:
                self.model.views.configuration.styles.elements.extend(style.model)
            else:
                self.model.views.configuration.styles.elements = style.model
        elif isinstance(style, StyleRelationships):
            if self.model.views.configuration.styles.relationships:
                self.model.views.configuration.styles.relationships.extend(style.model)
            else:
                self.model.views.configuration.styles.relationships = style.model

    def _merged_workspace(self) -> 'buildzr.models.Workspace':
        """
        Get the merged workspace model, combining extended workspace if present.

        This method handles implied relationships and workspace extension merging.

        Returns:
            The merged workspace model ready for export.
        """
        self._imply_relationships()

        if self._extended_model:
            return self._merge_models(self._extended_model, self._m)
        return self._m
    def to_dict(self) -> Dict[str, Any]:
        """
        Return workspace as a JSON-serializable dictionary.

        This method is useful for programmatic access to the workspace data
        and for Jupyter notebook display.

        Returns:
            Dictionary representation of the workspace with camelCase keys.

        Example:
            >>> data = workspace.to_dict()
            >>> print(data['name'])
        """
        import json
        from buildzr.encoders.encoder import JsonEncoder
        merged = self._merged_workspace()
        return cast(Dict[str, Any], json.loads(JsonEncoder().encode(merged)))

    def _sanitize_name(self, name: str) -> str:
        """Sanitize workspace name for use as filename."""
        return name.lower().replace(' ', '_')

    def save(
        self,
        format: SaveFormat = 'json',
        path: Optional[Union[str, Path]] = None,
        pretty: bool = False,
    ) -> Union[str, List[str]]:
        """
        Save workspace to file(s) in the specified format.

        Args:
            format: Output format. One of:
                - 'json': Single JSON file (default)
                - 'plantuml': PlantUML .puml files (one per view)
                - 'svg': SVG image files (one per view)
                - 'png': PNG image files (one per view)
            path: Output path. Behavior depends on format:
                - For 'json': file path (defaults to '{cwd}/{workspace_name}.json')
                - For diagram formats: directory path (defaults to '{cwd}/')
            pretty: For 'json' format only, whether to indent output.

        Returns:
            - For 'json': The path to the written file (str)
            - For diagram formats: List of paths to written files

        Raises:
            ImportError: If 'plantuml'/'svg'/'png' format requested but jpype1
                not installed. Install with: pip install buildzr[export-plantuml]
            ValueError: If format is not recognized.

        Example:
            >>> w.save()  # Saves to ./my_workspace.json
            >>> w.save(format='json', path='output/arch.json', pretty=True)
            >>> w.save(format='plantuml', path='diagrams/')
            >>> w.save(format='svg')  # Saves to ./
        """
        merged = self._merged_workspace()
        workspace_name = self._sanitize_name(self.model.name or 'workspace')

        if format == 'json':
            return self._save_json(merged, path, workspace_name, pretty)
        elif format in ('plantuml', 'svg', 'png'):
            return self._save_diagrams(merged, path, format)
        else:
            raise ValueError(
                f"Unsupported format: {format}. "
                f"Use one of: 'json', 'plantuml', 'svg', 'png'"
            )

    def _save_json(
        self,
        workspace: 'buildzr.models.Workspace',
        path: Optional[Union[str, Path]],
        workspace_name: str,
        pretty: bool,
    ) -> str:
        """Save workspace as JSON file."""
        import os
        from buildzr.sinks.json_sink import JsonSink, JsonSinkConfig

        if path is None:
            path = Path.cwd() / f"{workspace_name}.json"

        path = Path(path)

        # Create parent directories if needed
        if path.parent and not path.parent.exists():
            os.makedirs(path.parent, exist_ok=True)

        sink = JsonSink()
        sink.write(workspace=workspace, config=JsonSinkConfig(
            path=str(path),
            pretty=pretty
        ))
        return str(path)

    def _save_diagrams(
        self,
        workspace: 'buildzr.models.Workspace',
        path: Optional[Union[str, Path]],
        format: Literal['plantuml', 'svg', 'png'],
    ) -> List[str]:
        """Save workspace views as diagram files."""
        import os

        try:
            from buildzr.sinks.plantuml_sink import PlantUmlSink, PlantUmlSinkConfig
        except ImportError as e:
            raise ImportError(
                "jpype1 is required for diagram export. "
                "Install with: pip install buildzr[export-plantuml]"
            ) from e

        if path is None:
            path = Path.cwd()

        path = Path(path)

        # Create directory if needed
        if not path.exists():
            os.makedirs(path, exist_ok=True)

        # Map format to PlantUmlSinkConfig format
        puml_format: Literal['puml', 'svg', 'png']
        if format == 'plantuml':
            puml_format = 'puml'
        else:
            puml_format = format  # 'svg' or 'png'

        sink = PlantUmlSink()
        config = PlantUmlSinkConfig(path=str(path), format=puml_format)
        sink.write(workspace=workspace, config=config)

        # Build list of created files based on views
        ext = 'puml' if format == 'plantuml' else format
        created_files: List[str] = []

        if workspace.views:
            views = workspace.views
            # Collect all views that have keys
            all_views: List[Any] = []
            if views.systemLandscapeViews:
                all_views.extend(views.systemLandscapeViews)
            if views.systemContextViews:
                all_views.extend(views.systemContextViews)
            if views.containerViews:
                all_views.extend(views.containerViews)
            if views.componentViews:
                all_views.extend(views.componentViews)
            if views.deploymentViews:
                all_views.extend(views.deploymentViews)
            if views.dynamicViews:
                all_views.extend(views.dynamicViews)
            if views.customViews:
                all_views.extend(views.customViews)

            for view in all_views:
                if view.key:
                    created_files.append(str(path / f"{view.key}.{ext}"))

        return created_files

    def to_json(self, pretty: bool = True) -> str:
        """
        Return workspace as a JSON string.

        Args:
            pretty: If True (default), format with 2-space indentation.

        Returns:
            JSON string representation of the workspace.

        Example:
            >>> json_str = workspace.to_json()
            >>> print(json_str)
        """
        from buildzr.encoders.encoder import JsonEncoder
        merged = self._merged_workspace()
        indent = 2 if pretty else None
        return JsonEncoder(indent=indent).encode(merged)

    def _repr_json_(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Jupyter notebook JSON representation.

        Returns a tuple of (data, metadata) for Jupyter's JSON display.
        The data is the workspace as a dictionary, and metadata controls display.

        Returns:
            Tuple of (workspace_dict, display_metadata)
        """
        return self.to_dict(), {"expanded": False, "root": "workspace"}

    def to_plantuml(self) -> Dict[str, str]:
        """
        Return PlantUML source for all views as a dictionary.

        Uses the official structurizr-export Java library via JPype to generate
        C4-PlantUML diagrams from workspace views.

        Returns:
            Dictionary mapping view keys to PlantUML source strings.

        Raises:
            ImportError: If jpype1 is not installed (install with: pip install buildzr[export-plantuml])
            FileNotFoundError: If structurizr-export JAR cannot be found

        Example:
            >>> diagrams = workspace.to_plantuml()
            >>> for key, puml in diagrams.items():
            ...     print(f"{key}: {len(puml)} chars")
        """
        from buildzr.sinks.plantuml_sink import PlantUmlSink
        merged = self._merged_workspace()
        sink = PlantUmlSink()
        return sink.export_to_dict(merged)

    def to_svg(self) -> Dict[str, str]:
        """
        Return SVG content for all views as a dictionary.

        Uses the official structurizr-export Java library and PlantUML to
        render workspace views as SVG diagrams.

        Returns:
            Dictionary mapping view keys to SVG content strings.

        Raises:
            ImportError: If jpype1 is not installed (install with: pip install buildzr[export-plantuml])
            FileNotFoundError: If structurizr-export JAR cannot be found

        Example:
            >>> svgs = workspace.to_svg()
            >>> with open('diagram.svg', 'w') as f:
            ...     f.write(svgs['SystemContext'])
        """
        from buildzr.sinks.plantuml_sink import PlantUmlSink
        merged = self._merged_workspace()
        sink = PlantUmlSink()
        return sink.render_to_svg_dict(merged)

    def _repr_html_(self) -> str:
        """
        Jupyter notebook HTML representation with embedded SVG diagrams.

        Displays all workspace views as SVG diagrams stacked vertically,
        each with a heading showing the view key.

        Returns:
            HTML string with embedded SVG diagrams.

        Raises:
            ImportError: If jpype1 is not installed. Install with:
                pip install buildzr[export-plantuml]
        """
        try:
            svgs = self.to_svg()
        except ImportError as e:
            raise ImportError(
                "PlantUML export dependencies not installed. "
                "Install with: pip install buildzr[export-plantuml]"
            ) from e

        if not svgs:
            return "<p><em>No views defined in workspace.</em></p>"

        html_parts = []
        for view_key, svg_content in svgs.items():
            html_parts.append(f'<div style="margin-bottom: 2em;">')
            html_parts.append(f'<h3 style="font-family: sans-serif; color: #333;">{view_key}</h3>')
            html_parts.append(svg_content)
            html_parts.append('</div>')

        return '\n'.join(html_parts)

    def _merge_models(
        self,
        parent: buildzr.models.Workspace,
        child: buildzr.models.Workspace
    ) -> buildzr.models.Workspace:
        """
        Merge parent and child workspace models.

        The merged model contains:
        - All elements from parent workspace (with any modifications from child)
        - New elements added in child workspace
        - Relationships from both workspaces

        Args:
            parent: The extended (parent) workspace model
            child: The current (child) workspace model

        Returns:
            A new merged Workspace model
        """
        import copy

        # Start with a copy of the parent model
        merged = copy.deepcopy(parent)

        # Use child's name and description
        merged.name = child.name
        merged.description = child.description

        # Merge software systems
        if child.model and child.model.softwareSystems:
            if merged.model is None:
                merged.model = buildzr.models.Model()
            if merged.model.softwareSystems is None:
                merged.model.softwareSystems = []

            # Get existing IDs from parent
            existing_ids = {ss.id for ss in merged.model.softwareSystems}

            for ss in child.model.softwareSystems:
                if ss.id not in existing_ids:
                    merged.model.softwareSystems.append(ss)

        # Merge people
        if child.model and child.model.people:
            if merged.model is None:
                merged.model = buildzr.models.Model()
            if merged.model.people is None:
                merged.model.people = []

            existing_ids = {p.id for p in merged.model.people}

            for person in child.model.people:
                if person.id not in existing_ids:
                    merged.model.people.append(person)

        # Merge deployment nodes
        if child.model and child.model.deploymentNodes:
            if merged.model is None:
                merged.model = buildzr.models.Model()
            if merged.model.deploymentNodes is None:
                merged.model.deploymentNodes = []

            existing_ids = {dn.id for dn in merged.model.deploymentNodes}

            for dn in child.model.deploymentNodes:
                if dn.id not in existing_ids:
                    merged.model.deploymentNodes.append(dn)

        # Merge views if present
        if child.views:
            if merged.views is None:
                merged.views = child.views
            else:
                # Merge individual view types
                if child.views.systemLandscapeViews:
                    if merged.views.systemLandscapeViews is None:
                        merged.views.systemLandscapeViews = []
                    merged.views.systemLandscapeViews.extend(child.views.systemLandscapeViews)

                if child.views.systemContextViews:
                    if merged.views.systemContextViews is None:
                        merged.views.systemContextViews = []
                    merged.views.systemContextViews.extend(child.views.systemContextViews)

                if child.views.containerViews:
                    if merged.views.containerViews is None:
                        merged.views.containerViews = []
                    merged.views.containerViews.extend(child.views.containerViews)

                if child.views.componentViews:
                    if merged.views.componentViews is None:
                        merged.views.componentViews = []
                    merged.views.componentViews.extend(child.views.componentViews)

                if child.views.deploymentViews:
                    if merged.views.deploymentViews is None:
                        merged.views.deploymentViews = []
                    merged.views.deploymentViews.extend(child.views.deploymentViews)

        return merged


    def _add_dynamic_attr(self, name: str, model: Union['Person', 'SoftwareSystem', 'Element']) -> None:
        if isinstance(model, Person):
            self._dynamic_attrs[_child_name_transform(name)] = model
            if model._label:
                self._dynamic_attrs[_child_name_transform(model._label)] = model
        elif isinstance(model, SoftwareSystem):
            self._dynamic_attrs[_child_name_transform(name)] = model
            if model._label:
                self._dynamic_attrs[_child_name_transform(model._label)] = model
        elif isinstance(model, Element):
            self._dynamic_attrs[_child_name_transform(name)] = model
            if model._label:
                self._dynamic_attrs[_child_name_transform(model._label)] = model
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a workspace.'.format(type(model)))

    def __getattr__(self, name: str) -> Union['Person', 'SoftwareSystem', 'Element']:
        try:
            return self._dynamic_attrs[name]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __getitem__(self, name: str) -> Union['Person', 'SoftwareSystem', 'Element']:
        # Handle integer keys from failed tuple unpacking attempts
        if isinstance(name, int):
            raise TypeError(
                "Cannot unpack workspace - not extending another workspace. "
                "Use extend='path/to/workspace.json' to enable tuple unpacking."
            )
        return self._dynamic_attrs[_child_name_transform(name)]

    def __dir__(self) -> Iterable[str]:
        return list(super().__dir__()) + list(self._dynamic_attrs.keys())

class SoftwareSystem(DslElementRelationOverrides[
    'SoftwareSystem',
    Union[
        'Person',
        'SoftwareSystem',
        'Container',
        'Component',
        'Element',
    ]
]):
    """
    A software system.
    """

    @property
    def model(self) -> buildzr.models.SoftwareSystem:
        return self._m

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    @property
    def children(self) -> Optional[List['Container']]:
        return self._children

    @property
    def sources(self) -> List[DslElement]:
        return self._sources

    @property
    def destinations(self) -> List[DslElement]:
        return self._destinations

    @property
    def relationships(self) -> Set[DslRelationship]:
        return self._relationships

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def __init__(self, name: str, description: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.SoftwareSystem()
        self.model.containers = []
        self._parent: Optional[Workspace] = None
        self._children: Optional[List['Container']] = []
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._relationships: Set[DslRelationship] = set()
        self._tags = {'Element', 'Software System'}.union(tags)
        self._dynamic_attrs: Dict[str, 'Container'] = {}
        self._label: Optional[str] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.relationships = []
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties
        # Note: location is deprecated in Structurizr - use tags instead for styling
        self.model.location = buildzr.models.Location1.Unspecified
        self.model.documentation = buildzr.models.Documentation()

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.add_model(self)
            workspace._add_dynamic_attr(self.model.name, self)

        stack = _current_group_stack.get()
        if stack:
            stack[-1].add_element(self)

    @classmethod
    def _from_model(cls, model: buildzr.models.SoftwareSystem) -> 'SoftwareSystem':
        """Create DSL wrapper from existing model (for workspace extension)."""
        instance = object.__new__(cls)
        instance._m = model
        instance._parent = None
        instance._children = []
        instance._sources = []
        instance._destinations = []
        instance._relationships = set()
        instance._tags = set(model.tags.split(',')) if model.tags else {'Element', 'Software System'}
        instance._dynamic_attrs = {}
        instance._label = None

        # Ensure containers list is initialized for adding new containers
        if instance._m.containers is None:
            instance._m.containers = []

        # Wrap child containers
        if model.containers:
            for container_model in model.containers:
                container = Container._from_model(container_model, instance)
                instance._children.append(container)
                instance._dynamic_attrs[_child_name_transform(container_model.name or '')] = container

        return instance

    def __enter__(self) -> Self:
        self._token = _current_software_system.set(self)
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_value: Optional[BaseException], traceback: Optional[Any]) -> None:
        _current_software_system.reset(self._token)

    def container(self) -> TypedDynamicAttribute['Container']:
        return TypedDynamicAttribute['Container'](self._dynamic_attrs)

    def add_container(self, container: 'Container') -> None:
        if isinstance(container, Container):
            self.model.containers.append(container.model)
            container._parent = self
            self._add_dynamic_attr(container.model.name, container)
            self._children.append(container)
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a software system.'.format(type(container)))

    def _add_dynamic_attr(self, name: str, model: 'Container') -> None:
        if isinstance(model, Container):
            self._dynamic_attrs[_child_name_transform(name)] = model
            if model._label:
                self._dynamic_attrs[_child_name_transform(model._label)] = model
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a software system.'.format(type(model)))

    def __getattr__(self, name: str) -> 'Container':
        return self._dynamic_attrs[name]

    def __getitem__(self, name: str) -> 'Container':
        return self._dynamic_attrs[_child_name_transform(name)]

    def __dir__(self) -> Iterable[str]:
        return list(super().__dir__()) + list(self._dynamic_attrs.keys())

    def labeled(self, label: str) -> 'SoftwareSystem':
        self._label = label
        workspace = _current_workspace.get()
        if workspace is not None:
            workspace._add_dynamic_attr(label, self)
        return self

class Person(DslElementRelationOverrides[
    'Person',
    Union[
        'Person',
        'SoftwareSystem',
        'Container',
        'Component',
        'Element',
    ]
]):
    """
    A person who uses a software system.
    """

    @property
    def model(self) -> buildzr.models.Person:
        return self._m

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    @property
    def children(self) -> None:
        """
        The `Person` element does not have any children, and will always return
        `None`.
        """
        return None

    @property
    def sources(self) -> List[DslElement]:
        return self._sources

    @property
    def destinations(self) -> List[DslElement]:
        return self._destinations

    @property
    def relationships(self) -> Set[DslRelationship]:
        return self._relationships

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def __init__(self, name: str, description: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.Person()
        self._parent: Optional[Workspace] = None
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._relationships: Set[DslRelationship] = set()
        self._tags = {'Element', 'Person'}.union(tags)
        self._label: Optional[str] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.relationships = []
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties
        # Note: location is deprecated in Structurizr - use tags instead for styling
        self.model.location = buildzr.models.Location.Unspecified

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.add_model(self)

        stack = _current_group_stack.get()
        if stack:
            stack[-1].add_element(self)

    def labeled(self, label: str) -> 'Person':
        self._label = label
        workspace = _current_workspace.get()
        if workspace is not None:
            workspace._add_dynamic_attr(label, self)
        return self

    @classmethod
    def _from_model(cls, model: buildzr.models.Person) -> 'Person':
        """Create DSL wrapper from existing model (for workspace extension)."""
        instance = object.__new__(cls)
        instance._m = model
        instance._parent = None
        instance._sources = []
        instance._destinations = []
        instance._relationships = set()
        instance._tags = set(model.tags.split(',')) if model.tags else {'Element', 'Person'}
        instance._label = None
        return instance


class Element(DslElementRelationOverrides[
    'Element',
    Union[
        'Person',
        'SoftwareSystem',
        'Container',
        'Component',
        'Element',
    ]
]):
    """
    A custom element that sits outside the C4 model.

    Custom elements can be used to represent components that don't fit into
    the standard C4 model hierarchy (e.g., hardware systems, business processes,
    external services). Custom elements can only be displayed in CustomView.

    DSL class name: Element (matches Structurizr DSL syntax)
    Model class: buildzr.models.CustomElement (matches JSON field name)
    """

    @property
    def model(self) -> buildzr.models.CustomElement:
        return self._m

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    @property
    def children(self) -> None:
        """
        The `Element` does not have any children, and will always return
        `None`.
        """
        return None

    @property
    def sources(self) -> List[DslElement]:
        return self._sources

    @property
    def destinations(self) -> List[DslElement]:
        return self._destinations

    @property
    def relationships(self) -> Set[DslRelationship]:
        return self._relationships

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def __init__(
        self,
        name: str,
        metadata: str = "",
        description: str = "",
        tags: Set[str] = set(),
        properties: Dict[str, Any] = dict(),
    ) -> None:
        self._m = buildzr.models.CustomElement()
        self._parent: Optional[Workspace] = None
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._relationships: Set[DslRelationship] = set()
        self._tags = {'Element'}.union(tags)
        self._label: Optional[str] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.metadata = metadata
        self.model.description = description
        self.model.relationships = []
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.add_model(self)

        # Note: Custom elements (Element) do not support groups in Structurizr,
        # so we don't add them to the group stack

    def labeled(self, label: str) -> 'Element':
        self._label = label
        workspace = _current_workspace.get()
        if workspace is not None:
            workspace._add_dynamic_attr(label, self)
        return self

    @classmethod
    def _from_model(cls, model: buildzr.models.CustomElement) -> 'Element':
        """Create DSL wrapper from existing model (for workspace extension)."""
        instance = object.__new__(cls)
        instance._m = model
        instance._parent = None
        instance._sources = []
        instance._destinations = []
        instance._relationships = set()
        instance._tags = set(model.tags.split(',')) if model.tags else {'Element'}
        instance._label = None
        return instance


class Container(DslElementRelationOverrides[
    'Container',
    Union[
        'Person',
        'SoftwareSystem',
        'Container',
        'Component',
        'Element',
    ]
]):
    """
    A container (something that can execute code or host data).
    """

    @property
    def model(self) -> buildzr.models.Container:
        return self._m

    @property
    def parent(self) -> Optional[SoftwareSystem]:
        return self._parent

    @property
    def children(self) -> Optional[List['Component']]:
        return self._children

    @property
    def sources(self) -> List[DslElement]:
        return self._sources

    @property
    def destinations(self) -> List[DslElement]:
        return self._destinations

    @property
    def relationships(self) -> Set[DslRelationship]:
        return self._relationships

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def __init__(self, name: str, description: str="", technology: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.Container()
        self.model.components = []
        self._parent: Optional[SoftwareSystem] = None
        self._children: Optional[List['Component']] = []
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._relationships: Set[DslRelationship] = set()
        self._tags = {'Element', 'Container'}.union(tags)
        self._dynamic_attrs: Dict[str, 'Component'] = {}
        self._label: Optional[str] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.relationships = []
        self.model.technology = technology
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties

        software_system = _current_software_system.get()
        if software_system is not None:
            software_system.add_container(self)
            software_system._add_dynamic_attr(self.model.name, self)

        stack = _current_group_stack.get()
        if stack:
            stack[-1].add_element(self)

    @classmethod
    def _from_model(cls, model: buildzr.models.Container, parent: 'SoftwareSystem') -> 'Container':
        """Create DSL wrapper from existing model (for workspace extension)."""
        instance = object.__new__(cls)
        instance._m = model
        instance._parent = parent
        instance._children = []
        instance._sources = []
        instance._destinations = []
        instance._relationships = set()
        instance._tags = set(model.tags.split(',')) if model.tags else {'Element', 'Container'}
        instance._dynamic_attrs = {}
        instance._label = None

        # Ensure components list is initialized for adding new components
        if instance._m.components is None:
            instance._m.components = []

        # Wrap child components
        if model.components:
            for component_model in model.components:
                component = Component._from_model(component_model, instance)
                instance._children.append(component)
                instance._dynamic_attrs[_child_name_transform(component_model.name or '')] = component

        return instance

    def __enter__(self) -> Self:
        self._token = _current_container.set(self)
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_value: Optional[BaseException], traceback: Optional[Any]) -> None:
        _current_container.reset(self._token)

    def labeled(self, label: str) -> 'Container':
        self._label = label
        software_system = _current_software_system.get()
        if software_system is not None:
            software_system._add_dynamic_attr(label, self)
        return self

    def component(self) -> TypedDynamicAttribute['Component']:
        return TypedDynamicAttribute['Component'](self._dynamic_attrs)

    def add_component(self, component: 'Component') -> None:
        if isinstance(component, Component):
            self.model.components.append(component.model)
            component._parent = self
            self._add_dynamic_attr(component.model.name, component)
            self._children.append(component)
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a container.'.format(type(component)))

    def _add_dynamic_attr(self, name: str, model: 'Component') -> None:
        if isinstance(model, Component):
            self._dynamic_attrs[_child_name_transform(name)] = model
            if model._label:
                self._dynamic_attrs[_child_name_transform(model._label)] = model
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a container.'.format(type(model)))

    def __getattr__(self, name: str) -> 'Component':
        return self._dynamic_attrs[name]

    def __getitem__(self, name: str) -> 'Component':
        return self._dynamic_attrs[_child_name_transform(name)]

    def __dir__(self) -> Iterable[str]:
        return list(super().__dir__()) + list(self._dynamic_attrs.keys())

class Component(DslElementRelationOverrides[
    'Component',
    Union[
        'Person',
        'SoftwareSystem',
        'Container',
        'Component',
        'Element',
    ]
]):
    """
    A component (a grouping of related functionality behind an interface that runs inside a container).
    """

    @property
    def model(self) -> buildzr.models.Component:
        return self._m

    @property
    def parent(self) -> Optional[Container]:
        return self._parent

    @property
    def children(self) -> None:
        return None

    @property
    def sources(self) -> List[DslElement]:
        return self._sources

    @property
    def destinations(self) -> List[DslElement]:
        return self._destinations

    @property
    def relationships(self) -> Set[DslRelationship]:
        return self._relationships

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def __init__(self, name: str, description: str="", technology: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.Component()
        self._parent: Optional[Container] = None
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._relationships: Set[DslRelationship] = set()
        self._tags = {'Element', 'Component'}.union(tags)
        self._label: Optional[str] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.technology = technology
        self.model.relationships = []
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties

        container = _current_container.get()
        if container is not None:
            container.add_component(self)
            container._add_dynamic_attr(self.model.name, self)

        stack = _current_group_stack.get()
        if stack:
            stack[-1].add_element(self)

    def labeled(self, label: str) -> 'Component':
        self._label = label
        container = _current_container.get()
        if container is not None:
            container._add_dynamic_attr(label, self)
        return self

    @classmethod
    def _from_model(cls, model: buildzr.models.Component, parent: 'Container') -> 'Component':
        """Create DSL wrapper from existing model (for workspace extension)."""
        instance = object.__new__(cls)
        instance._m = model
        instance._parent = parent
        instance._sources = []
        instance._destinations = []
        instance._relationships = set()
        instance._tags = set(model.tags.split(',')) if model.tags else {'Element', 'Component'}
        instance._label = None
        return instance


class Group:

    def __init__(
        self,
        name: str,
        workspace: Optional[Workspace]=None,
    ) -> None:

        if not workspace:
            workspace = _current_workspace.get()
            if workspace is not None:
                self._group_separator = workspace._group_separator

        self._group_separator = workspace._group_separator
        self._name = name

        if len(self._group_separator) > 1:
            raise ValueError('Group separator must be a single character.')

        if self._group_separator in self._name:
            raise ValueError('Group name cannot contain the group separator.')

        stack = _current_group_stack.get()
        new_stack = stack.copy()
        new_stack.extend([self])

        self._full_name = self._group_separator.join([group._name for group in new_stack])

    def full_name(self) -> str:
        return self._full_name

    def add_element(
        self,
        model: Union[
            'Person',
            'SoftwareSystem',
            'Container',
            'Component',
        ]
    ) -> None:


        model.model.group = self._full_name

    def __enter__(self) -> Self:
        stack = _current_group_stack.get() # stack: a/b
        stack.extend([self]) # stack: a/b -> a/b/self
        self._token = _current_group_stack.set(stack)
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[Any]
    ) -> None:
        stack = _current_group_stack.get()
        stack.pop() # stack: a/b/self -> a/b
        _current_group_stack.reset(self._token)

_RankDirection = Literal['tb', 'bt', 'lr', 'rl']

_AutoLayout = Optional[
    Union[
        _RankDirection,
        Tuple[_RankDirection, float],
        Tuple[_RankDirection, float, float]
    ]
]

class DeploymentEnvironment(DslDeploymentEnvironment):

    def __init__(self, name: str) -> None:
        self._name = name
        self._parent: Optional[Workspace] = None
        self._children: Optional[List['DeploymentNode']] = []

        workspace = _current_workspace.get()
        if workspace is not None:
            self._parent = workspace

    @property
    def name(self) -> str:
        return self._name

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    @property
    def children(self) -> Optional[List['DeploymentNode']]:
        return self._children

    def add_deployment_node(self, node: 'DeploymentNode') -> None:
        node._m.environment = self._name

    def __enter__(self) -> Self:
        self._token = _current_deployment_environment.set(self)
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_value: Optional[BaseException], traceback: Optional[Any]) -> None:
        _current_deployment_environment.reset(self._token)

        if self._parent is not None:
            self._imply_software_system_instance_relationships(self._parent)
            self._imply_container_instance_relationships(self._parent)

    def _imply_software_system_instance_relationships(self, workspace: Workspace) -> None:

        from buildzr.dsl.expression import Expression

        """
        Process implied instance relationships. For example, if we have a
        relationship between two software systems, and the software system
        instances of those software systems exists, then we need to create a
        new relationship between those software system instances.

        These implied relationships are used in `DeploymentView`.

        Relationships are only created between instances that share at least
        one common deployment group. If no deployment groups are specified,
        instances are considered to be in the same default group.
        """

        software_instances = [
            cast('SoftwareSystemInstance', e) for e in Expression(include_elements=[
                lambda w, e: e.type == SoftwareSystemInstance,
            ]).elements(workspace)
        ]

        software_instance_map: Dict[str, List['SoftwareSystemInstance']] = {}
        for software_instance in software_instances:
            software_id = software_instance.model.softwareSystemId
            if software_id not in software_instance_map:
                software_instance_map[software_id] = []
            software_instance_map[software_id].append(software_instance)

        softwares = [
            cast('SoftwareSystem', e) for e in Expression(include_elements=[
                lambda w, e: e.type == SoftwareSystem,
            ]).elements(workspace)
        ]

        for software in softwares:

            other_softwares_ids = {
                s.model.id for s in softwares
                if s.model.id != software.model.id
            }

            if not software.model.relationships:
                continue

            for relationship in software.model.relationships:
                if not relationship.destinationId in other_softwares_ids:
                    continue

                if software.model.id not in software_instance_map:
                    continue

                if relationship.destinationId not in software_instance_map:
                    continue

                this_software_instances = software_instance_map[software.model.id]
                other_software_instances = software_instance_map[relationship.destinationId]

                for this_software_instance in this_software_instances:
                    for other_software_instance in other_software_instances:

                        # Only create relationship if instances share a deployment group
                        if not self._instances_share_deployment_group(
                            this_software_instance,
                            other_software_instance
                        ):
                            continue

                        already_exists = this_software_instance.model.relationships is not None and any(
                            r.sourceId == this_software_instance.model.id and
                            r.destinationId == other_software_instance.model.id and
                            r.description == relationship.description and
                            r.technology == relationship.technology
                            for r in this_software_instance.model.relationships
                        )

                        if not already_exists:
                            # Note: tags aren't carried over.
                            r = this_software_instance.uses(
                                other_software_instance,
                                description=relationship.description,
                                technology=relationship.technology,
                            )
                            r.model.linkedRelationshipId = relationship.id

    def _instances_share_deployment_group(
        self,
        instance1: Union['ContainerInstance', 'SoftwareSystemInstance'],
        instance2: Union['ContainerInstance', 'SoftwareSystemInstance']
    ) -> bool:
        """
        Check if two deployment instances share at least one common deployment group.

        If either instance has no deployment groups specified, they are considered
        to be in the "default" group and can relate to all other instances without
        deployment groups.

        Args:
            instance1: First deployment instance
            instance2: Second deployment instance

        Returns:
            True if instances share at least one deployment group or if both have
            no deployment groups specified, False otherwise.
        """
        groups1 = set(instance1.model.deploymentGroups or [])
        groups2 = set(instance2.model.deploymentGroups or [])

        # If both have no deployment groups, they can relate
        if not groups1 and not groups2:
            return True

        # If one has groups and the other doesn't, they cannot relate
        if (groups1 and not groups2) or (not groups1 and groups2):
            return False

        # Check if they share at least one common group
        return bool(groups1.intersection(groups2))

    def _imply_container_instance_relationships(self, workspace: Workspace) -> None:

        """
        Process implied instance relationships. For example, if we have a
        relationship between two containers, and the container instances of
        those containers exists, then we need to create a new relationship
        between those container instances.

        These implied relationships are used in `DeploymentView`.

        Relationships are only created between instances that share at least
        one common deployment group. If no deployment groups are specified,
        instances are considered to be in the same default group.
        """

        from buildzr.dsl.expression import Expression

        container_instances = [
            cast('ContainerInstance', e) for e in Expression(include_elements=[
                lambda w, e: e.type == ContainerInstance,
        ]).elements(workspace)]

        container_instance_map: Dict[str, List['ContainerInstance']] = {}
        for container_instance in container_instances:
            container_id = container_instance.model.containerId
            if container_id not in container_instance_map:
                container_instance_map[container_id] = []
            container_instance_map[container_id].append(container_instance)

        containers = [
            cast('ContainerInstance', e) for e in Expression(include_elements=[
                lambda w, e: e.type == Container,
        ]).elements(workspace)]

        for container in containers:

            other_containers_ids = {
                c.model.id for c in containers
                if c.model.id != container.model.id
            }

            if not container.model.relationships:
                continue

            for relationship in container.model.relationships:

                if not relationship.destinationId in other_containers_ids:
                    continue

                if container.model.id not in container_instance_map:
                    continue

                if relationship.destinationId not in container_instance_map:
                    continue

                this_container_instances = container_instance_map[container.model.id]
                other_container_instances = container_instance_map[relationship.destinationId]

                for this_container_instance in this_container_instances:
                    for other_container_instance in other_container_instances:

                        # Only create relationship if instances share a deployment group
                        if not self._instances_share_deployment_group(
                            this_container_instance,
                            other_container_instance
                        ):
                            continue

                        already_exists = this_container_instance.model.relationships is not None and any(
                            r.sourceId == this_container_instance.model.id and
                            r.destinationId == other_container_instance.model.id and
                            r.description == relationship.description and
                            r.technology == relationship.technology
                            for r in this_container_instance.model.relationships
                        )

                        if not already_exists:
                            # Note: tags aren't carried over.
                            r = this_container_instance.uses(
                                other_container_instance,
                                description=relationship.description,
                                technology=relationship.technology,
                            )
                            r.model.linkedRelationshipId = relationship.id


class DeploymentNode(DslDeploymentNodeElement, DslElementRelationOverrides[
    'DeploymentNode',
    'DeploymentNode'
]):

    def __init__(self, name: str, description: str="", technology: str="", tags: Set[str]=set(), instances: str="1") -> None:
        self._m = buildzr.models.DeploymentNode()
        self._m.instances = instances
        self._m.id = GenerateId.for_element()
        self._m.name = name
        self._m.children = []
        self._m.softwareSystemInstances = []
        self._m.containerInstances = []
        self._m.infrastructureNodes = []
        self._m.description = description
        self._m.technology = technology
        self._parent: Optional[Workspace] = None
        self._children: Optional[List[
            Union[
                'SoftwareSystemInstance',
                'ContainerInstance',
                'InfrastructureNode',
                'DeploymentNode']]
            ] = []
        self._tags = {'Element', 'Deployment Node'}.union(tags)
        self._m.tags = ','.join(self._tags)

        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._relationships: Set[DslRelationship] = set()

        # If the deployment stack is not empty, then we're inside the context of
        # another deployment node. Otherwise, we're at the root of the
        # workspace.
        stack = _current_deployment_node_stack.get()
        if stack:
            stack[-1].add_deployment_node(self)
        else:
            workspace = _current_workspace.get()
            if workspace:
                self._parent = workspace
                workspace.add_model(self)

        deployment_environment = _current_deployment_environment.get()
        if deployment_environment is not None:
            self._m.environment = deployment_environment.name
            deployment_environment.add_deployment_node(self)

    @property
    def model(self) -> buildzr.models.DeploymentNode:
        return self._m

    @property
    def tags(self) -> Set[str]:
        return self._tags

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    @property
    def children(self) -> Optional[List[Union['SoftwareSystemInstance', 'ContainerInstance', 'InfrastructureNode', 'DeploymentNode']]]:
        return self._children

    @property
    def destinations(self) -> List[DslElement]:
        return self._destinations

    @property
    def sources(self) -> List[DslElement]:
        return self._sources

    @property
    def relationships(self) -> Set[DslRelationship]:
        return self._relationships

    def __enter__(self) -> Self:
        stack = _current_deployment_node_stack.get()
        stack.extend([self])
        self._token = _current_deployment_node_stack.set(stack)
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[Any]
    ) -> None:
        stack = _current_deployment_node_stack.get()
        stack.pop()
        _current_deployment_node_stack.reset(self._token)

    def add_infrastructure_node(self, node: 'InfrastructureNode') -> None:
        self._m.infrastructureNodes.append(node.model)
        self._children.append(node)

    def add_element_instance(self, instance: Union['SoftwareSystemInstance', 'ContainerInstance']) -> None:
        if isinstance(instance, SoftwareSystemInstance):
            self._m.softwareSystemInstances.append(instance.model)
        elif isinstance(instance, ContainerInstance):
            self._m.containerInstances.append(instance.model)
        self._children.append(instance)

    def add_deployment_node(self, node: 'DeploymentNode') -> None:
        self._m.children.append(node.model)
        self._children.append(node)

class InfrastructureNode(DslInfrastructureNodeElement, DslElementRelationOverrides[
    'InfrastructureNode',
    Union[
        'DeploymentNode',
        'InfrastructureNode',
        'SoftwareSystemInstance',
        'ContainerInstance',
    ]
]):

    def __init__(self, name: str, description: str="", technology: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.InfrastructureNode()
        self._m.id = GenerateId.for_element()
        self._m.name = name
        self._m.description = description
        self._m.technology = technology
        self._m.properties = properties
        self._parent: Optional[DeploymentNode] = None
        self._tags = {'Element', 'Infrastructure Node'}.union(tags)
        self._m.tags = ','.join(self._tags)

        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._relationships: Set[DslRelationship] = set()

        stack = _current_deployment_node_stack.get()
        if stack:
            stack[-1].add_infrastructure_node(self)

        deployment_environment = _current_deployment_environment.get()
        if deployment_environment is not None:
            self._m.environment = deployment_environment.name

    @property
    def model(self) -> buildzr.models.InfrastructureNode:
        return self._m

    @property
    def tags(self) -> Set[str]:
        return self._tags

    @property
    def parent(self) -> Optional[DeploymentNode]:
        return self._parent

    @property
    def children(self) -> None:
        """
        The `InfrastructureNode` element does not have any children, and will always return
        `None`.
        """
        return None

    @property
    def sources(self) -> List[DslElement]:
        return self._sources

    @property
    def destinations(self) -> List[DslElement]:
        return self._destinations

    @property
    def relationships(self) -> Set[DslRelationship]:
        return self._relationships

class SoftwareSystemInstance(DslElementInstance, DslElementRelationOverrides[
    'SoftwareSystemInstance',
    'InfrastructureNode',
]):

    def __init__(
        self,
        software_system: 'SoftwareSystem',
        deployment_groups: Optional[List['DeploymentGroup']]=None,
        tags: Set[str]=set(),
    ) -> None:
        self._m = buildzr.models.SoftwareSystemInstance()
        self._m.id = GenerateId.for_element()
        self._m.softwareSystemId = software_system.model.id
        self._parent: Optional[DeploymentNode] = None
        self._element = software_system
        self._m.deploymentGroups = [g.name for g in deployment_groups] if deployment_groups else ["Default"]
        self._tags = {'Software System Instance'}.union(tags)
        self._m.tags = ','.join(self._tags)

        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._relationships: Set[DslRelationship] = set()

        stack = _current_deployment_node_stack.get()
        if stack:
            self._parent = stack[-1]
            self._parent.add_element_instance(self)

        deployment_environment = _current_deployment_environment.get()
        if deployment_environment is not None:
            self._m.environment = deployment_environment.name

    @property
    def model(self) -> buildzr.models.SoftwareSystemInstance:
        return self._m

    @property
    def tags(self) -> Set[str]:
        return self._tags

    @property
    def parent(self) -> Optional[DeploymentNode]:
        return self._parent

    @property
    def children(self) -> None:
        """
        The `SoftwareSystemInstance` element does not have any children, and will always return
        `None`.
        """
        return None

    @property
    def destinations(self) -> List[DslElement]:
        return self._destinations

    @property
    def sources(self) -> List[DslElement]:
        return self._sources

    @property
    def relationships(self) -> Set[DslRelationship]:
        return self._relationships

    @property
    def element(self) -> DslElement:
        return self._element

class ContainerInstance(DslElementInstance, DslElementRelationOverrides[
    'ContainerInstance',
    'InfrastructureNode',
]):

    def __init__(
        self,
        container: 'Container',
        deployment_groups: Optional[List['DeploymentGroup']]=None,
        tags: Set[str]=set(),
    ) -> None:
        self._m = buildzr.models.ContainerInstance()
        self._m.id = GenerateId.for_element()
        self._m.containerId = container.model.id
        self._parent: Optional[DeploymentNode] = None
        self._element = container
        self._m.deploymentGroups = [g.name for g in deployment_groups] if deployment_groups else ["Default"]
        self._tags = {'Container Instance'}.union(tags)
        self._m.tags = ','.join(self._tags)

        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._relationships: Set[DslRelationship] = set()

        stack = _current_deployment_node_stack.get()
        if stack:
            self._parent = stack[-1]
            self._parent.add_element_instance(self)

        deployment_environment = _current_deployment_environment.get()
        if deployment_environment is not None:
            self._m.environment = deployment_environment.name

    @property
    def model(self) -> buildzr.models.ContainerInstance:
        return self._m

    @property
    def tags(self) -> Set[str]:
        return self._tags

    @property
    def parent(self) -> Optional[DeploymentNode]:
        return self._parent

    @property
    def children(self) -> None:
        """
        The `ContainerInstance` element does not have any children, and will always return
        `None`.
        """
        return None

    @property
    def sources(self) -> List[DslElement]:
        return self._sources

    @property
    def destinations(self) -> List[DslElement]:
        return self._destinations

    @property
    def relationships(self) -> Set[DslRelationship]:
        return self._relationships

    @property
    def element(self) -> DslElement:
        return self._element

class DeploymentGroup:

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

def _auto_layout_to_model(auto_layout: _AutoLayout) -> buildzr.models.AutomaticLayout:
    """
    See: https://docs.structurizr.com/dsl/language#autolayout
    """

    model = buildzr.models.AutomaticLayout()

    def is_auto_layout_with_rank_separation(\
        auto_layout: _AutoLayout,
    ) -> TypeIs[Tuple[_RankDirection, float]]:
        if isinstance(auto_layout, tuple):
            return len(auto_layout) == 2 and \
                    type(auto_layout[0]) is _RankDirection and \
                    type(auto_layout[1]) is float
        return False

    def is_auto_layout_with_node_separation(\
        auto_layout: _AutoLayout,
    ) -> TypeIs[Tuple[_RankDirection, float, float]]:
        if isinstance(auto_layout, tuple) and len(auto_layout) == 3:
            return type(auto_layout[0]) is _RankDirection and \
                   all([type(x) is float for x in auto_layout[1:]])
        return False

    map_rank_direction: Dict[_RankDirection, buildzr.models.RankDirection] = {
        'lr': buildzr.models.RankDirection.LeftRight,
        'tb': buildzr.models.RankDirection.TopBottom,
        'rl': buildzr.models.RankDirection.RightLeft,
        'bt': buildzr.models.RankDirection.BottomTop,
    }

    if auto_layout is not None:
        if is_auto_layout_with_rank_separation(auto_layout):
            d, rs = cast(Tuple[_RankDirection, float], auto_layout)
            model.rankDirection = map_rank_direction[cast(_RankDirection, d)]
            model.rankSeparation = rs
        elif is_auto_layout_with_node_separation(auto_layout):
            d, rs, ns = cast(Tuple[_RankDirection, float, float], auto_layout)
            model.rankDirection = map_rank_direction[cast(_RankDirection, d)]
            model.rankSeparation = rs
            model.nodeSeparation = ns
        else:
            model.rankDirection = map_rank_direction[cast(_RankDirection, auto_layout)]

    if model.rankSeparation is None:
        model.rankSeparation = 300
    if model.nodeSeparation is None:
        model.nodeSeparation = 300
    if model.edgeSeparation is None:
        model.edgeSeparation = 0
    if model.implementation is None:
        model.implementation = buildzr.models.Implementation.Graphviz
    if model.vertices is None:
        model.vertices = False

    return model

class SystemLandscapeView(DslViewElement):

    from buildzr.dsl.expression import Expression, WorkspaceExpression, ElementExpression, RelationshipExpression

    @property
    def model(self) -> buildzr.models.SystemLandscapeView:
        return self._m

    def __init__(
        self,
        key: str,
        description: str,
        auto_layout: _AutoLayout='tb',
        title: Optional[str]=None,
        include_elements: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]]=[],
        exclude_elements: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]]=[],
        include_relationships: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]]=[],
        exclude_relationships: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]]=[],
        properties: Optional[Dict[str, str]]=None,
    ) -> None:
        self._m = buildzr.models.SystemLandscapeView()

        self._m.key = key
        self._m.description = description

        self._m.automaticLayout = _auto_layout_to_model(auto_layout)
        self._m.title = title
        self._m.properties = properties

        self._include_elements = include_elements
        self._exclude_elements = exclude_elements
        self._include_relationships = include_relationships
        self._exclude_relationships = exclude_relationships

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_view(self)

    def _on_added(self, workspace: Workspace) -> None:

        from buildzr.dsl.expression import Expression, WorkspaceExpression, ElementExpression, RelationshipExpression
        from buildzr.models import ElementView, RelationshipView

        expression = Expression(
            include_elements=self._include_elements,
            exclude_elements=self._exclude_elements,
            include_relationships=self._include_relationships,
            exclude_relationships=self._exclude_relationships,
        )

        include_view_elements_filter: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]] = [
            lambda w, e: e.type == Person,
            lambda w, e: e.type == SoftwareSystem,
            lambda w, e: e.type == Element,
        ]

        exclude_view_elements_filter: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]] = [
            lambda w, e: e.type == Container,
            lambda w, e: e.type == Component,
        ]

        include_view_relationships_filter: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]] = [
            lambda w, r: r.source.type == Person,
            lambda w, r: r.source.type == SoftwareSystem,
            lambda w, r: r.source.type == Element,
            lambda w, r: r.destination.type == Person,
            lambda w, r: r.destination.type == SoftwareSystem,
            lambda w, r: r.destination.type == Element,
        ]

        expression = Expression(
            include_elements=self._include_elements + include_view_elements_filter,
            exclude_elements=self._exclude_elements + exclude_view_elements_filter,
            include_relationships=self._include_relationships + include_view_relationships_filter,
            exclude_relationships=self._exclude_relationships,
        )

        element_ids = map(
            lambda x: str(x.model.id),
            expression.elements(workspace)
        )

        relationship_ids = map(
            lambda x: str(x.model.id),
            expression.relationships(workspace)
        )

        self._m.elements = []
        for element_id in element_ids:
            # Add x, y coordinates (required by Structurizr for rendering)
            self._m.elements.append(ElementView(id=element_id, x=0, y=0))

        self._m.relationships = []
        for relationship_id in relationship_ids:
            self._m.relationships.append(RelationshipView(id=relationship_id))

class SystemContextView(DslViewElement):

    """
    If no filter is applied, this view includes all elements that have a direct
    relationship with the selected `SoftwareSystem`.
    """

    from buildzr.dsl.expression import Expression, WorkspaceExpression, ElementExpression, RelationshipExpression

    @property
    def model(self) -> buildzr.models.SystemContextView:
        return self._m

    def __init__(
        self,
        software_system_selector: Union[SoftwareSystem, Callable[[WorkspaceExpression], SoftwareSystem]],
        key: str,
        description: str,
        auto_layout: _AutoLayout='tb',
        title: Optional[str]=None,
        include_elements: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]]=[],
        exclude_elements: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]]=[],
        include_relationships: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]]=[],
        exclude_relationships: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]]=[],
        properties: Optional[Dict[str, str]]=None,
    ) -> None:
        self._m = buildzr.models.SystemContextView()

        self._m.key = key
        self._m.description = description

        self._m.automaticLayout = _auto_layout_to_model(auto_layout)
        # Add applied field to automaticLayout (required by Structurizr)
        if self._m.automaticLayout:
            self._m.automaticLayout.applied = False

        self._m.title = title
        self._m.properties = properties
        # Add enterprise boundary visibility and order (required by Structurizr)
        self._m.enterpriseBoundaryVisible = True
        self._m.order = 1

        self._selector = software_system_selector
        self._include_elements = include_elements
        self._exclude_elements = exclude_elements
        self._include_relationships = include_relationships
        self._exclude_relationships = exclude_relationships

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_view(self)

    def _on_added(self, workspace: Workspace) -> None:

        from buildzr.dsl.expression import Expression, WorkspaceExpression, ElementExpression, RelationshipExpression
        from buildzr.models import ElementView, RelationshipView

        if isinstance(self._selector, SoftwareSystem):
            software_system = self._selector
        else:
            software_system = self._selector(WorkspaceExpression(workspace))
        self._m.softwareSystemId = software_system.model.id
        view_elements_filter: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]] = [
            lambda w, e: e == software_system,
            lambda w, e: software_system.model.id in e.sources.ids,
            lambda w, e: software_system.model.id in e.destinations.ids,
        ]

        view_relationships_filter: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]] = [
            lambda w, r: software_system == r.source,
            lambda w, r: software_system == r.destination,
        ]

        expression = Expression(
            include_elements=self._include_elements + view_elements_filter,
            exclude_elements=self._exclude_elements,
            include_relationships=self._include_relationships + view_relationships_filter,
            exclude_relationships=self._exclude_relationships,
        )

        element_ids = map(
            lambda x: str(x.model.id),
            expression.elements(workspace)
        )

        relationship_ids = map(
            lambda x: str(x.model.id),
            expression.relationships(workspace)
        )

        self._m.elements = []
        for element_id in element_ids:
            # Add x, y coordinates (required by Structurizr for rendering)
            self._m.elements.append(ElementView(id=element_id, x=0, y=0))

        self._m.relationships = []
        for relationship_id in relationship_ids:
            self._m.relationships.append(RelationshipView(id=relationship_id))

class ContainerView(DslViewElement):

    from buildzr.dsl.expression import Expression, WorkspaceExpression, ElementExpression, RelationshipExpression

    @property
    def model(self) -> buildzr.models.ContainerView:
        return self._m

    def __init__(
        self,
        software_system_selector: Union[SoftwareSystem, Callable[[WorkspaceExpression], SoftwareSystem]],
        key: str,
        description: str,
        auto_layout: _AutoLayout='tb',
        title: Optional[str]=None,
        include_elements: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]]=[],
        exclude_elements: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]]=[],
        include_relationships: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]]=[],
        exclude_relationships: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]]=[],
        properties: Optional[Dict[str, str]]=None,
    ) -> None:
        self._m = buildzr.models.ContainerView()

        self._m.key = key
        self._m.description = description

        self._m.automaticLayout = _auto_layout_to_model(auto_layout)
        self._m.title = title
        self._m.properties = properties

        self._selector = software_system_selector
        self._include_elements = include_elements
        self._exclude_elements = exclude_elements
        self._include_relationships = include_relationships
        self._exclude_relationships = exclude_relationships

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_view(self)

    def _on_added(self, workspace: Workspace) -> None:

        from buildzr.dsl.expression import Expression, WorkspaceExpression, ElementExpression, RelationshipExpression
        from buildzr.models import ElementView, RelationshipView

        if isinstance(self._selector, SoftwareSystem):
            software_system = self._selector
        else:
            software_system = self._selector(WorkspaceExpression(workspace))
        self._m.softwareSystemId = software_system.model.id

        container_ids = { container.model.id for container in software_system.children}

        view_elements_filter: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]] = [
            lambda w, e: e.parent == software_system,
            lambda w, e: any(container_ids.intersection({ id for id in e.sources.ids })),
            lambda w, e: any(container_ids.intersection({ id for id in e.destinations.ids })),
        ]

        view_relationships_filter: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]] = [
            lambda w, r: software_system == r.source.parent,
            lambda w, r: software_system == r.destination.parent,
        ]

        expression = Expression(
            include_elements=self._include_elements + view_elements_filter,
            exclude_elements=self._exclude_elements,
            include_relationships=self._include_relationships + view_relationships_filter,
            exclude_relationships=self._exclude_relationships,
        )

        element_ids = map(
            lambda x: str(x.model.id),
            expression.elements(workspace)
        )

        relationship_ids = map(
            lambda x: str(x.model.id),
            expression.relationships(workspace)
        )

        self._m.elements = []
        for element_id in element_ids:
            # Add x, y coordinates (required by Structurizr for rendering)
            self._m.elements.append(ElementView(id=element_id, x=0, y=0))

        self._m.relationships = []
        for relationship_id in relationship_ids:
            self._m.relationships.append(RelationshipView(id=relationship_id))

class ComponentView(DslViewElement):

    from buildzr.dsl.expression import Expression, WorkspaceExpression, ElementExpression, RelationshipExpression

    @property
    def model(self) -> buildzr.models.ComponentView:
        return self._m

    def __init__(
        self,
        container_selector: Union[Container, Callable[[WorkspaceExpression], Container]],
        key: str,
        description: str,
        auto_layout: _AutoLayout='tb',
        title: Optional[str]=None,
        include_elements: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]]=[],
        exclude_elements: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]]=[],
        include_relationships: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]]=[],
        exclude_relationships: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]]=[],
        properties: Optional[Dict[str, str]]=None,
    ) -> None:
        self._m = buildzr.models.ComponentView()

        self._m.key = key
        self._m.description = description

        self._m.automaticLayout = _auto_layout_to_model(auto_layout)
        self._m.title = title
        self._m.properties = properties

        self._selector = container_selector
        self._include_elements = include_elements
        self._exclude_elements = exclude_elements
        self._include_relationships = include_relationships
        self._exclude_relationships = exclude_relationships

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_view(self)

    def _on_added(self, workspace: Workspace) -> None:

        from buildzr.dsl.expression import Expression, WorkspaceExpression, ElementExpression, RelationshipExpression
        from buildzr.models import ElementView, RelationshipView

        container: Container
        if isinstance(self._selector, Container):
            container = self._selector
        else:
            container = self._selector(WorkspaceExpression(workspace))
        self._m.containerId = container.model.id

        component_ids = { component.model.id for component in container.children or [] }

        view_elements_filter: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]] = [
            lambda w, e: e.parent == container,
            lambda w, e: any(component_ids.intersection({ id for id in e.sources.ids })),
            lambda w, e: any(component_ids.intersection({ id for id in e.destinations.ids })),
        ]

        view_relationships_filter: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]] = [
            lambda w, r: container == r.source.parent,
            lambda w, r: container == r.destination.parent,
        ]

        expression = Expression(
            include_elements=self._include_elements + view_elements_filter,
            exclude_elements=self._exclude_elements,
            include_relationships=self._include_relationships + view_relationships_filter,
            exclude_relationships=self._exclude_relationships,
        )

        element_ids = map(
            lambda x: str(x.model.id),
            expression.elements(workspace)
        )

        relationship_ids = map(
            lambda x: str(x.model.id),
            expression.relationships(workspace)
        )

        self._m.elements = []
        for element_id in element_ids:
            # Add x, y coordinates (required by Structurizr for rendering)
            self._m.elements.append(ElementView(id=element_id, x=0, y=0))

        self._m.relationships = []
        for relationship_id in relationship_ids:
            self._m.relationships.append(RelationshipView(id=relationship_id))

class DeploymentView(DslViewElement):

    from buildzr.dsl.expression import Expression, WorkspaceExpression, ElementExpression, RelationshipExpression

    @property
    def model(self) -> buildzr.models.DeploymentView:
        return self._m

    def __init__(
        self,
        environment: DeploymentEnvironment,
        key: str,
        software_system_selector: Optional[Union[SoftwareSystem, Callable[[WorkspaceExpression], SoftwareSystem]]]=None,
        description: str="",
        auto_layout: _AutoLayout='tb',
        title: Optional[str]=None,
        include_elements: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]]=[],
        exclude_elements: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]]=[],
        include_relationships: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]]=[],
        exclude_relationships: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]]=[],
        properties: Optional[Dict[str, str]]=None,
    ) -> None:
        self._m = buildzr.models.DeploymentView()

        self._selector = software_system_selector
        self._environment = environment

        self._m.key = key
        self._m.description = description
        self._m.environment = environment.name

        self._m.automaticLayout = _auto_layout_to_model(auto_layout)
        self._m.title = title
        self._m.properties = properties

        self._include_elements = include_elements
        self._exclude_elements = exclude_elements
        self._include_relationships = include_relationships
        self._exclude_relationships = exclude_relationships

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_view(self)

    def _on_added(self, workspace: Workspace) -> None:

        from buildzr.dsl.expression import Expression, WorkspaceExpression, ElementExpression, RelationshipExpression
        from buildzr.dsl.explorer import Explorer
        from buildzr.models import ElementView, RelationshipView

        software_system: Optional[SoftwareSystem] = None
        if self._selector is not None:
            if isinstance(self._selector, SoftwareSystem):
                software_system = self._selector
                self._m.softwareSystemId = software_system.model.id
            else:
                software_system = self._selector(WorkspaceExpression(workspace))
                self._m.softwareSystemId = software_system.model.id

        view_elements_filter: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]] = []
        view_elements_filter_excludes: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]] = []
        view_relationships_filter_env: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]] = []
        view_relationships_filter_implied_instance_relationships: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]] = []

        def is_software_system_contains_container(
            software_system_id: str,
            container_id: str,
        ) -> bool:
            for software_system in workspace.model.model.softwareSystems:
                if software_system.id == software_system_id:
                    for container in software_system.containers:
                        if container.id == container_id:
                            return True
            return False

        def recursive_includes(
            deployment_node_ancestor_ids: List[str],
            deployment_node: buildzr.models.DeploymentNode,
            upstream_software_system_ids: Set[str],
            environment: str,
            include_ids: Set[str],
            selected_software_system: Optional[buildzr.models.SoftwareSystem] = None,
        ) -> None:

            """
            Recursively includes the relevant deployment nodes, software system
            instances, container instances, and infrastructure nodes based on
            the provided environment and DeploymentView parameters.

            @param deployment_node_ancestor_ids: List of ancestor deployment
            node IDs. Useful for tracing back the upstream deployment nodes that
            should be included in the view. For example, we may have deployment nodes
            `a` -> `b` -> `c`, and we want to include all of them if `c` is included,
            even if `b` has no software system instances, container instances,
            or infrastructure nodes.

            @param upstream_software_system_ids: Set of software system IDs that
            whose instance exists in the upstream deployment nodes.
            """

            instance_ids: Set[str] = set()
            for child in deployment_node.children:
                if child.environment == environment:
                    recursive_includes(
                        deployment_node_ancestor_ids + [deployment_node.id],
                        child,
                        upstream_software_system_ids.union({
                            software_system_instance.softwareSystemId
                            for software_system_instance in deployment_node.softwareSystemInstances
                        }),
                        environment,
                        include_ids,
                        selected_software_system
                    )

            if selected_software_system is None:
                software_instance_ids = {
                    instance.id for instance in deployment_node.softwareSystemInstances
                    if instance.environment == environment
                }

                sibling_software_system_ids = {
                    instance.softwareSystemId for instance in deployment_node.softwareSystemInstances
                    if instance.environment == environment
                }

                container_instance_ids = {
                    instance.id for instance in deployment_node.containerInstances
                    if instance.environment == environment and \
                       not any({
                            is_software_system_contains_container(
                                software_system_id,
                                instance.containerId
                            ) for software_system_id in upstream_software_system_ids.union(sibling_software_system_ids)
                       })
                }

                instance_ids.update(software_instance_ids)
                instance_ids.update(container_instance_ids)

            else:
                container_instance_ids = {
                    instance.id for instance in deployment_node.containerInstances
                    if instance.environment == environment and \
                        is_software_system_contains_container(
                            selected_software_system.id,
                            instance.containerId
                        )
                }

                instance_ids.update(container_instance_ids)

            software_instance_relation_ids: Set[str] = set()
            for software_system_instance in deployment_node.softwareSystemInstances:
                if software_system_instance.relationships and software_system_instance.environment == environment:
                    for relationship in software_system_instance.relationships:
                        software_instance_relation_ids.add(relationship.id)

            container_instance_relation_ids: Set[str] = set()
            if selected_software_system is not None:
                # Note: These relations are created in the `__exit__` of each
                # `DeploymentEnvironment` -- the relationships are being implied
                # from the respective `SoftwareSystem`s and `Container`s.
                for container_instance in deployment_node.containerInstances:
                    if container_instance.relationships and container_instance.environment == environment:
                        for relationship in container_instance.relationships:
                            container_instance_relation_ids.add(relationship.id)

            infrastructure_node_relation_ids: Set[str] = set()
            for infrastructure_node in deployment_node.infrastructureNodes:
                if infrastructure_node.relationships and infrastructure_node.environment == environment:
                    for relationship in infrastructure_node.relationships:
                        infrastructure_node_relation_ids.add(relationship.id)

            infrastructure_node_ids = {
                infrastructure_node.id for infrastructure_node in deployment_node.infrastructureNodes
                if infrastructure_node.environment == environment
            }

            instance_ids.update(software_instance_relation_ids)
            instance_ids.update(container_instance_relation_ids)
            instance_ids.update(infrastructure_node_relation_ids)
            instance_ids.update(infrastructure_node_ids)

            # Only include this deployment node
            # if there's anything to include at all.
            if len(instance_ids) > 0:
                for deployment_node_ancestor_id in deployment_node_ancestor_ids:
                    include_ids.add(deployment_node_ancestor_id)
                include_ids.add(deployment_node.id)
                include_ids.update(instance_ids)

        include_ids: Set[str] = set()
        upstream_software_system_ids: Set[str] = set()

        for root_deployment_node in workspace.model.model.deploymentNodes:
            if root_deployment_node.environment == self._environment.name:
                recursive_includes(
                    [],
                    root_deployment_node,
                    upstream_software_system_ids,
                    self._environment.name,
                    include_ids,
                    software_system.model if software_system else None
                )

        view_elements_filter = [
            lambda w, e: (
                e.id in include_ids
            ),
        ]

        view_relationships_filter_env = [
            lambda w, r: r.source.environment == self._environment.name,
            lambda w, r: r.destination.environment == self._environment.name,
        ]

        view_relationships_filter_implied_instance_relationships = [
            lambda w, r: r.id in include_ids,
        ]

        expression = Expression(
            include_elements=self._include_elements + view_elements_filter,
            exclude_elements=self._exclude_elements,
            include_relationships=self._include_relationships +\
                view_relationships_filter_env +\
                view_relationships_filter_implied_instance_relationships,
            exclude_relationships=self._exclude_relationships,
        )

        element_ids = [str(element.model.id) for element in expression.elements(workspace)]
        relationship_ids = [str(relationship.model.id) for relationship in expression.relationships(workspace)]

        self._m.elements = []
        for element_id in element_ids:
            # Add x, y coordinates (required by Structurizr for rendering)
            self._m.elements.append(ElementView(id=element_id, x=0, y=0))

        self._m.relationships = []
        for relationship_id in relationship_ids:
            self._m.relationships.append(RelationshipView(id=relationship_id))


class DynamicView(DslViewElement):

    from buildzr.dsl.expression import WorkspaceExpression

    @property
    def model(self) -> buildzr.models.DynamicView:
        return self._m

    def __init__(
        self,
        key: str,
        description: str = "",
        scope: Optional[Union[SoftwareSystem, Container, Callable[[WorkspaceExpression], Union[SoftwareSystem, Container]]]] = None,
        steps: List[DslRelationship] = [],
        auto_layout: _AutoLayout = 'tb',
        title: Optional[str] = None,
        properties: Optional[Dict[str, str]] = None,
    ) -> None:

        self._m = buildzr.models.DynamicView()
        self._m.key = key
        self._m.description = description
        self._m.automaticLayout = _auto_layout_to_model(auto_layout)
        self._m.title = title
        self._m.properties = properties

        self._scope = scope
        self._relationships = steps

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_view(self)

    def _find_original_relationship(
        self,
        workspace: Workspace,
        source: DslElement,
        destination: DslElement,
        exclude_id: str,
        technology: Optional[str] = None,
    ) -> Optional[DslRelationship]:
        """Find an existing relationship between source and destination, excluding a specific ID.

        Args:
            workspace: The workspace containing relationships.
            source: The source element of the relationship.
            destination: The destination element of the relationship.
            exclude_id: Relationship ID to exclude from matching.
            technology: If specified, only match relationships with this exact technology.
                       This follows Structurizr behavior where technology acts as a selector.
        """
        from buildzr.dsl.explorer import Explorer

        explorer = Explorer(workspace)
        for rel in explorer.walk_relationships():
            if rel.source.model.id == source.model.id and \
               rel.destination.model.id == destination.model.id and \
               rel.model.id != exclude_id:
                # If technology is specified, it must match exactly
                if technology is not None:
                    if rel.model.technology == technology:
                        return rel
                    # Continue searching for a relationship with matching technology
                else:
                    return rel
        return None

    def _remove_relationship_from_model(
        self,
        source: DslElement,
        rel_id: str,
    ) -> None:
        """Remove a relationship from both the source element's model and DSL relationships."""
        # Remove from model relationships
        if hasattr(source.model, 'relationships') and source.model.relationships:
            source.model.relationships = [
                r for r in source.model.relationships if r.id != rel_id
            ]
        # Also remove from DSL element's relationships set (used by Explorer)
        to_remove: Optional[DslRelationship] = None
        for r in source.relationships:
            if r.model.id == rel_id:
                to_remove = r
                break
        if to_remove is not None:
            source.relationships.discard(to_remove)

    def _on_added(self, workspace: Workspace) -> None:
        from buildzr.dsl.expression import WorkspaceExpression
        from buildzr.models import ElementView, RelationshipView
        from buildzr.dsl.explorer import Explorer

        # Resolve scope selector and set elementId
        if self._scope is not None:
            if isinstance(self._scope, (SoftwareSystem, Container)):
                self._m.elementId = self._scope.model.id
            elif callable(self._scope):
                resolved = self._scope(WorkspaceExpression(workspace))
                self._m.elementId = resolved.model.id

        # Collect relationship IDs passed to this DynamicView
        dv_rel_ids = {rel.model.id for rel in self._relationships}

        # Collect all relationship IDs in the workspace
        all_rel_ids = {rel.model.id for rel in Explorer(workspace).walk_relationships()}

        # Determine which relationships are "pre-existing" (created before this DynamicView)
        # vs "inline" (created during DynamicView argument evaluation)
        other_rel_ids = all_rel_ids - dv_rel_ids

        if not other_rel_ids:
            # All relationships in workspace are the ones passed to DynamicView.
            # This means they were ALL passed by reference (valid).
            pre_existing_rel_ids = dv_rel_ids.copy()
        else:
            # Some relationships exist outside of DynamicView. These are truly pre-existing.
            # For relationships passed to DynamicView, check if they existed before
            # by comparing IDs. Relationships with lower IDs were created earlier.
            max_other_id = max(int(rid) for rid in other_rel_ids)
            pre_existing_rel_ids = other_rel_ids.copy()
            for rel in self._relationships:
                if int(rel.model.id) <= max_other_id:
                    # This relationship was created before or around the same time
                    # as other relationships, so it's pre-existing (passed by reference)
                    pre_existing_rel_ids.add(rel.model.id)

        # Process relationships and collect elements
        element_ids: Set[str] = set()
        self._m.relationships = []

        for idx, rel in enumerate(self._relationships, start=1):
            source = rel.source
            destination = rel.destination
            rel_description: Optional[str] = None
            rel_id = rel.model.id
            rel_technology = rel.model.technology  # Technology from inline relationship (if any)

            # Check if there's an original relationship (created before this one)
            # If the inline relationship specifies a technology, use it as a selector
            # (following Structurizr behavior where technology acts as a selector, not an override)
            original_rel = self._find_original_relationship(
                workspace, source, destination, rel.model.id, technology=rel_technology
            )

            if original_rel is not None:
                # This is a view-specific relationship - use original's ID
                # and remove the duplicate from the model
                rel_description = rel.model.description
                self._remove_relationship_from_model(source, rel.model.id)
                rel_id = original_rel.model.id
            elif rel.model.id not in pre_existing_rel_ids:
                # This relationship was created during DynamicView argument evaluation
                # (inline syntax) and there's no pre-existing relationship between
                # source and destination (with matching technology if specified). This is invalid.
                source_name = getattr(source.model, 'name', str(source.model.id))
                dest_name = getattr(destination.model, 'name', str(destination.model.id))
                if rel_technology:
                    raise ValueError(
                        f"No existing relationship found between '{source_name}' and "
                        f"'{dest_name}' with technology '{rel_technology}'. "
                        f"When technology is specified in a DynamicView relationship, it acts as a "
                        f"selector to match a model relationship with that exact technology."
                    )
                raise ValueError(
                    f"No existing relationship found between '{source_name}' and "
                    f"'{dest_name}'. DynamicView relationships must reference "
                    f"pre-existing relationships in the model. Either define the relationship "
                    f"before creating the DynamicView, or pass the relationship variable directly."
                )
            # else: This is the original relationship passed by reference, use it directly

            # Collect element IDs
            element_ids.add(str(source.model.id))
            element_ids.add(str(destination.model.id))

            # Add relationship view with order and optional description override
            self._m.relationships.append(
                RelationshipView(
                    id=rel_id,
                    order=str(idx),
                    description=rel_description,
                )
            )

        # Populate elements
        self._m.elements = [ElementView(id=eid) for eid in element_ids]


class CustomView(DslViewElement):
    """
    A custom view for displaying custom elements (Element type).

    CustomView is specifically designed for custom elements that sit outside
    the C4 model. By default, it only includes Element types and relationships
    between them. This matches the Structurizr DSL behavior where custom views
    are intended for custom elements.

    Note: Structurizr CLI/Lite only supports CustomElement types in CustomView.
    Including other element types (Person, SoftwareSystem, etc.) will cause
    export errors.
    """

    from buildzr.dsl.expression import Expression, WorkspaceExpression, ElementExpression, RelationshipExpression

    @property
    def model(self) -> buildzr.models.CustomView:
        return self._m

    def __init__(
        self,
        key: str,
        description: str = "",
        auto_layout: _AutoLayout = 'tb',
        title: Optional[str] = None,
        include_elements: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]] = [],
        exclude_elements: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]] = [],
        include_relationships: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]] = [],
        exclude_relationships: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]] = [],
        properties: Optional[Dict[str, str]] = None,
    ) -> None:
        self._m = buildzr.models.CustomView()

        self._m.key = key
        self._m.description = description

        self._m.automaticLayout = _auto_layout_to_model(auto_layout)
        self._m.title = title
        self._m.properties = properties

        # Validate that include_elements only contains Element types
        # CustomView can ONLY display custom elements (Element type)
        for elem in include_elements:
            if isinstance(elem, DslElement) and not isinstance(elem, Element):
                raise ValueError(
                    f"CustomView can only include Element types, not {type(elem).__name__}. "
                    f"Use SystemLandscapeView or other views for C4 elements."
                )

        self._include_elements = include_elements
        self._exclude_elements = exclude_elements
        self._include_relationships = include_relationships
        self._exclude_relationships = exclude_relationships

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_view(self)

    def _on_added(self, workspace: Workspace) -> None:

        from buildzr.dsl.expression import Expression, WorkspaceExpression, ElementExpression, RelationshipExpression
        from buildzr.models import ElementView, RelationshipView

        # CustomView only includes Element (custom element) types by default
        # This matches Structurizr CLI/DSL behavior
        include_view_elements_filter: List[Union[DslElement, Callable[[WorkspaceExpression, ElementExpression], bool]]] = [
            lambda w, e: e.type == Element,
        ]

        # Include relationships where both source and destination are Element types
        include_view_relationships_filter: List[Union[DslElement, Callable[[WorkspaceExpression, RelationshipExpression], bool]]] = [
            lambda w, r: r.source.type == Element and r.destination.type == Element,
        ]

        expression = Expression(
            include_elements=self._include_elements + include_view_elements_filter,
            exclude_elements=self._exclude_elements,
            include_relationships=self._include_relationships + include_view_relationships_filter,
            exclude_relationships=self._exclude_relationships,
        )

        element_ids = map(
            lambda x: str(x.model.id),
            expression.elements(workspace)
        )

        relationship_ids = map(
            lambda x: str(x.model.id),
            expression.relationships(workspace)
        )

        self._m.elements = []
        for element_id in element_ids:
            # Add x, y coordinates (required by Structurizr for rendering)
            self._m.elements.append(ElementView(id=element_id, x=0, y=0))

        self._m.relationships = []
        for relationship_id in relationship_ids:
            self._m.relationships.append(RelationshipView(id=relationship_id))


class StyleElements:

    from buildzr.dsl.expression import WorkspaceExpression, ElementExpression

    Shapes = Union[
        Literal['Box'],
        Literal['RoundedBox'],
        Literal['Circle'],
        Literal['Ellipse'],
        Literal['Hexagon'],
        Literal['Cylinder'],
        Literal['Pipe'],
        Literal['Person'],
        Literal['Robot'],
        Literal['Folder'],
        Literal['WebBrowser'],
        Literal['MobileDevicePortrait'],
        Literal['MobileDeviceLandscape'],
        Literal['Component'],
    ]

    @property
    def model(self) -> List[buildzr.models.ElementStyle]:
        return self._m

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    # TODO: Validate arguments with pydantic.
    def __init__(
            self,
            on: List[Union[
                DslElement,
                Group,
                Callable[[WorkspaceExpression, ElementExpression], bool],
                Type[Union['Person', 'SoftwareSystem', 'Container', 'Component']],
                str
            ]],
            tag: Optional[str]=None,
            shape: Optional[Shapes]=None,
            icon: Optional[str]=None,
            width: Optional[int]=None,
            height: Optional[int]=None,
            background: Optional[Union['str', Tuple[int, int, int], Color]]=None,
            color: Optional[Union['str', Tuple[int, int, int], Color]]=None,
            stroke: Optional[Union[str, Tuple[int, int, int], Color]]=None,
            stroke_width: Optional[int]=None,
            font_size: Optional[int]=None,
            border: Optional[Literal['solid', 'dashed', 'dotted']]=None,
            opacity: Optional[int]=None,
            metadata: Optional[bool]=None,
            description: Optional[bool]=None,
    ) -> None:

        # How the tag is populated depends on each element type in the
        # `elemenets`.
        # - If the element is a `DslElement`, then we create a unique tag
        #   specifically to help the stylizer identify that specific element.
        #   For example, if the element has an id `3`, then we should create a
        #   tag, say, `style-element-3`.
        # - If the element is a `Group`, then we simply make create the tag
        #   based on the group name and its nested path. For example,
        #   `Group:Company 1/Department 1`.
        # - If the element is a `Callable[[Workspace, Element], bool]`, we just
        #   run the function to filter out all the elements that matches the
        #   description, and create a unique tag for all of the filtered
        #   elements.
        # - If the element is a `Type[Union['Person', 'SoftwareSystem', 'Container', 'Component']]`,
        #   we create a tag based on the class name. This is based on the fact
        #   that the default tag for each element is the element's type.
        # - If the element is a `str`, we just use the string as the tag.
        #   This is useful for when you want to apply a style to all elements
        #   with a specific tag, just like in the original Structurizr DSL.
        #
        # Note that a new `buildzr.models.ElementStyle` is created for each
        # item, not for each of `StyleElements` instance. This makes the styling
        # makes more concise and flexible.

        from buildzr.dsl.expression import ElementExpression
        from uuid import uuid4

        if background:
            assert Color.is_valid_color(background), "Invalid background color: {}".format(background)
        if color:
            assert Color.is_valid_color(color), "Invalid color: {}".format(color)
        if stroke:
            assert Color.is_valid_color(stroke), "Invalid stroke color: {}".format(stroke)

        self._m: List[buildzr.models.ElementStyle] = []
        self._parent: Optional[Workspace] = None

        workspace = _current_workspace.get()
        if workspace is not None:
            self._parent = workspace

        self._elements = on

        border_enum: Dict[str, buildzr.models.Border] = {
            'solid': buildzr.models.Border.Solid,
            'dashed': buildzr.models.Border.Dashed,
            'dotted': buildzr.models.Border.Dotted,
        }

        shape_enum: Dict[str, buildzr.models.Shape] = {
            'Box': buildzr.models.Shape.Box,
            'RoundedBox': buildzr.models.Shape.RoundedBox,
            'Circle': buildzr.models.Shape.Circle,
            'Ellipse': buildzr.models.Shape.Ellipse,
            'Hexagon': buildzr.models.Shape.Hexagon,
            'Cylinder': buildzr.models.Shape.Cylinder,
            'Pipe': buildzr.models.Shape.Pipe,
            'Person': buildzr.models.Shape.Person,
            'Robot': buildzr.models.Shape.Robot,
            'Folder': buildzr.models.Shape.Folder,
            'WebBrowser': buildzr.models.Shape.WebBrowser,
            'MobileDevicePortrait': buildzr.models.Shape.MobileDevicePortrait,
            'MobileDeviceLandscape': buildzr.models.Shape.MobileDeviceLandscape,
            'Component': buildzr.models.Shape.Component,
        }

        # A single unique element to be applied to all elements
        # affected by this style.
        # If a tag is provided (e.g., from a ThemeElement), use it for meaningful
        # legend display. Otherwise, generate a unique internal tag.
        element_tag = tag if tag else "buildzr-styleelements-{}".format(uuid4().hex)

        # Track which tags we've already created styles for (to avoid duplicates)
        created_tags: set[str] = set()

        for element in self._elements:
            # Determine the tag for this element
            if isinstance(element, DslElement) and not isinstance(element.model, buildzr.models.Workspace):
                tag = element_tag
                element.add_tags(element_tag)
            elif isinstance(element, Group):
                tag = f"Group:{element.full_name()}"
            elif isinstance(element, type):
                tag = f"{element.__name__}"
            elif isinstance(element, str):
                tag = element
            elif callable(element):
                from buildzr.dsl.expression import ElementExpression, Expression
                if self._parent:
                    tag = element_tag
                    matched_elems = Expression(include_elements=[element]).elements(self._parent)
                    for e in matched_elems:
                        e.add_tags(element_tag)
                else:
                    raise ValueError("Cannot use callable to select elements to style without a Workspace.")
            else:
                continue

            # Only create one style per unique tag
            if tag in created_tags:
                continue
            created_tags.add(tag)

            element_style = buildzr.models.ElementStyle()
            element_style.tag = tag
            element_style.shape = shape_enum[shape] if shape else None
            element_style.icon = icon
            element_style.width = width
            element_style.height = height
            element_style.background = Color(background).to_hex() if background else None
            element_style.color = Color(color).to_hex() if color else None
            element_style.stroke = Color(stroke).to_hex() if stroke else None
            element_style.strokeWidth = stroke_width
            element_style.fontSize = font_size
            element_style.border = border_enum[border] if border else None
            element_style.opacity = opacity
            element_style.metadata = metadata
            element_style.description = description
            self._m.append(element_style)

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_style(self)

class StyleRelationships:

    from buildzr.dsl.expression import WorkspaceExpression, RelationshipExpression

    @property
    def model(self) -> List[buildzr.models.RelationshipStyle]:
        return self._m

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    def __init__(
        self,
        on: Optional[List[Union[
            DslRelationship,
            Group,
            Callable[[WorkspaceExpression, RelationshipExpression], bool],
            str
        ]]]=None,
        thickness: Optional[int]=None,
        color: Optional[Union[str, Tuple[int, int, int], Color]]=None,
        routing: Optional[Literal['Direct', 'Orthogonal', 'Curved']]=None,
        font_size: Optional[int]=None,
        width: Optional[int]=None,
        dashed: Optional[bool]=None,
        position: Optional[int]=None,
        opacity: Optional[int]=None,
    ) -> None:

        from uuid import uuid4

        if color is not None:
            assert Color.is_valid_color(color), "Invalid color: {}".format(color)

        routing_enum: Dict[str, buildzr.models.Routing1] = {
            'Direct': buildzr.models.Routing1.Direct,
            'Orthogonal': buildzr.models.Routing1.Orthogonal,
            'Curved': buildzr.models.Routing1.Curved,
        }

        self._m: List[buildzr.models.RelationshipStyle] = []
        self._parent: Optional[Workspace] = None

        workspace = _current_workspace.get()
        if workspace is not None:
            self._parent = workspace

        # A single unique tag to be applied to all relationships
        # affected by this style.
        relation_tag = "buildzr-stylerelationships-{}".format(uuid4().hex)

        if on is None:
            self._m.append(buildzr.models.RelationshipStyle(
                thickness=thickness,
                color=Color(color).to_hex() if color else None,
                routing=routing_enum[routing] if routing else None,
                fontSize=font_size,
                width=width,
                dashed=dashed,
                position=position,
                opacity=opacity,
                tag="Relationship",
            ))
        else:
            for relationship in on:

                relationship_style = buildzr.models.RelationshipStyle()
                relationship_style.thickness = thickness
                relationship_style.color = Color(color).to_hex() if color else None
                relationship_style.routing = routing_enum[routing] if routing else None
                relationship_style.fontSize = font_size
                relationship_style.width = width
                relationship_style.dashed = dashed
                relationship_style.position = position
                relationship_style.opacity = opacity

                if isinstance(relationship, DslRelationship):
                    relationship.add_tags(relation_tag)
                    relationship_style.tag = relation_tag
                elif isinstance(relationship, Group):
                    from buildzr.dsl.expression import Expression
                    if self._parent:
                        rels = Expression(include_relationships=[
                            lambda w, r: r.source.group == relationship.full_name() and \
                                         r.destination.group == relationship.full_name()
                        ]).relationships(self._parent)
                        for r in rels:
                            r.add_tags(relation_tag)
                        relationship_style.tag = relation_tag
                    else:
                        raise ValueError("Cannot use callable to select elements to style without a Workspace.")
                elif isinstance(relationship, str):
                    relationship_style.tag = relationship
                elif callable(relationship):
                    from buildzr.dsl.expression import Expression
                    if self._parent:
                        relationship_style.tag = relation_tag
                        matched_rels = Expression(include_relationships=[relationship]).relationships(self._parent)
                        for matched_rel in matched_rels:
                            matched_rel.add_tags(relation_tag)
                    else:
                        raise ValueError("Cannot use callable to select elements to style without a Workspace.")
                self._m.append(relationship_style)

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_style(self)