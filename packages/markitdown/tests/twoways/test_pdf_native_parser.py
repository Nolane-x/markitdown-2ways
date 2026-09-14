from __future__ import annotations

import pytest

from markitdown.twoways.formats.pdf.lexer import (
    decode_pdf_text_string,
    encode_pdf_text_string,
    parse_pdf_dictionary,
)
from markitdown.twoways.formats.pdf.limits import PdfNativeLimits
from markitdown.twoways.formats.pdf.model import PdfIndirectRef, PdfParseError
from markitdown.twoways.formats.pdf.parser import parse_pdf_source

from ._pdf_fixtures import (
    append_classic_revision,
    append_free_info_revision,
    make_classic_pdf,
)


def test_parse_pdf_dictionary_preserves_raw_values_and_indirect_refs() -> None:
    raw = b"<< /Title (A\\(B\\)) /Ref 7 2 R /Flag true /List [1 null /Name] >>"

    parsed = parse_pdf_dictionary(raw, 0, limits=PdfNativeLimits())

    assert parsed.start == 0
    assert parsed.end == len(raw)
    assert parsed.entries["Title"].raw == b"(A\\(B\\))"
    assert parsed.entries["Ref"].value == PdfIndirectRef(7, 2)
    assert parsed.entries["Flag"].value is True
    assert parsed.entries["List"].raw == b"[1 null /Name]"


def test_pdf_text_string_utf16be_hex_round_trip() -> None:
    encoded = encode_pdf_text_string("Nolane Việt")

    assert encoded.startswith(b"<FEFF")
    assert encoded.endswith(b">")
    assert decode_pdf_text_string(encoded, limits=PdfNativeLimits()) == "Nolane Việt"


def test_unterminated_dictionary_fails_closed() -> None:
    with pytest.raises(PdfParseError) as exc:
        parse_pdf_dictionary(b"<< /Title (Alpha)", 0, limits=PdfNativeLimits())

    assert exc.value.reason == "pdf.syntax.unterminated_dictionary"


def test_parse_classic_pdf_resolves_effective_info() -> None:
    source = make_classic_pdf(info={"Title": "Alpha", "Author": "Ada"})

    parsed = parse_pdf_source(source)

    assert parsed.startxref > 0
    assert parsed.revision_count == 1
    assert parsed.root_ref.object_number == 1
    assert parsed.root_ref.generation == 0
    assert parsed.info is not None
    assert parsed.info.ref.object_number == 3
    assert parsed.info.ref.generation == 0
    assert parsed.info.decoded_fields["Title"] == "Alpha"
    assert parsed.info.decoded_fields["Author"] == "Ada"
    assert parsed.writable is True
    assert parsed.read_only_reason is None


def test_parse_classic_pdf_without_info_keeps_creation_authority() -> None:
    source = make_classic_pdf()

    parsed = parse_pdf_source(source)

    assert parsed.info is None
    assert parsed.effective_size == 3
    assert parsed.writable is True
    assert parsed.read_only_reason is None


def test_parse_incremental_chain_uses_newest_info_revision() -> None:
    first = make_classic_pdf(info={"Title": "Alpha", "Author": "Ada"})
    source = append_classic_revision(
        first,
        info_updates={"Title": "Beta", "Author": "Ada"},
    )

    parsed = parse_pdf_source(source)

    assert parsed.revision_count == 2
    assert parsed.info is not None
    assert parsed.info.decoded_fields["Title"] == "Beta"
    assert parsed.info.decoded_fields["Author"] == "Ada"


def test_parse_utf16be_hex_info_string() -> None:
    payload = b"\xfe\xff" + "Nolane Việt".encode("utf-16-be")
    encoded = payload.hex().upper().encode("ascii")
    source = make_classic_pdf(info={"Title": b"<" + encoded + b">"})

    parsed = parse_pdf_source(source)

    assert parsed.info is not None
    assert parsed.info.decoded_fields["Title"] == "Nolane Việt"


def test_newest_free_xref_entry_overrides_older_info_object() -> None:
    source = make_classic_pdf(info={"Title": "Alpha"})
    source = append_free_info_revision(source)

    with pytest.raises(PdfParseError) as exc:
        parse_pdf_source(source)

    assert exc.value.reason == "pdf.info.reference_unavailable"


def test_effective_document_id_is_inherited_across_incremental_revision() -> None:
    document_id = b"[<0011223344556677><8899AABBCCDDEEFF>]"
    first = make_classic_pdf(
        info={"Title": "Alpha"},
        document_id_raw=document_id,
    )
    source = append_classic_revision(first, info_updates={"Title": "Beta"})

    parsed = parse_pdf_source(source)

    assert parsed.document_id_raw == document_id
    assert parsed.trailer_values_raw["ID"] == document_id
