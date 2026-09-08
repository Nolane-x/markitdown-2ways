from __future__ import annotations

from dataclasses import dataclass

from .model import ProjectionDiagnostic


@dataclass(frozen=True)
class RenderedNode:
    markdown: str
    semantic_text: str
    editable_capabilities: tuple[str, ...] = ()
    diagnostics: tuple[ProjectionDiagnostic, ...] = ()
