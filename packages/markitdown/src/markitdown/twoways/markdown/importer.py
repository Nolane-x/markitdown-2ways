from __future__ import annotations

from ..ir.document import DocumentIR
from ._import_edits import generate_identity_edits
from ._import_integrity import validate_identity_input
from .model import MarkdownImportResult, ProjectionManifest


def import_identity_markdown(
    edited_markdown: str,
    *,
    original_document: DocumentIR,
    manifest: ProjectionManifest,
    strict: bool = True,
) -> MarkdownImportResult:
    envelope = validate_identity_input(
        edited_markdown,
        original_document=original_document,
        manifest=manifest,
        strict=strict,
    )
    return generate_identity_edits(envelope, original_document=original_document)
