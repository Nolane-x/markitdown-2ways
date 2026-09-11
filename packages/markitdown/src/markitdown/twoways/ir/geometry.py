from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Mapping


PORTABLE_UNITS = frozenset({"pt", "in", "px", "emu", "normalized"})


def _require_finite(name: str, value: float | int | None) -> None:
    if value is not None and not isfinite(float(value)):
        raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class Geometry:
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    rotation: float = 0.0
    unit: str = "pt"
    origin: str = "top-left"
    transform: tuple[float, ...] | None = None
    source_values: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("x", "y", "width", "height", "rotation"):
            _require_finite(name, getattr(self, name))
        if self.width < 0:
            raise ValueError("width must be non-negative")
        if self.height < 0:
            raise ValueError("height must be non-negative")
        if self.unit not in PORTABLE_UNITS:
            raise ValueError(f"unsupported geometry unit: {self.unit}")
        if self.transform is not None:
            for index, value in enumerate(self.transform):
                _require_finite(f"transform[{index}]", value)
        object.__setattr__(self, "rotation", self.rotation % 360.0)
        object.__setattr__(self, "source_values", dict(self.source_values))
