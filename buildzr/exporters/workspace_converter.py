"""Converts buildzr Python workspace objects to Java Workspace objects for JPype."""

from typing import Dict, Any, Optional, Union, TYPE_CHECKING
import jpype  # type: ignore
import jpype.imports  # type: ignore

if TYPE_CHECKING:
    from typing import Any as JavaAny  # Placeholder for Java types during type checking

from buildzr.models.models import (
    Workspace,
    Model,
    Person,
    SoftwareSystem,
    Container,
    Component,
    DeploymentNode,
    InfrastructureNode,
    Relationship,
    Views,
    SystemLandscapeView,
    SystemContextView,
    ContainerView,
    ComponentView,
    DeploymentView,
    DynamicView,
    CustomView,
    InteractionStyle,
    Shape,
)


class WorkspaceConverter:
    """
    Converts buildzr Python workspace to Java com.structurizr.Workspace.

    This class handles the bidirectional mapping between Python dataclasses
    and Java objects via JPype, preserving all model elements, relationships,
    views, and styling information.

    Example:
        >>> converter = WorkspaceConverter()
        >>> java_workspace = converter.to_java(python_workspace)
    """

    def __init__(self) -> None:
        """Initialize the converter."""
        if not jpype.isJVMStarted():
            raise RuntimeError(
                "JVM must be started before creating WorkspaceConverter. "
                "Use PlantUmlSink which initializes the JVM."
            )

        # Import Java classes (only after JVM is started)
        # JPype provides type stubs for some imports
        from com.structurizr import Workspace as JavaWorkspace  # type: ignore[import-not-found]
        from com.structurizr.model import Model as JavaModel  # type: ignore[import-not-found]
        from com.structurizr.model import Person as JavaPerson
        from com.structurizr.model import SoftwareSystem as JavaSoftwareSystem
        from com.structurizr.model import Container as JavaContainer
        from com.structurizr.model import Component as JavaComponent
        from com.structurizr.model import DeploymentNode as JavaDeploymentNode
        from com.structurizr.model import Location as JavaLocation
        from com.structurizr.model import InteractionStyle as JavaInteractionStyle
        from com.structurizr.view import ViewSet as JavaViewSet  # type: ignore[import-not-found]

        self.JavaWorkspace = JavaWorkspace
        self.JavaModel = JavaModel
        self.JavaPerson = JavaPerson
        self.JavaSoftwareSystem = JavaSoftwareSystem
        self.JavaContainer = JavaContainer
        self.JavaComponent = JavaComponent
        self.JavaDeploymentNode = JavaDeploymentNode
        self.JavaLocation = JavaLocation
        self.JavaInteractionStyle = JavaInteractionStyle
        self.JavaViewSet = JavaViewSet

        # Maps to track ID -> Java object for relationship resolution
        self._element_map: Dict[str, Any] = {}

    def to_java(self, workspace: Workspace) -> Any:
        """
        Convert Python workspace to Java Workspace object.

        Args:
            workspace: Python workspace to convert

        Returns:
            Java com.structurizr.Workspace object
        """
        # Clear element map for this conversion
        self._element_map.clear()

        # Create Java workspace with basic properties
        java_workspace = self.JavaWorkspace(
            workspace.name or "Workspace",
            workspace.description or ""
        )

        # Set workspace metadata
        if workspace.id:
            java_workspace.setId(workspace.id)
        if workspace.version:
            java_workspace.setVersion(workspace.version)

        # Convert model (elements and relationships)
        if workspace.model:
            self._convert_model(workspace.model, java_workspace)

        # Convert views
        if workspace.views:
            self._convert_views(workspace.views, java_workspace)

        return java_workspace

    def _convert_model(self, model: Model, java_workspace: Any) -> None:
        """
        Convert Python model to Java model.

        Args:
            model: Python Model to convert
            java_workspace: Target Java Workspace
        """
        java_model = java_workspace.getModel()

        # Convert people
        if model.people:
            for person in model.people:
                self._convert_person(person, java_model)

        # Convert software systems
        if model.softwareSystems:
            for system in model.softwareSystems:
                self._convert_software_system(system, java_model)

        # Convert static structure relationships BEFORE deployment nodes
        # This is required so that the Java library can auto-create implied
        # relationships between container instances when we add them
        if model.people:
            for person in model.people:
                if person.relationships:
                    for rel in person.relationships:
                        self._convert_relationship(rel, java_model)

        if model.softwareSystems:
            for system in model.softwareSystems:
                if system.relationships:
                    for rel in system.relationships:
                        self._convert_relationship(rel, java_model)

                # Container relationships
                if system.containers:
                    for container in system.containers:
                        if container.relationships:
                            for rel in container.relationships:
                                self._convert_relationship(rel, java_model)

                        # Component relationships
                        if container.components:
                            for component in container.components:
                                if component.relationships:
                                    for rel in component.relationships:
                                        self._convert_relationship(rel, java_model)

        # Convert deployment nodes AFTER static structure relationships
        # The Java library auto-creates implied relationships between container
        # instances based on the existing container-to-container relationships
        if model.deploymentNodes:
            for deployment_node in model.deploymentNodes:
                self._convert_deployment_node(deployment_node, java_model)

        # Convert deployment-specific relationships (infrastructure nodes, etc.)
        if model.deploymentNodes:
            for deployment_node in model.deploymentNodes:
                self._convert_deployment_relationships(deployment_node, java_model)

    def _convert_person(self, person: Person, java_model: Any) -> Any:
        """Convert Python Person to Java Person."""
        java_person = java_model.addPerson(
            person.name or "",
            person.description or ""
        )

        # Map Python ID to Java element (Java generates its own IDs)
        if person.id:
            self._element_map[person.id] = java_person

        if person.tags:
            # Tags are comma-separated in Python
            for tag in person.tags.split(','):
                java_person.addTags(tag.strip())

        if person.url:
            java_person.setUrl(person.url)

        # Note: Location is stored in Python model but Java API doesn't expose setLocation()
        # Location will be included in JSON export but not available for PlantUML rendering

        if person.properties:
            for key, value in person.properties.items():
                java_person.addProperty(key, str(value))

        return java_person

    def _convert_software_system(self, system: SoftwareSystem, java_model: Any) -> Any:
        """Convert Python SoftwareSystem to Java SoftwareSystem."""
        java_system = java_model.addSoftwareSystem(
            system.name or "",
            system.description or ""
        )

        # Map Python ID to Java element (Java generates its own IDs)
        if system.id:
            self._element_map[system.id] = java_system

        if system.tags:
            for tag in system.tags.split(','):
                java_system.addTags(tag.strip())

        if system.url:
            java_system.setUrl(system.url)

        # Note: Location is stored in Python model but Java API doesn't expose setLocation()
        # Location will be included in JSON export but not available for PlantUML rendering

        if system.properties:
            for key, value in system.properties.items():
                java_system.addProperty(key, str(value))

        # Convert containers
        if system.containers:
            for container in system.containers:
                self._convert_container(container, java_system)

        return java_system

    def _convert_container(self, container: Container, java_system: Any) -> Any:
        """Convert Python Container to Java Container."""
        java_container = java_system.addContainer(
            container.name or "",
            container.description or "",
            container.technology or ""
        )

        # Map Python ID to Java element (Java generates its own IDs)
        if container.id:
            self._element_map[container.id] = java_container

        if container.tags:
            for tag in container.tags.split(','):
                java_container.addTags(tag.strip())

        if container.url:
            java_container.setUrl(container.url)

        if container.properties:
            for key, value in container.properties.items():
                java_container.addProperty(key, str(value))

        # Convert components
        if container.components:
            for component in container.components:
                self._convert_component(component, java_container)

        return java_container

    def _convert_component(self, component: Component, java_container: Any) -> Any:
        """Convert Python Component to Java Component."""
        java_component = java_container.addComponent(
            component.name or "",
            component.description or "",
            component.technology or ""
        )

        # Map Python ID to Java element (Java generates its own IDs)
        if component.id:
            self._element_map[component.id] = java_component

        if component.tags:
            for tag in component.tags.split(','):
                java_component.addTags(tag.strip())

        if component.url:
            java_component.setUrl(component.url)

        if component.properties:
            for key, value in component.properties.items():
                java_component.addProperty(key, str(value))

        return java_component

    def _convert_deployment_node(
        self,
        deployment_node: DeploymentNode,
        parent: Any,
        depth: int = 0
    ) -> Any:
        """
        Convert Python DeploymentNode to Java DeploymentNode.

        Args:
            deployment_node: Python DeploymentNode
            parent: Parent Java object (Model or DeploymentNode)
            depth: Current nesting depth
        """
        # Check if parent is Model or DeploymentNode
        if depth == 0:
            java_node = parent.addDeploymentNode(
                deployment_node.name or "",
                deployment_node.description or "",
                deployment_node.technology or ""
            )
        else:
            java_node = parent.addDeploymentNode(
                deployment_node.name or "",
                deployment_node.description or "",
                deployment_node.technology or ""
            )

        # Map Python ID to Java element (Java generates its own IDs)
        if deployment_node.id:
            self._element_map[deployment_node.id] = java_node

        if deployment_node.tags:
            for tag in deployment_node.tags.split(','):
                java_node.addTags(tag.strip())

        if deployment_node.url:
            java_node.setUrl(deployment_node.url)

        if deployment_node.properties:
            for key, value in deployment_node.properties.items():
                java_node.addProperty(key, str(value))

        if deployment_node.instances:
            java_node.setInstances(str(deployment_node.instances))

        # Recursively convert child deployment nodes
        if deployment_node.children:
            for child_node in deployment_node.children:
                self._convert_deployment_node(child_node, java_node, depth + 1)

        # Convert infrastructure nodes
        if deployment_node.infrastructureNodes:
            for infra_node in deployment_node.infrastructureNodes:
                self._convert_infrastructure_node(infra_node, java_node)

        # Convert container instances
        if deployment_node.containerInstances:
            for instance in deployment_node.containerInstances:
                if instance.containerId and instance.containerId in self._element_map:
                    java_container = self._element_map[instance.containerId]
                    # Pass deployment groups to Java - this controls implied relationship creation
                    deployment_groups = instance.deploymentGroups or []
                    if deployment_groups:
                        java_instance = java_node.add(java_container, *deployment_groups)
                    else:
                        java_instance = java_node.add(java_container)
                    if instance.instanceId:
                        java_instance.setInstanceId(int(instance.instanceId))
                    # Map the ContainerInstance's ID to the Java instance
                    if instance.id:
                        self._element_map[instance.id] = java_instance

        return java_node

    def _convert_infrastructure_node(
        self,
        infra_node: InfrastructureNode,
        java_deployment_node: Any
    ) -> Any:
        """
        Convert Python InfrastructureNode to Java InfrastructureNode.

        Args:
            infra_node: Python InfrastructureNode
            java_deployment_node: Parent Java DeploymentNode
        """
        java_infra = java_deployment_node.addInfrastructureNode(
            infra_node.name or "",
            infra_node.description or "",
            infra_node.technology or ""
        )

        # Map Python ID to Java element
        if infra_node.id:
            self._element_map[infra_node.id] = java_infra

        if infra_node.tags:
            for tag in infra_node.tags.split(','):
                java_infra.addTags(tag.strip())

        if infra_node.url:
            java_infra.setUrl(infra_node.url)

        if infra_node.properties:
            for key, value in infra_node.properties.items():
                java_infra.addProperty(key, str(value))

        return java_infra

    def _convert_deployment_relationships(self, deployment_node: DeploymentNode, java_model: Any) -> None:
        """Recursively convert relationships from deployment nodes, infrastructure nodes, and container instances."""
        if deployment_node.relationships:
            for rel in deployment_node.relationships:
                self._convert_relationship(rel, java_model)

        # Convert infrastructure node relationships
        if deployment_node.infrastructureNodes:
            for infra_node in deployment_node.infrastructureNodes:
                if infra_node.relationships:
                    for rel in infra_node.relationships:
                        self._convert_relationship(rel, java_model)

        # Convert container instance relationships
        if deployment_node.containerInstances:
            for instance in deployment_node.containerInstances:
                if instance.relationships:
                    for rel in instance.relationships:
                        self._convert_relationship(rel, java_model)

        if deployment_node.children:
            for child_node in deployment_node.children:
                self._convert_deployment_relationships(child_node, java_model)

    def _convert_relationship(self, relationship: Relationship, java_model: Any) -> Optional[Any]:
        """Convert Python Relationship to Java Relationship."""
        if not relationship.sourceId or not relationship.destinationId:
            return None

        # Skip implied relationships - the Java library auto-creates these when
        # container instances are added for containers that have relationships
        if relationship.linkedRelationshipId is not None:
            return None

        source = self._element_map.get(relationship.sourceId)
        destination = self._element_map.get(relationship.destinationId)

        if not source or not destination:
            # Skip relationship if elements not found
            return None

        # Check parent-child relationships (not allowed in Structurizr Java)
        # See: https://github.com/structurizr/java/blob/master/structurizr-core/src/main/java/com/structurizr/model/Model.java
        if self._is_child_of(source, destination) or self._is_child_of(destination, source):
            is_implied = relationship.linkedRelationshipId is not None
            relationship_type = "Implied relationship" if is_implied else "Relationship"
            raise ValueError(
                f"{relationship_type} cannot be added between parents and children: "
                f"'{source.getName()}' (id={relationship.sourceId}) -> "
                f"'{destination.getName()}' (id={relationship.destinationId})"
            )

        # Determine the correct Java method based on element types
        # - delivers(): for relationships TO a Person
        # - interactsWith(): for Person to Person relationships
        # - uses(): for all other relationships
        dest_class_name = destination.getClass().getSimpleName()
        source_class_name = source.getClass().getSimpleName()

        if dest_class_name == "Person":
            if source_class_name == "Person":
                java_rel = source.interactsWith(
                    destination,
                    relationship.description or "",
                    relationship.technology or ""
                )
            else:
                java_rel = source.delivers(
                    destination,
                    relationship.description or "",
                    relationship.technology or ""
                )
        else:
            java_rel = source.uses(
                destination,
                relationship.description or "",
                relationship.technology or ""
            )

        # Note: Java library generates relationship IDs automatically

        if relationship.tags:
            for tag in relationship.tags.split(','):
                java_rel.addTags(tag.strip())

        if relationship.url:
            java_rel.setUrl(relationship.url)

        if relationship.interactionStyle:
            java_rel.setInteractionStyle(
                self._convert_interaction_style(relationship.interactionStyle)
            )

        if relationship.properties:
            for key, value in relationship.properties.items():
                java_rel.addProperty(key, str(value))

        return java_rel

    def _convert_views(self, views: Views, java_workspace: Any) -> None:
        """Convert Python Views to Java ViewSet."""
        java_views = java_workspace.getViews()

        # Convert system landscape views
        if views.systemLandscapeViews:
            for view in views.systemLandscapeViews:
                self._convert_system_landscape_view(view, java_views)

        # Convert system context views
        if views.systemContextViews:
            for ctx_view in views.systemContextViews:
                self._convert_system_context_view(ctx_view, java_views)

        # Convert container views
        if views.containerViews:
            for cnt_view in views.containerViews:
                self._convert_container_view(cnt_view, java_views)

        # Convert component views
        if views.componentViews:
            for cmp_view in views.componentViews:
                self._convert_component_view(cmp_view, java_views)

        # Convert deployment views
        if views.deploymentViews:
            for dep_view in views.deploymentViews:
                self._convert_deployment_view(dep_view, java_views)

        # Convert dynamic views
        if views.dynamicViews:
            for dyn_view in views.dynamicViews:
                self._convert_dynamic_view(dyn_view, java_views)

        # Convert custom views
        if views.customViews:
            for cust_view in views.customViews:
                self._convert_custom_view(cust_view, java_views)

        # Convert styles
        if views.configuration:
            self._convert_styles(views.configuration, java_views)

    def _convert_system_landscape_view(self, view: SystemLandscapeView, java_views: Any) -> Any:
        """Convert Python SystemLandscapeView to Java."""
        java_view = java_views.createSystemLandscapeView(
            view.key or "",
            view.description or ""
        )

        self._apply_common_view_properties(view, java_view)
        return java_view

    def _convert_system_context_view(self, view: SystemContextView, java_views: Any) -> Any:
        """Convert Python SystemContextView to Java."""
        if not view.softwareSystemId:
            return None

        software_system = self._element_map.get(view.softwareSystemId)
        if not software_system:
            return None

        java_view = java_views.createSystemContextView(
            software_system,
            view.key or "",
            view.description or ""
        )

        self._apply_common_view_properties(view, java_view)
        return java_view

    def _convert_container_view(self, view: ContainerView, java_views: Any) -> Any:
        """Convert Python ContainerView to Java."""
        if not view.softwareSystemId:
            return None

        software_system = self._element_map.get(view.softwareSystemId)
        if not software_system:
            return None

        java_view = java_views.createContainerView(
            software_system,
            view.key or "",
            view.description or ""
        )

        self._apply_common_view_properties(view, java_view)
        return java_view

    def _convert_component_view(self, view: ComponentView, java_views: Any) -> Any:
        """Convert Python ComponentView to Java."""
        if not view.containerId:
            return None

        container = self._element_map.get(view.containerId)
        if not container:
            return None

        java_view = java_views.createComponentView(
            container,
            view.key or "",
            view.description or ""
        )

        self._apply_common_view_properties(view, java_view)
        return java_view

    def _convert_deployment_view(self, view: DeploymentView, java_views: Any) -> Any:
        """Convert Python DeploymentView to Java."""
        # Deployment views can be scoped to a software system or be global
        if view.softwareSystemId:
            software_system = self._element_map.get(view.softwareSystemId)
            if software_system:
                java_view = java_views.createDeploymentView(
                    software_system,
                    view.key or "",
                    view.description or ""
                )
            else:
                return None
        else:
            java_view = java_views.createDeploymentView(
                view.key or "",
                view.description or ""
            )

        # For deployment views, use addAllDeploymentNodes() to include all
        # deployment nodes and their implied relationships automatically
        java_view.addAllDeploymentNodes()

        # Remove relationships between container instances that don't share
        # at least one common deployment group (cross-group relationships)
        self._remove_cross_group_relationships(java_view)

        self._apply_common_view_properties(view, java_view)
        return java_view

    def _remove_cross_group_relationships(self, java_view: Any) -> None:
        """
        Remove relationships between container/software system instances that
        don't share at least one common deployment group.

        This is needed because the Java library creates implied relationships
        between ALL instances when their underlying elements have relationships,
        regardless of deployment groups. The Python model correctly filters
        these by deployment group, so we need to remove the extras.

        Args:
            java_view: Java DeploymentView object
        """
        # Collect relationships to remove (can't modify while iterating)
        rels_to_remove = []

        for rel_view in java_view.getRelationships():
            rel = rel_view.getRelationship()
            source = rel.getSource()
            destination = rel.getDestination()

            # Only check StaticStructureElementInstance relationships
            # (ContainerInstance or SoftwareSystemInstance)
            source_class = source.getClass().getSimpleName()
            dest_class = destination.getClass().getSimpleName()

            if source_class not in ('ContainerInstance', 'SoftwareSystemInstance'):
                continue
            if dest_class not in ('ContainerInstance', 'SoftwareSystemInstance'):
                continue

            # Get deployment groups for both instances
            source_groups = set(source.getDeploymentGroups())
            dest_groups = set(destination.getDeploymentGroups())

            # If they share no common deployment groups, remove the relationship
            if not source_groups.intersection(dest_groups):
                rels_to_remove.append(rel)

        # Remove the cross-group relationships from the view
        for rel in rels_to_remove:
            java_view.remove(rel)

    def _convert_dynamic_view(self, view: DynamicView, java_views: Any) -> Any:
        """Convert Python DynamicView to Java."""
        # Dynamic views can be scoped to various elements
        scope_element = None

        if hasattr(view, 'elementId') and view.elementId:
            scope_element = self._element_map.get(view.elementId)

        if scope_element:
            java_view = java_views.createDynamicView(
                scope_element,
                view.key or "",
                view.description or ""
            )
        else:
            java_view = java_views.createDynamicView(
                view.key or "",
                view.description or ""
            )

        # Add relationships in sequence
        if hasattr(view, 'relationships') and view.relationships:
            for rel_view in view.relationships:
                if hasattr(rel_view, 'relationshipId') and rel_view.relationshipId:
                    # Find the relationship by ID
                    source_element = self._element_map.get(rel_view.relationshipId) if hasattr(rel_view, 'relationshipId') else None
                    if source_element:
                        java_view.add(source_element)

        self._apply_common_view_properties(view, java_view)
        return java_view

    def _convert_custom_view(self, view: CustomView, java_views: Any) -> Any:
        """Convert Python CustomView to Java."""
        java_view = java_views.createCustomView(
            view.key or "",
            view.title or "",
            view.description or ""
        )

        self._apply_common_view_properties(view, java_view)
        return java_view

    def _apply_common_view_properties(self, view: Any, java_view: Any) -> None:
        """Apply common properties to all view types."""
        # Add elements to view
        if hasattr(view, 'elements') and view.elements:
            for element_view in view.elements:
                if element_view.id and element_view.id in self._element_map:
                    java_element = self._element_map[element_view.id]

                    # Add element to view
                    try:
                        java_view.add(java_element)
                    except TypeError as e:
                        # Element type not compatible with this view type
                        element_type = type(java_element).__name__.split('.')[-1]
                        view_type = type(java_view).__name__.split('.')[-1]
                        raise TypeError(
                            f"Cannot add {element_type} to {view_type}. "
                            f"View element types must be compatible with the view. "
                            f"Original error: {str(e)}"
                        ) from e

        # Add relationships to view (if not added automatically)
        # Views typically auto-add relationships between included elements

        # Apply automatic layout
        self._apply_automatic_layout(view, java_view)

        # Set title if present
        if hasattr(view, 'title') and view.title:
            java_view.setTitle(view.title)

    def _apply_automatic_layout(self, view: Any, java_view: Any) -> None:
        """Apply automatic layout if specified (optional feature)."""
        # Note: AutomaticLayout may not be available in all versions of structurizr-export
        if hasattr(view, 'automaticLayout') and view.automaticLayout:
            try:
                layout = view.automaticLayout
                from com.structurizr.view import AutomaticLayout as JavaAutoLayout
                from com.structurizr.view import RankDirection as JavaRankDirection

                rank_direction = JavaRankDirection.TopBottom  # Default
                if hasattr(layout, 'rankDirection') and layout.rankDirection:
                    rank_direction = self._convert_rank_direction(layout.rankDirection)

                java_auto_layout = JavaAutoLayout(
                    rank_direction,
                    layout.rankSeparation if hasattr(layout, 'rankSeparation') and layout.rankSeparation else 100,
                    layout.nodeSeparation if hasattr(layout, 'nodeSeparation') and layout.nodeSeparation else 100,
                    layout.edgeSeparation if hasattr(layout, 'edgeSeparation') and layout.edgeSeparation else 10,
                    layout.vertices if hasattr(layout, 'vertices') and layout.vertices else False
                )
                java_view.setAutomaticLayout(java_auto_layout)
            except (ImportError, AttributeError):
                # AutomaticLayout not available in this version, skip it
                pass

    def _convert_styles(self, configuration: Any, java_views: Any) -> None:
        """Convert view configuration and styles."""
        java_config = java_views.getConfiguration()

        # Convert configuration properties (e.g., c4plantuml.tags for sprite support)
        if hasattr(configuration, 'properties') and configuration.properties:
            for key, value in configuration.properties.items():
                java_config.addProperty(key, str(value))

        # Convert element styles
        if hasattr(configuration, 'styles') and configuration.styles:
            if hasattr(configuration.styles, 'elements') and configuration.styles.elements:
                for element_style in configuration.styles.elements:
                    java_style = java_config.getStyles().addElementStyle(element_style.tag or "")
                    self._apply_element_style(element_style, java_style)

            # Convert relationship styles
            if hasattr(configuration.styles, 'relationships') and configuration.styles.relationships:
                for rel_style in configuration.styles.relationships:
                    java_style = java_config.getStyles().addRelationshipStyle(rel_style.tag or "")
                    self._apply_relationship_style(rel_style, java_style)

    def _apply_element_style(self, style: Any, java_style: Any) -> None:
        """Apply element style properties."""
        if hasattr(style, 'width') and style.width:
            java_style.setWidth(style.width)
        if hasattr(style, 'height') and style.height:
            java_style.setHeight(style.height)
        if hasattr(style, 'background') and style.background:
            java_style.setBackground(style.background)
        if hasattr(style, 'color') and style.color:
            java_style.setColor(style.color)
        if hasattr(style, 'shape') and style.shape:
            from com.structurizr.view import Shape as JavaShape
            java_style.setShape(self._convert_shape(style.shape))
        if hasattr(style, 'icon') and style.icon:
            java_style.setIcon(style.icon)
        if hasattr(style, 'fontSize') and style.fontSize:
            java_style.setFontSize(style.fontSize)

    def _apply_relationship_style(self, style: Any, java_style: Any) -> None:
        """Apply relationship style properties."""
        if hasattr(style, 'thickness') and style.thickness:
            java_style.setThickness(style.thickness)
        if hasattr(style, 'color') and style.color:
            java_style.setColor(style.color)
        if hasattr(style, 'dashed') and style.dashed is not None:
            java_style.setDashed(style.dashed)
        if hasattr(style, 'routing') and style.routing:
            from com.structurizr.view import Routing as JavaRouting
            java_style.setRouting(self._convert_routing(style.routing))
        if hasattr(style, 'fontSize') and style.fontSize:
            java_style.setFontSize(style.fontSize)
        if hasattr(style, 'width') and style.width:
            java_style.setWidth(style.width)
        if hasattr(style, 'position') and style.position:
            java_style.setPosition(style.position)

    def _convert_location(self, location: str) -> Any:
        """Convert Python location string to Java Location enum."""
        location_upper = location.upper()
        if location_upper == "INTERNAL":
            return self.JavaLocation.Internal
        elif location_upper == "EXTERNAL":
            return self.JavaLocation.External
        else:
            return self.JavaLocation.Unspecified

    def _convert_interaction_style(self, style: InteractionStyle) -> Any:
        """Convert Python interaction style to Java InteractionStyle enum."""
        # Convert enum to string and then to upper case
        style_upper = style.value.upper()
        if style_upper == "SYNCHRONOUS":
            return self.JavaInteractionStyle.Synchronous
        elif style_upper == "ASYNCHRONOUS":
            return self.JavaInteractionStyle.Asynchronous
        else:
            return self.JavaInteractionStyle.Synchronous

    def _convert_rank_direction(self, direction: str) -> Any:
        """Convert rank direction string to Java enum."""
        from com.structurizr.view import RankDirection as JavaRankDirection

        direction_upper = direction.upper()
        if direction_upper == "TOPBOTTOM" or direction_upper == "TOP_BOTTOM":
            return JavaRankDirection.TopBottom
        elif direction_upper == "BOTTOMTOP" or direction_upper == "BOTTOM_TOP":
            return JavaRankDirection.BottomTop
        elif direction_upper == "LEFTRIGHT" or direction_upper == "LEFT_RIGHT":
            return JavaRankDirection.LeftRight
        elif direction_upper == "RIGHTLEFT" or direction_upper == "RIGHT_LEFT":
            return JavaRankDirection.RightLeft
        else:
            return JavaRankDirection.TopBottom

    def _convert_shape(self, shape: Union[str, Shape]) -> Any:
        """Convert shape string or enum to Java Shape enum."""
        from com.structurizr.view import Shape as JavaShape

        # Handle Shape enum by extracting its value
        shape_str = shape.value if isinstance(shape, Shape) else shape
        shape_upper = shape_str.upper()
        if shape_upper == "BOX":
            return JavaShape.Box
        elif shape_upper == "ROUNDEDBOX":
            return JavaShape.RoundedBox
        elif shape_upper == "CIRCLE":
            return JavaShape.Circle
        elif shape_upper == "ELLIPSE":
            return JavaShape.Ellipse
        elif shape_upper == "HEXAGON":
            return JavaShape.Hexagon
        elif shape_upper == "CYLINDER":
            return JavaShape.Cylinder
        elif shape_upper == "COMPONENT":
            return JavaShape.Component
        elif shape_upper == "PERSON":
            return JavaShape.Person
        elif shape_upper == "ROBOT":
            return JavaShape.Robot
        elif shape_upper == "FOLDER":
            return JavaShape.Folder
        elif shape_upper == "WEBBROWSER":
            return JavaShape.WebBrowser
        elif shape_upper == "MOBILEDEVICEPORTRAIT":
            return JavaShape.MobileDevicePortrait
        elif shape_upper == "MOBILEDEVICELANDSCAPE":
            return JavaShape.MobileDeviceLandscape
        elif shape_upper == "PIPE":
            return JavaShape.Pipe
        else:
            return JavaShape.Box

    def _is_child_of(self, element: Any, parent: Any) -> bool:
        """Check if element is a child (at any depth) of parent.

        Mirrors the isChildOf() check in Structurizr Java Model.java.
        See: https://github.com/structurizr/java/blob/master/structurizr-core/src/main/java/com/structurizr/model/Model.java
        """
        # Person elements have no parent hierarchy
        if element.getClass().getSimpleName() == "Person":
            return False

        current = element.getParent() if hasattr(element, 'getParent') else None
        while current is not None:
            if current == parent:
                return True
            current = current.getParent() if hasattr(current, 'getParent') else None
        return False

    def _convert_routing(self, routing: str) -> Any:
        """Convert routing string to Java Routing enum."""
        from com.structurizr.view import Routing as JavaRouting

        routing_upper = routing.upper()
        if routing_upper == "DIRECT":
            return JavaRouting.Direct
        elif routing_upper == "ORTHOGONAL":
            return JavaRouting.Orthogonal
        elif routing_upper == "CURVED":
            return JavaRouting.Curved
        else:
            return JavaRouting.Direct
