from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .geometry import Geometry
from .provenance import NativeLocator, Provenance
from .style import Style


INITIAL_NODE_KINDS = frozenset({
    "text", "image", "table", "chart", "group", "shape", "note", "unknown_native"
})


@dataclass(frozen=True)
class TextRun:
    text: str
    style: Style | None = None
    native_locator: NativeLocator | None = None


@dataclass(frozen=True)
class Paragraph:
    runs: tuple[TextRun, ...] = ()
    list_level: int | None = None
    alignment: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.list_level is not None and self.list_level < 0:
            raise ValueError("list_level must be non-negative")
        object.__setattr__(self, "runs", tuple(self.runs))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class TextPayload:
    text: str = ""
    paragraphs: tuple[Paragraph, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "paragraphs", tuple(self.paragraphs))


@dataclass(frozen=True)
class ImagePayload:
    resource_id: str
    alt_text: str | None = None
    crop: Mapping[str, float] = field(default_factory=dict)
    original_width: float | None = None
    original_height: float | None = None

    def __post_init__(self) -> None:
        if not self.resource_id:
            raise ValueError("resource_id must be non-empty")
        if self.original_width is not None and self.original_width < 0:
            raise ValueError("original_width must be non-negative")
        if self.original_height is not None and self.original_height < 0:
            raise ValueError("original_height must be non-negative")
        object.__setattr__(self, "crop", dict(self.crop))


@dataclass(frozen=True)
class TableCell:
    row: int
    column: int
    row_span: int = 1
    column_span: int = 1
    text: str | None = None
    node_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.row < 0 or self.column < 0:
            raise ValueError("table cell row/column must be non-negative")
        if self.row_span < 1 or self.column_span < 1:
            raise ValueError("table cell spans must be >= 1")
        object.__setattr__(self, "node_ids", tuple(self.node_ids))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class TablePayload:
    rows: int
    columns: int
    cells: tuple[TableCell, ...] = ()

    def __post_init__(self) -> None:
        if self.rows < 0 or self.columns < 0:
            raise ValueError("table rows/columns must be non-negative")
        object.__setattr__(self, "cells", tuple(self.cells))


@dataclass(frozen=True)
class ChartPayload:
    chart_type: str | None = None
    title: str | None = None
    categories: tuple[Any, ...] = ()
    series: tuple[Mapping[str, Any], ...] = ()
    native_payload_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "categories", tuple(self.categories))
        object.__setattr__(self, "series", tuple(dict(item) for item in self.series))


@dataclass(frozen=True)
class UnknownNativePayload:
    native_payload_ref: str
    summary: str | None = None

    def __post_init__(self) -> None:
        if not self.native_payload_ref:
            raise ValueError("native_payload_ref must be non-empty")


NodePayload = TextPayload | ImagePayload | TablePayload | ChartPayload | UnknownNativePayload | Mapping[str, Any] | None


@dataclass(frozen=True)
class Node:
    node_id: str
    kind: str
    semantic_role: str | None = None
    parent_id: str | None = None
    children: tuple[str, ...] = ()
    order: int = 0
    canvas_id: str | None = None
    geometry: Geometry | None = None
    style: Style | None = None
    provenance: tuple[Provenance, ...] = ()
    native_locator: NativeLocator | None = None
    payload: NodePayload = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("node_id must be non-empty")
        if not self.kind:
            raise ValueError("kind must be non-empty")
        if self.order < 0:
            raise ValueError("order must be non-negative")
        object.__setattr__(self, "children", tuple(self.children))
        object.__setattr__(self, "provenance", tuple(self.provenance))
        if isinstance(self.payload, Mapping):
            object.__setattr__(self, "payload", dict(self.payload))
        object.__setattr__(self, "metadata", dict(self.metadata))
