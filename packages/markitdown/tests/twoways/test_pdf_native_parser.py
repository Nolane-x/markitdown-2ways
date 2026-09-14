from __future__ import annotations

import pytest

from markitdown.twoways.formats.pdf.model import PdfParseError
from markitdown.twoways.formats.pdf.parser import parse_pdf_source

from ._pdf_fixtures import (
    append_classic_revision,
    append_free_info_revision,
    make_classic_pdf,
)


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
