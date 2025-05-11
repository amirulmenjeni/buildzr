import re
from typing import Tuple, Optional, Union, Literal

class Color:
    r: int
    g: int
    b: int

    _ENGLISH_COLORS = {
        'black': '#000000',
        'white': '#ffffff',
        'red': '#ff0000',
        'green': '#00ff00',
        'blue': '#0000ff',
        'yellow': '#ffff00',
        'cyan': '#00ffff',
        'magenta': '#ff00ff',
        'gray': '#808080',
        'grey': '#808080',
        'orange': '#ffa500',
        'purple': '#800080',
        'pink': '#ffc0cb',
        'brown': '#a52a2a',
        'lime': '#00ff00',
        'navy': '#000080',
        'teal': '#008080',
        'olive': '#808000',
        'maroon': '#800000',
        'silver': '#c0c0c0',
        'gold': '#ffd700',
    }

    def __init__(
        self,
        value: Union[
            'Color',
            str,
            Tuple[int, int, int],
            Literal[
                'black', 'white', 'red', 'green', 'blue', 'yellow', 'cyan', 'magenta', 'gray', 'grey', 'orange', 'purple', 'pink', 'brown', 'lime', 'navy', 'teal', 'olive', 'maroon', 'silver', 'gold'
            ]
        ]
    ):
        if isinstance(value, Color):
            self.r, self.g, self.b = value.r, value.g, value.b
        elif isinstance(value, tuple):
            if len(value) == 3:
                self.r, self.g, self.b = value
            else:
                raise ValueError("Tuple must be (r, g, b)")
        elif isinstance(value, str):
            self.r, self.g, self.b = self._parse_color(value)
        else:
            raise TypeError("Invalid type for Color constructor")

    @classmethod
    def is_valid_color(cls, value: Union[str, Tuple[int, int, int], 'Color']) -> bool:
        try:
            if isinstance(value, tuple):
                if len(value) == 3 and all(isinstance(x, int) and 0 <= x <= 255 for x in value):
                    return True
                return False
            elif isinstance(value, str):
                v = value.strip().lower()
                if v in cls._ENGLISH_COLORS:
                    return True
                if v.startswith('#'):
                    try:
                        cls._parse_hex(v)
                        return True
                    except Exception:
                        return False
                if v.startswith('rgb'):
                    try:
                        cls._parse_rgb(v)
                        return True
                    except Exception:
                        return False
                return False
            return False
        except Exception:
            return False

    @classmethod
    def _parse_color(cls, value: str) -> Tuple[int, int, int]:
        value = value.strip().lower()
        if value in cls._ENGLISH_COLORS:
            value = cls._ENGLISH_COLORS[value]
        if value.startswith('#'):
            return cls._parse_hex(value)
        if value.startswith('rgb'):
            return cls._parse_rgb(value)
        raise ValueError(f"Unknown color format: {value}")

    @classmethod
    def _parse_hex(cls, value: str) -> Tuple[int, int, int]:
        value = value.lstrip('#')
        if len(value) == 3:
            value = ''.join([c*2 for c in value])
        if len(value) == 6:
            r, g, b = value[0:2], value[2:4], value[4:6]
            return int(r, 16), int(g, 16), int(b, 16)
        raise ValueError(f"Invalid hex color: #{value}")

    @classmethod
    def _parse_rgb(cls, value: str) -> Tuple[int, int, int]:
        # Match rgb(r, g, b)
        match = re.match(r"rgb\(([^)]+)\)", value)
        if not match:
            raise ValueError(f"Invalid rgb color: {value}")
        parts = [x.strip() for x in match.group(1).split(',')]
        if len(parts) == 3:
            r, g, b = map(int, parts)
            return r, g, b
        raise ValueError(f"Invalid rgb color: {value}")

    def to_hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    def __str__(self) -> str:
        return f"rgb({self.r}, {self.g}, {self.b})"