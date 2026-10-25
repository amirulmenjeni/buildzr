"""Base classes for buildzr theme system."""

from dataclasses import dataclass
from typing import Optional, Iterator, Any
from collections.abc import Mapping


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
        The icon as a base64 data URI (see :func:`buildzr.themes.assets.fetch_icon`).

        A theme icon is read from the cache of the pinned structurizr/themes commit, or fetched from it once.
        The result is cached on the instance for subsequent calls.

        Raises:
            buildzr.themes.assets.IconFetchError: When the icon can be neither read from the cache nor fetched.
        """
        cache_attr = '_icon_base64_cache'
        cached: str = getattr(self, cache_attr, None)
        if cached is not None:
            return cached

        from buildzr.themes.assets import fetch_icon
        result = fetch_icon(self.icon_url)

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
