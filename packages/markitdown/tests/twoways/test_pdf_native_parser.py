from __future__ import annotations

from hashlib import sha256

import pytest

from markitdown.twoways.formats.pdf.limits import PdfNativeLimits
from markitdown.twoways.formats.pdf.model import PdfParseError
from markitdown.twoways.formats.pdf.parser import parse_pdf_source

from ._pdf_fixtures import make_metadata_pdf


def test_pdf_parser_binds_source_and_info_authority() -> None:
    source = make_metadata_pdf()
    parsed = parse_pdf_source(source)

    assert parsed.snapshot.source_sha256 == sha256(source).hexdigest()
    assert parsed.snapshot.source_size == len(source)
    assert parsed.snapshot.page_count == 1
    assert parsed.snapshot.root_objgen == (1, 0)
    assert parsed.snapshot.info_objgen == (4, 0)
    assert parsed.snapshot.supported_metadata == {
        "Title": "Alpha",
        "Author": "Ada",
        "Subject": "Spec",
        "Keywords": "one,two",
    }
    assert parsed.writable is True


def test_pdf_parser_rejects_malformed_source() -> None:
    with pytest.raises(PdfParseError) as exc:
        parse_pdf_source(b"not a pdf")

    assert exc.value.reason == "pdf.source.malformed"


def test_pdf_parser_enforces_source_byte_limit() -> None:
    source = make_metadata_pdf()
    limits = PdfNativeLimits(max_source_bytes=len(source) - 1)

    with pytest.raises(PdfParseError) as exc:
        parse_pdf_source(source, limits=limits)

    assert exc.value.reason == "pdf.source.too_large"
