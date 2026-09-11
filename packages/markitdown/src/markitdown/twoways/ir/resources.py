from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .provenance import NativeLocator


@dataclass(frozen=True)
class Resource:
    resource_id: str
    sha256: str | None = None
    content_type: str | None = None
    filename: str | None = None
    size_bytes: int | None = None
    storage_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.resource_id:
            raise ValueError("resource_id must be non-empty")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class Relationship:
    relationship_id: str
    source_id: str
    kind: str
    target_id: str | None = None
    external_target: str | None = None
    native_locator: NativeLocator | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.relationship_id:
            raise ValueError("relationship_id must be non-empty")
        if not self.source_id:
            raise ValueError("source_id must be non-empty")
        if not self.kind:
            raise ValueError("kind must be non-empty")
        if (self.target_id is None) == (self.external_target is None):
            raise ValueError(
                "exactly one of target_id or external_target must be provided"
            )
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class NativePayload:
    payload_id: str
    backend: str
    content_type: str | None = None
    sha256: str | None = None
    storage_ref: str | None = None
    scope: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.payload_id:
            raise ValueError("payload_id must be non-empty")
        if not self.backend:
            raise ValueError("backend must be non-empty")
        object.__setattr__(self, "metadata", dict(self.metadata))
