"""Base classes for buildzr theme system."""

from dataclasses import dataclass
from typing import Optional, Iterator, Any
from collections.abc import Mapping
import base64
import urllib.request


@dataclass(frozen=True)
class ThemeElement(Mapping):
    """
    A theme element that can be unpacked into StyleElements kwargs.

    Supports direct unpacking via ** operator:
        StyleElements(on=[my_element], **AWS.EC2_INSTANCE)

    For offline/self-contained workspaces, use as_inline() to embed icons as base64:
        StyleElements(on=[my_element], **AWS.EC2_INSTANCE.as_inline())
    """

    tag: str
    stroke: str
    color: str
    icon_url: str

    # Mapping protocol implementation for ** unpacking
    # Includes 'tag' so legend shows meaningful names like "Amazon Web Services - EC2"
    _style_keys = ('tag', 'stroke', 'color', 'icon')

    def __getitem__(self, key: str) -> str:
        """Get style property by key."""
        if key == 'tag':
            return self.tag
        elif key == 'stroke':
            return self.stroke
        elif key == 'color':
            return self.color
        elif key == 'icon':
            return self.icon_url
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        """Iterate over style keys."""
        return iter(self._style_keys)

    def __len__(self) -> int:
        """Return number of style properties."""
        return len(self._style_keys)

    @property
    def icon_base64(self) -> str:
        """
        Fetch icon and return as base64 data URI.

        The result is cached on the instance for subsequent calls.
        """
        # Check if we have a cached value (stored as a private attribute)
        cache_attr = '_icon_base64_cache'
        cached: str = getattr(self, cache_attr, None)
        if cached is not None:
            return cached

        # Fetch and encode the icon
        with urllib.request.urlopen(self.icon_url) as response:
            data = base64.b64encode(response.read()).decode('utf-8')

        # Determine MIME type from URL extension
        ext = self.icon_url.rsplit('.', 1)[-1].lower()
        mime_types = {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'gif': 'image/gif',
            'svg': 'image/svg+xml',
        }
        mime = mime_types.get(ext, 'image/png')

        result = f'data:{mime};base64,{data}'

        # Cache the result (bypass frozen dataclass restriction)
        object.__setattr__(self, cache_attr, result)

        return result

    def as_inline(self) -> dict:
        """
        Return kwargs with base64-embedded icon for offline use.

        Use this when you need a fully self-contained workspace
        that doesn't depend on external icon URLs.
        """
        return {
            'tag': self.tag,
            'stroke': self.stroke,
            'color': self.color,
            'icon': self.icon_base64,
        }
