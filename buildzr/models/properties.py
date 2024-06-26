from dataclasses import dataclass

@dataclass
class Properties(dict):
    def __setitem__(self, key: str, value: str) -> None:
        return super().__setitem__(key, value)