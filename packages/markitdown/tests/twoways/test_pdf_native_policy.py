from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter

from markitdown.twoways.formats.pdf.limits import PdfNativeLimits
from markitdown.twoways.formats.pdf.model import PdfParseError
from markitdown.twoways.formats.pdf.parser import parse_pdf_source

from ._pdf_fixtures import make_metadata_pdf


def _policy_pdf(
    *,
    catalog_extra: bytes = b"",
    title_token: bytes = b"(Alpha)",
    extra_objects: dict[int, bytes] | None = None,
) -> bytes:
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R" + catalog_extra + b" >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
        4: (
            b"<< /Title "
            + title_token
            + b" /Author (Ada) /Subject (Spec) /Keywords (one,two) >>"
        ),
    }
    objects.update(extra_objects or {})

    output = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(output)
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(objects[number])
        output.extend(b"\nendobj\n")

    max_object = max(objects)
    xref_offset = len(output)
    output.extend(f"xref\n0 {max_object + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for number in range(1, max_object + 1):
        output.extend(f"{offsets[number]:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {max_object + 1} /Root 1 0 R /Info 4 0 R >>\n".encode(
            "ascii"
        )
    )
    output.extend(f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(output)


def _encrypted_pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata(
        {
            "/Title": "Alpha",
            "/Author": "Ada",
            "/Subject": "Spec",
            "/Keywords": "one,two",
        }
    )
    writer.encrypt("secret")
    writer.write(output)
    return output.getvalue()


def _two_page_pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata({"/Title": "Alpha"})
    writer.write(output)
    return output.getvalue()


def test_pdf_parser_marks_xmp_conflict_read_only() -> None:
    xml = b"<x:xmpmeta xmlns:x='adobe:ns:meta/'></x:xmpmeta>"
    metadata = (
        f"<< /Type /Metadata /Subtype /XML /Length {len(xml)} >>\n".encode("ascii")
        + b"stream\n"
        + xml
        + b"\nendstream"
    )
    parsed = parse_pdf_source(
        _policy_pdf(
            catalog_extra=b" /Metadata 5 0 R",
            extra_objects={5: metadata},
        )
    )

    assert parsed.snapshot.has_xmp is True
    assert parsed.writable is False
    assert "pdf.metadata.xmp_conflict" in parsed.diagnostics


def test_pdf_parser_marks_signature_field_read_only() -> None:
    parsed = parse_pdf_source(
        _policy_pdf(
            catalog_extra=b" /AcroForm 5 0 R",
            extra_objects={
                5: b"<< /Fields [6 0 R] >>",
                6: b"<< /FT /Sig /T (Signature1) >>",
            },
        )
    )

    assert parsed.snapshot.has_signature is True
    assert parsed.writable is False
    assert "pdf.security.signature_present" in parsed.diagnostics


def test_pdf_parser_marks_certification_policy_read_only() -> None:
    parsed = parse_pdf_source(
        _policy_pdf(
            catalog_extra=b" /Perms << /DocMDP 5 0 R >>",
            extra_objects={5: b"<< /Type /Sig >>"},
        )
    )

    assert parsed.snapshot.has_certification is True
    assert parsed.writable is False
    assert "pdf.security.certification_present" in parsed.diagnostics


def test_pdf_parser_marks_linearized_source_read_only() -> None:
    parsed = parse_pdf_source(_policy_pdf(catalog_extra=b" /Linearized 1"))

    assert parsed.snapshot.linearized is True
    assert parsed.writable is False
    assert "pdf.structure.linearized" in parsed.diagnostics


def test_pdf_parser_marks_non_text_supported_metadata_read_only() -> None:
    parsed = parse_pdf_source(_policy_pdf(title_token=b"/UnsupportedName"))

    assert "Title" not in parsed.snapshot.supported_metadata
    assert parsed.writable is False
    assert "pdf.metadata.unsupported_value_type" in parsed.diagnostics


def test_pdf_parser_marks_encrypted_source_read_only() -> None:
    parsed = parse_pdf_source(_encrypted_pdf())

    assert parsed.snapshot.encrypted is True
    assert parsed.writable is False
    assert "pdf.security.encrypted" in parsed.diagnostics


def test_pdf_parser_enforces_page_limit() -> None:
    with pytest.raises(PdfParseError) as exc:
        parse_pdf_source(_two_page_pdf(), limits=PdfNativeLimits(max_pages=1))

    assert exc.value.reason == "pdf.source.too_many_pages"


def test_pdf_parser_marks_metadata_value_limit_read_only() -> None:
    parsed = parse_pdf_source(
        make_metadata_pdf(),
        limits=PdfNativeLimits(max_metadata_value_chars=4),
    )

    assert parsed.writable is False
    assert "pdf.metadata.value_too_large" in parsed.diagnostics


def test_pdf_parser_marks_total_metadata_limit_read_only() -> None:
    parsed = parse_pdf_source(
        make_metadata_pdf(),
        limits=PdfNativeLimits(max_total_metadata_chars=8),
    )

    assert parsed.writable is False
    assert "pdf.metadata.total_too_large" in parsed.diagnostics
