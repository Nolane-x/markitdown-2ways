from __future__ import annotations

from io import BytesIO

from markitdown.twoways.formats.html.reader import read_html_ir
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    import_identity_markdown,
    project_markdown,
)


def test_html_identity_markdown_is_inspection_only() -> None:
    document = read_html_ir(
        BytesIO(b'<html><body><p id="7">Ada</p><!--keep--></body></html>'),
        filename="page.html",
    )

    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(
            mode=MarkdownProjectionMode.IDENTITY,
            include_unknown_placeholders=True,
        ),
    )

    assert projection.manifest.blocks
    assert all(
        block.node_kind == "unknown_native" for block in projection.manifest.blocks
    )
    assert all(
        block.editable_capabilities == () for block in projection.manifest.blocks
    )
    unchanged = import_identity_markdown(
        projection.markdown,
        original_document=document,
        manifest=projection.manifest,
    )
    assert unchanged.edits == ()


def test_recovery_unstable_html_identity_markdown_remains_inspection_only() -> None:
    document = read_html_ir(BytesIO(b"<p>one<p>two"), filename="page.html")

    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(
            mode=MarkdownProjectionMode.IDENTITY,
            include_unknown_placeholders=True,
        ),
    )

    assert len(projection.manifest.blocks) == 1
    assert projection.manifest.blocks[0].editable_capabilities == ()
