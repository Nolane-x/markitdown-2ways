from __future__ import annotations

from io import BytesIO

from markitdown.twoways.formats.epub.reader import read_epub_ir
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    import_identity_markdown,
    project_markdown,
)

from ._epub_fixtures import make_epub


def test_epub_identity_markdown_is_inspection_only() -> None:
    document = read_epub_ir(BytesIO(make_epub()), filename="book.epub")

    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )

    assert projection.manifest.blocks
    assert all(block.node_kind == "text" for block in projection.manifest.blocks)
    assert all(
        block.editable_capabilities == () for block in projection.manifest.blocks
    )
    assert "Demo Book" in projection.markdown
    assert "Author One" in projection.markdown
    assert "Hello" in projection.markdown
    assert "world" in projection.markdown

    unchanged = import_identity_markdown(
        projection.markdown,
        original_document=document,
        manifest=projection.manifest,
    )
    assert unchanged.edits == ()


def test_epub_navigation_and_blocked_xhtml_content_remain_noneditable() -> None:
    document = read_epub_ir(BytesIO(make_epub()), filename="book.epub")
    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )

    assert all(
        block.editable_capabilities == () for block in projection.manifest.blocks
    )
    assert "Chapter One" not in projection.markdown
    assert "blocked()" not in projection.markdown
    assert "vector" not in projection.markdown
