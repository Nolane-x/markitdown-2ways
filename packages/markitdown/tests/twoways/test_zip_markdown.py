from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import MarkdownImportError
from markitdown.twoways.formats.zip.reader import read_zip_ir
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    import_identity_markdown,
    project_markdown,
)

from ._xlsx_fixtures import make_xlsx
from ._zip_fixtures import make_zip


def _identity_projection():
    source = make_zip(members={"book.xlsx": make_xlsx()})
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )
    return document, projection


def test_zip_identity_markdown_renders_nested_content_as_inspection_only() -> None:
    document, projection = _identity_projection()

    nested_ids = {
        node.node_id
        for node in document.nodes.values()
        if node.metadata.get("zip.member_chain") == ("book.xlsx",)
        and node.metadata.get("zip.identity_markdown") is False
    }
    nested_blocks = [
        block for block in projection.manifest.blocks if block.node_id in nested_ids
    ]

    assert nested_blocks
    assert all(block.editable_capabilities == () for block in nested_blocks)
    assert "North" in projection.markdown
    assert "East" in projection.markdown
    assert "untouched" in projection.markdown

    unchanged = import_identity_markdown(
        projection.markdown,
        original_document=document,
        manifest=projection.manifest,
    )
    assert unchanged.edits == ()


def test_zip_identity_markdown_cannot_emit_nested_member_edits() -> None:
    document, projection = _identity_projection()
    edited = projection.markdown.replace("North", "Changed", 1)
    assert edited != projection.markdown

    with pytest.raises(MarkdownImportError, match="read-only"):
        import_identity_markdown(
            edited,
            original_document=document,
            manifest=projection.manifest,
        )
