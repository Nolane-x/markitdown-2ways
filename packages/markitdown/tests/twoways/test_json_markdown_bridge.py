from __future__ import annotations

from io import BytesIO

from markitdown.twoways.formats.json.reader import read_json_ir
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    project_markdown,
)


def test_json_identity_markdown_is_inspection_only() -> None:
    document = read_json_ir(
        BytesIO(b'{"name":"Ada","nested":[1,true,null]}'),
        filename="data.json",
    )

    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(
            mode=MarkdownProjectionMode.IDENTITY,
            include_unknown_placeholders=True,
        ),
    )

    assert projection.manifest.blocks
    assert all(block.node_kind == "unknown_native" for block in projection.manifest.blocks)
    assert all(block.editable_capabilities == () for block in projection.manifest.blocks)
