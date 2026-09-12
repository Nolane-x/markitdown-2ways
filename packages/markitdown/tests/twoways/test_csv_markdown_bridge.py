from __future__ import annotations

from io import BytesIO

from markitdown.twoways.formats.csv.reader import read_csv_ir
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    import_identity_markdown,
    project_markdown,
)


def test_csv_identity_markdown_is_inspection_only() -> None:
    document = read_csv_ir(BytesIO(b"name,city\nAda,North\n"), filename="people.csv")

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
