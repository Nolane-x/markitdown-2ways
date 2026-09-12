from __future__ import annotations

from io import BytesIO

from markitdown.twoways.formats.text.reader import read_text_ir
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    import_identity_markdown,
    project_markdown,
)


def test_native_text_source_is_read_only_through_identity_markdown() -> None:
    document = read_text_ir(
        BytesIO(b"literal **stars**  \n\nbody\n"), filename="notes.txt"
    )

    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )

    assert len(projection.manifest.blocks) == 1
    assert projection.manifest.blocks[0].editable_capabilities == ()
    unchanged = import_identity_markdown(
        projection.markdown,
        original_document=document,
        manifest=projection.manifest,
    )
    assert unchanged.edits == ()


def test_native_markdown_source_is_read_only_through_identity_markdown() -> None:
    document = read_text_ir(
        BytesIO(b"# Title\n\nBody with **bold** and  \ntrailing spaces\n"),
        filename="README.md",
        mimetype="text/markdown",
    )

    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )

    assert len(projection.manifest.blocks) == 1
    assert projection.manifest.blocks[0].editable_capabilities == ()
