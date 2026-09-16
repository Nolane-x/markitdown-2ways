from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)

from markitdown.twoways.formats.pdf.limits import PdfNativeLimits
from markitdown.twoways.formats.pdf.model import PdfParseError
from markitdown.twoways.formats.pdf.parser import parse_pdf_source


def _action(uri: str = "https://example.com/old") -> DictionaryObject:
    return DictionaryObject(
        {
            NameObject("/S"): NameObject("/URI"),
            NameObject("/URI"): TextStringObject(uri),
        }
    )


def _annotation(action: object, *, left: int = 10) -> DictionaryObject:
    return DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/Rect"): RectangleObject(
                [
                    NumberObject(left),
                    NumberObject(10),
                    NumberObject(left + 100),
                    NumberObject(30),
                ]
            ),
            NameObject("/A"): action,
        }
    )


def _write(writer: PdfWriter) -> bytes:
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def _uri_link_pdf(*, indirect_action: bool) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 fixture"})
    action = _action()
    action_value = writer._add_object(action) if indirect_action else action
    page[NameObject("/Annots")] = ArrayObject(
        [writer._add_object(_annotation(action_value))]
    )
    return _write(writer)


def _two_links_with_shared_action_pdf() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 fixture"})
    shared_action = writer._add_object(_action())
    page[NameObject("/Annots")] = ArrayObject(
        [
            writer._add_object(_annotation(shared_action, left=10)),
            writer._add_object(_annotation(shared_action, left=130)),
        ]
    )
    return _write(writer)


def _two_independent_links_pdf() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 fixture"})
    page[NameObject("/Annots")] = ArrayObject(
        [
            writer._add_object(_annotation(_action("https://example.com/a"), left=10)),
            writer._add_object(_annotation(_action("https://example.com/b"), left=130)),
        ]
    )
    return _write(writer)


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


def test_parser_marks_shared_action_owner_read_only() -> None:
    parsed = parse_pdf_source(_two_links_with_shared_action_pdf())

    assert len(parsed.links) == 2
    assert {link.reason_code for link in parsed.links} == {"pdf.link.shared_owner"}
    assert all(not link.writable for link in parsed.links)


def test_parser_marks_competing_destination_read_only() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 fixture"})
    annotation = _annotation(_action())
    annotation[NameObject("/Dest")] = ArrayObject()
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])

    parsed = parse_pdf_source(_write(writer))

    assert len(parsed.links) == 1
    assert parsed.links[0].writable is False
    assert parsed.links[0].reason_code == "pdf.link.competing_destination"


def test_parser_marks_additional_actions_read_only() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 fixture"})
    annotation = _annotation(_action())
    annotation[NameObject("/AA")] = DictionaryObject()
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])

    parsed = parse_pdf_source(_write(writer))

    assert len(parsed.links) == 1
    assert parsed.links[0].writable is False
    assert parsed.links[0].reason_code == "pdf.link.additional_actions"


def test_parser_does_not_expose_unsupported_action_as_uri_capability() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 fixture"})
    action = DictionaryObject(
        {
            NameObject("/S"): NameObject("/GoTo"),
            NameObject("/D"): TextStringObject("destination"),
        }
    )
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(_annotation(action))])

    parsed = parse_pdf_source(_write(writer))

    assert parsed.links == ()


def test_parser_marks_non_text_uri_read_only() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 fixture"})
    action = DictionaryObject(
        {
            NameObject("/S"): NameObject("/URI"),
            NameObject("/URI"): NumberObject(42),
        }
    )
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(_annotation(action))])

    parsed = parse_pdf_source(_write(writer))

    assert len(parsed.links) == 1
    assert parsed.links[0].uri == ""
    assert parsed.links[0].writable is False
    assert parsed.links[0].reason_code == "pdf.link.unsupported_uri"


def test_parser_inherits_source_policy_block_to_uri_links() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 fixture"})
    page[NameObject("/Annots")] = ArrayObject(
        [writer._add_object(_annotation(_action()))]
    )
    xmp = DecodedStreamObject()
    xmp.set_data(b"<x:xmpmeta xmlns:x='adobe:ns:meta/'></x:xmpmeta>")
    xmp[NameObject("/Type")] = NameObject("/Metadata")
    xmp[NameObject("/Subtype")] = NameObject("/XML")
    writer._root_object[NameObject("/Metadata")] = writer._add_object(xmp)

    parsed = parse_pdf_source(_write(writer))

    assert parsed.snapshot.has_xmp is True
    assert "pdf.metadata.xmp_conflict" in parsed.diagnostics
    assert len(parsed.links) == 1
    assert parsed.links[0].writable is False
    assert parsed.links[0].reason_code == "pdf.link.source_policy"


def test_parser_does_not_authorize_direct_annotation_entry() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    writer.add_metadata({"/Title": "H10 fixture"})
    page[NameObject("/Annots")] = ArrayObject([_annotation(_action())])

    parsed = parse_pdf_source(_write(writer))

    assert parsed.links == ()


def test_parser_enforces_total_annotation_limit() -> None:
    with pytest.raises(PdfParseError) as excinfo:
        parse_pdf_source(
            _two_independent_links_pdf(),
            limits=PdfNativeLimits(max_total_annotations=1),
        )

    assert excinfo.value.reason == "pdf.annotations.too_many"


def test_parser_enforces_uri_character_limit() -> None:
    with pytest.raises(PdfParseError) as excinfo:
        parse_pdf_source(
            _uri_link_pdf(indirect_action=False),
            limits=PdfNativeLimits(max_uri_chars=4),
        )

    assert excinfo.value.reason == "pdf.link.uri_too_large"


def test_parser_enforces_total_uri_character_limit() -> None:
    with pytest.raises(PdfParseError) as excinfo:
        parse_pdf_source(
            _two_independent_links_pdf(),
            limits=PdfNativeLimits(max_total_uri_chars=30),
        )

    assert excinfo.value.reason == "pdf.link.total_uri_too_large"
