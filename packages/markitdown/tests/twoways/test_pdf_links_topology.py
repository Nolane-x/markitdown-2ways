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


def _pdf_with_link_and_sibling_annotation() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 topology"})

    action = DictionaryObject(
        {
            NameObject("/S"): NameObject("/URI"),
            NameObject("/URI"): TextStringObject("https://example.com/old"),
        }
    )
    link = DictionaryObject(
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
            NameObject("/Border"): ArrayObject(
                [NumberObject(0), NumberObject(0), NumberObject(0)]
            ),
            NameObject("/A"): action,
        }
    )
    sibling = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Text"),
            NameObject("/Rect"): RectangleObject(
                [
                    NumberObject(140),
                    NumberObject(10),
                    NumberObject(180),
                    NumberObject(40),
                ]
            ),
            NameObject("/Contents"): TextStringObject("sibling note"),
        }
    )
    page[NameObject("/Annots")] = ArrayObject(
        [writer._add_object(link), writer._add_object(sibling)]
    )

    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def test_pdf_parser_records_complete_page_and_annotation_topology() -> None:
    parsed = parse_pdf_source(_pdf_with_link_and_sibling_annotation())

    assert len(parsed.snapshot.page_objgens) == 1
    assert parsed.snapshot.page_objgens[0] is not None
    assert len(parsed.snapshot.annotation_topology) == 1
    assert len(parsed.snapshot.annotation_topology[0]) == 2
    assert all(objgen is not None for objgen in parsed.snapshot.annotation_topology[0])
    assert len(parsed.snapshot.annotation_fingerprints) == 1
    assert len(parsed.snapshot.annotation_fingerprints[0]) == 2
    assert all(
        len(fingerprint) == 64
        for fingerprint in parsed.snapshot.annotation_fingerprints[0]
    )

    link = parsed.links[0]
    assert parsed.snapshot.annotation_topology[0][0] == link.annotation_objgen
    assert len(link.immutable_digest) == 64
