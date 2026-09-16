from __future__ import annotations

from io import BytesIO

from markitdown.twoways.formats.xml.reader import read_xml_ir
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    import_identity_markdown,
    project_markdown,
)


def test_xml_identity_markdown_is_inspection_only() -> None:
    document = read_xml_ir(
        BytesIO(b'<root id="7"><name>Ada</name><!--keep--></root>'),
        filename="data.xml",
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
