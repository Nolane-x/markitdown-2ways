from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)

from markitdown.twoways._errors import MarkdownImportError
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.markdown import (
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    import_identity_markdown,
    project_markdown,
)


def _link_pdf() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 markdown"})
    action = DictionaryObject(
        {
            NameObject("/S"): NameObject("/URI"),
            NameObject("/URI"): TextStringObject("https://example.com/old"),
        }
    )
    annotation = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/Rect"): RectangleObject(
                [
                    NumberObject(10),
                    NumberObject(10),
                    NumberObject(120),
                    NumberObject(30),
                ]
            ),
            NameObject("/A"): action,
        }
    )
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def _projection():
    source = _link_pdf()
    document = read_pdf_ir(BytesIO(source), filename="links.pdf")
    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )
    link = next(
        node for node in document.nodes.values() if node.semantic_role == "pdf-link-uri"
    )
    block = next(
        block for block in projection.manifest.blocks if block.node_id == link.node_id
    )
    return document, projection, block


def test_pdf_link_identity_markdown_is_inspection_only() -> None:
    document, projection, block = _projection()

    assert block.editable_capabilities == ()
    assert "https://example.com/old" in projection.markdown
    unchanged = import_identity_markdown(
        projection.markdown,
        original_document=document,
        manifest=projection.manifest,
    )
    assert unchanged.edits == ()


def test_pdf_link_identity_markdown_cannot_emit_uri_edit() -> None:
    document, projection, _block = _projection()
    edited = projection.markdown.replace(
        "https://example.com/old",
        "https://example.com/changed",
        1,
    )
    assert edited != projection.markdown

    with pytest.raises(MarkdownImportError, match="read-only"):
        import_identity_markdown(
            edited,
            original_document=document,
            manifest=projection.manifest,
        )
