from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Style:
    """Sparse portable style with explicit inheritance layers."""

    direct: Mapping[str, Any] = field(default_factory=dict)
    inherited: Mapping[str, Any] = field(default_factory=dict)
    resolved: Mapping[str, Any] = field(default_factory=dict)
    native_style_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "direct", dict(self.direct))
        object.__setattr__(self, "inherited", dict(self.inherited))
        object.__setattr__(self, "resolved", dict(self.resolved))
