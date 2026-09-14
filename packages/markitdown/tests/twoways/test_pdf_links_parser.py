from __future__ import annotations

from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)

from markitdown.twoways.formats.pdf.parser import parse_pdf_source


def _uri_link_pdf(*, indirect_action: bool) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 fixture"})

    action = DictionaryObject(
        {
            NameObject("/S"): NameObject("/URI"),
            NameObject("/URI"): TextStringObject("https://example.com/old"),
        }
    )
    action_value = writer._add_object(action) if indirect_action else action
    annotation = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/Rect"): RectangleObject(
                [NumberObject(10), NumberObject(10), NumberObject(120), NumberObject(30)]
            ),
            NameObject("/A"): action_value,
        }
    )
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])

    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def test_parser_materializes_direct_action_uri_link_owner() -> None:
    parsed = parse_pdf_source(_uri_link_pdf(indirect_action=False))

    assert len(parsed.links) == 1
    link = parsed.links[0]
    assert link.page_index == 0
    assert link.annotation_index == 0
    assert link.uri == "https://example.com/old"
    assert link.owner_kind == "annotation"
    assert link.annotation_objgen is not None
    assert link.action_objgen is None
    assert link.mutation_owner_objgen == link.annotation_objgen
    assert link.writable is True


def test_parser_materializes_indirect_action_uri_link_owner() -> None:
    parsed = parse_pdf_source(_uri_link_pdf(indirect_action=True))

    assert len(parsed.links) == 1
    link = parsed.links[0]
    assert link.owner_kind == "action"
    assert link.action_objgen is not None
    assert link.mutation_owner_objgen == link.action_objgen
    assert link.annotation_objgen != link.action_objgen
    assert link.writable is True
