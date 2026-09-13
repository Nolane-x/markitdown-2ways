from __future__ import annotations

from io import BytesIO

from markitdown.twoways.formats.ipynb.reader import read_ipynb_ir
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    import_identity_markdown,
    project_markdown,
)


def _source():
    return (
        b'{"cells":['
        b'{"cell_type":"markdown","metadata":{},"source":["# Title\\n","body"]},'
        b'{"cell_type":"code","execution_count":null,"metadata":{},"outputs":[],"source":"print(1)"},'
        b'{"cell_type":"raw","metadata":{},"source":["raw"]}'
        b'],"metadata":{},"nbformat":4,"nbformat_minor":5}'
    )


def test_ipynb_identity_markdown_is_inspection_only() -> None:
    document = read_ipynb_ir(BytesIO(_source()), filename="book.ipynb")

    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )

    assert len(projection.manifest.blocks) == 3
    assert all(block.node_kind == "text" for block in projection.manifest.blocks)
    assert all(block.editable_capabilities == () for block in projection.manifest.blocks)
    assert "# Title" in projection.markdown
    assert "print(1)" in projection.markdown
    assert "raw" in projection.markdown

    unchanged = import_identity_markdown(
        projection.markdown,
        original_document=document,
        manifest=projection.manifest,
    )
    assert unchanged.edits == ()


def test_read_only_unknown_cell_source_stays_inspection_only() -> None:
    source = (
        b'{"cells":[{"cell_type":"mystery","metadata":{},"source":"opaque"}],'
        b'"metadata":{},"nbformat":4,"nbformat_minor":5}'
    )
    document = read_ipynb_ir(BytesIO(source), filename="book.ipynb")

    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )

    assert len(projection.manifest.blocks) == 1
    assert projection.manifest.blocks[0].editable_capabilities == ()
    assert "opaque" in projection.markdown
