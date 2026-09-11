from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Mapping

from .edits import EditOperation
from .nodes import Node
from .provenance import NativeLocator
from .resources import NativePayload, Relationship, Resource


SCHEMA_NAME = "MarkItDown2WaysDocument"
SCHEMA_VERSION = "0.1.0"


@dataclass(frozen=True)
class SourceDescriptor:
    format: str
    filename: str | None = None
    mimetype: str | None = None
    uri: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    preserved_source_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.format:
            raise ValueError("format must be non-empty")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")


@dataclass(frozen=True)
class DocumentMetadata:
    title: str | None = None
    subject: str | None = None
    author: str | None = None
    company: str | None = None
    language: str | None = None
    custom: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "custom", dict(self.custom))


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: str
    message: str
    node_id: str | None = None
    canvas_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in {"info", "warning", "error"}:
            raise ValueError("severity must be info, warning, or error")
        object.__setattr__(self, "details", dict(self.details))


@dataclass(frozen=True)
class Canvas:
    canvas_id: str
    index: int
    kind: str
    name: str | None = None
    width: float | None = None
    height: float | None = None
    unit: str | None = None
    root_node_ids: tuple[str, ...] = ()
    native_locator: NativeLocator | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.canvas_id:
            raise ValueError("canvas_id must be non-empty")
        if self.index < 0:
            raise ValueError("canvas index must be non-negative")
        if not self.kind:
            raise ValueError("canvas kind must be non-empty")
        if self.width is not None and self.width < 0:
            raise ValueError("canvas width must be non-negative")
        if self.height is not None and self.height < 0:
            raise ValueError("canvas height must be non-negative")
        object.__setattr__(self, "root_node_ids", tuple(self.root_node_ids))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class DocumentIR:
    document_id: str
    source: SourceDescriptor | None = None
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)
    canvases: tuple[Canvas, ...] = ()
    nodes: Mapping[str, Node] = field(default_factory=dict)
    root_node_ids: tuple[str, ...] = ()
    resources: Mapping[str, Resource] = field(default_factory=dict)
    relationships: tuple[Relationship, ...] = ()
    native_payloads: Mapping[str, NativePayload] = field(default_factory=dict)
    edits: tuple[EditOperation, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    schema_name: str = SCHEMA_NAME
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.document_id:
            raise ValueError("document_id must be non-empty")
        object.__setattr__(self, "canvases", tuple(self.canvases))
        object.__setattr__(self, "nodes", dict(self.nodes))
        object.__setattr__(self, "root_node_ids", tuple(self.root_node_ids))
        object.__setattr__(self, "resources", dict(self.resources))
        object.__setattr__(self, "relationships", tuple(self.relationships))
        object.__setattr__(self, "native_payloads", dict(self.native_payloads))
        object.__setattr__(self, "edits", tuple(self.edits))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


class DocumentIdFactory:
    """Document-local deterministic id factory without time or randomness."""

    def __init__(self, seed: str | None = None) -> None:
        self._seed = seed
        self._counter = 0
        self.reproducible = seed is not None

    def new(self, label: str) -> str:
        self._counter += 1
        if self._seed is None:
            return f"local-{label}-{self._counter}"
        material = f"{self._seed}\0{label}\0{self._counter}".encode("utf-8")
        return f"{label}-{sha256(material).hexdigest()[:24]}"
