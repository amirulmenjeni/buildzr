from dataclasses import dataclass, field
from .system_landscape_view import SystemLandscapeView
from .system_context_view import SystemContextView
from .container_view import ContainerView
from .component_view import ComponentView

@dataclass
class Views:

    system_landscape_views: list[SystemLandscapeView] = field(default_factory=list)

    system_context_views: list[SystemContextView] = field(default_factory=list)

    container_views: list[ContainerView] = field(default_factory=list)

    component_views: list[ComponentView] = field(default_factory=list)