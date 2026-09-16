from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import MarkdownImportError
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    import_identity_markdown,
    project_markdown,
)

from ._pdf_fixtures import make_metadata_pdf


def _identity_projection():
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="metadata.pdf")
    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )
    return document, projection


def test_pdf_identity_markdown_renders_metadata_as_inspection_only() -> None:
    document, projection = _identity_projection()

    metadata_ids = {
        node.node_id
        for node in document.nodes.values()
        if node.semantic_role == "pdf-metadata"
        and node.metadata.get("pdf.identity_markdown") is False
    }
    metadata_blocks = [
        block for block in projection.manifest.blocks if block.node_id in metadata_ids
    ]

    assert metadata_blocks
    assert all(block.editable_capabilities == () for block in metadata_blocks)
    assert "Alpha" in projection.markdown
    assert "Ada" in projection.markdown

    unchanged = import_identity_markdown(
        projection.markdown,
        original_document=document,
        manifest=projection.manifest,
    )
    assert unchanged.edits == ()


def test_pdf_identity_markdown_cannot_emit_metadata_edits() -> None:
    document, projection = _identity_projection()
    edited = projection.markdown.replace("Alpha", "Changed", 1)
    assert edited != projection.markdown

    with pytest.raises(MarkdownImportError, match="read-only"):
        import_identity_markdown(
            edited,
            original_document=document,
            manifest=projection.manifest,
        )
