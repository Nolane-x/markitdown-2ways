from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Mapping

from ..ir.edits import EditOperation


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _require_digest(value: str | None, field_name: str, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a 64-character SHA-256 hex digest")


class MarkdownProjectionMode(str, Enum):
    CLEAN = "clean"
    IDENTITY = "identity"


@dataclass(frozen=True)
class MarkdownProjectionOptions:
    mode: MarkdownProjectionMode = MarkdownProjectionMode.CLEAN
    include_document_title: bool = True
    include_notes: bool = True
    include_unknown_placeholders: bool = False
    resource_uri_scheme: str = "m2w-resource"

    def __post_init__(self) -> None:
        if not self.resource_uri_scheme:
            raise ValueError("resource_uri_scheme must be non-empty")


@dataclass(frozen=True)
class ProjectionDiagnostic:
    code: str
    severity: str
    message: str
    node_id: str | None = None
    projection_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in {"info", "warning", "error"}:
            raise ValueError("severity must be info, warning, or error")
        object.__setattr__(self, "details", dict(self.details))


@dataclass(frozen=True)
class ProjectionBlock:
    projection_id: str
    node_id: str
    canvas_id: str | None
    node_kind: str
    semantic_role: str | None
    ordinal: int
    source_semantic_digest: str
    native_locator_digest: str | None
    editable_capabilities: tuple[str, ...] = ()
    rendered_digest: str = ""

    def __post_init__(self) -> None:
        if not self.projection_id:
            raise ValueError("projection_id must be non-empty")
        if not self.node_id:
            raise ValueError("node_id must be non-empty")
        if self.ordinal < 0:
            raise ValueError("ordinal must be non-negative")
        _require_digest(self.source_semantic_digest, "source_semantic_digest")
        _require_digest(
            self.native_locator_digest,
            "native_locator_digest",
            optional=True,
        )
        _require_digest(self.rendered_digest, "rendered_digest")
        object.__setattr__(
            self,
            "editable_capabilities",
            tuple(self.editable_capabilities),
        )


@dataclass(frozen=True)
class ProjectionManifest:
    format_version: str
    document_id: str
    document_schema_version: str
    source_document_digest: str
    projection_mode: str
    blocks: tuple[ProjectionBlock, ...] = ()
    diagnostics: tuple[ProjectionDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not self.format_version:
            raise ValueError("format_version must be non-empty")
        if not self.document_id:
            raise ValueError("document_id must be non-empty")
        _require_digest(self.source_document_digest, "source_document_digest")
        if self.projection_mode not in {"clean", "identity"}:
            raise ValueError("projection_mode must be clean or identity")
        object.__setattr__(self, "blocks", tuple(self.blocks))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@dataclass(frozen=True)
class MarkdownProjection:
    markdown: str
    manifest: ProjectionManifest


@dataclass(frozen=True)
class MarkdownImportDiagnostic:
    code: str
    severity: str
    message: str
    node_id: str | None = None
    projection_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in {"info", "warning", "error"}:
            raise ValueError("severity must be info, warning, or error")
        object.__setattr__(self, "details", dict(self.details))


@dataclass(frozen=True)
class MarkdownImportResult:
    edits: tuple[EditOperation, ...] = ()
    unchanged_node_ids: tuple[str, ...] = ()
    diagnostics: tuple[MarkdownImportDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "edits", tuple(self.edits))
        object.__setattr__(self, "unchanged_node_ids", tuple(self.unchanged_node_ids))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


def _json_ready(value):
    from dataclasses import fields, is_dataclass
    if is_dataclass(value):
        return {field.name: _json_ready(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, Enum):
        return value.value
    return value


def projection_manifest_bytes(manifest: ProjectionManifest) -> bytes:
    import json
    return json.dumps(
        _json_ready(manifest),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def projection_manifest_digest(manifest: ProjectionManifest) -> str:
    from hashlib import sha256
    return sha256(projection_manifest_bytes(manifest)).hexdigest()
