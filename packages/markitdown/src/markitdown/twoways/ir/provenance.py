from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Mapping


@dataclass(frozen=True)
class BoundingBox:
    x: float
    y: float
    width: float
    height: float
    unit: str = "pt"

    def __post_init__(self) -> None:
        for name in ("x", "y", "width", "height"):
            if not isfinite(float(getattr(self, name))):
                raise ValueError(f"{name} must be finite")
        if self.width < 0:
            raise ValueError("width must be non-negative")
        if self.height < 0:
            raise ValueError("height must be non-negative")


@dataclass(frozen=True)
class NativeLocator:
    backend: str
    part_uri: str | None = None
    object_id: str | None = None
    creation_id: str | None = None
    relationship_id: str | None = None
    name: str | None = None
    path: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.backend.strip():
            raise ValueError("backend must be non-empty")
        object.__setattr__(self, "attributes", dict(self.attributes))


@dataclass(frozen=True)
class Provenance:
    source_format: str
    canvas_index: int | None = None
    part_uri: str | None = None
    bbox: BoundingBox | None = None
    char_span: tuple[int, int] | None = None
    extraction_method: str | None = None
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_format.strip():
            raise ValueError("source_format must be non-empty")
        if self.confidence is not None:
            if (
                not isfinite(float(self.confidence))
                or not 0.0 <= self.confidence <= 1.0
            ):
                raise ValueError("confidence must be between 0 and 1")
        if self.char_span is not None:
            start, end = self.char_span
            if start < 0 or end < start:
                raise ValueError("char_span must be an ordered non-negative range")
        object.__setattr__(self, "metadata", dict(self.metadata))
