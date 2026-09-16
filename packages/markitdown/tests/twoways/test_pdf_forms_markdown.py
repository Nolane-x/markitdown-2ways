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

from ._pdf_fixtures import make_text_form_pdf


def _projection():
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )
    field = next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "pdf-form-text-value"
    )
    block = next(
        block for block in projection.manifest.blocks if block.node_id == field.node_id
    )
    return document, projection, block


def test_pdf_form_identity_markdown_is_inspection_only() -> None:
    document, projection, block = _projection()

    assert block.editable_capabilities == ()
    assert "Alice" in projection.markdown
    unchanged = import_identity_markdown(
        projection.markdown,
        original_document=document,
        manifest=projection.manifest,
    )
    assert unchanged.edits == ()


def test_pdf_form_identity_markdown_cannot_emit_form_value_edit() -> None:
    document, projection, _block = _projection()
    edited = projection.markdown.replace("Alice", "Bob", 1)
    assert edited != projection.markdown

    with pytest.raises(MarkdownImportError, match="read-only"):
        import_identity_markdown(
            edited,
            original_document=document,
            manifest=projection.manifest,
        )
