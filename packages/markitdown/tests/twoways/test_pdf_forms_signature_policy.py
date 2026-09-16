from __future__ import annotations

import pytest

from markitdown.twoways.formats.pdf.parser import parse_pdf_source

from ._pdf_fixtures import _build_pdf


def _sigflags_form_pdf(sig_flags: bytes) -> bytes:
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R /AcroForm 5 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Annots [6 0 R] >>",
        4: b"<< /Title (H11 signature policy) >>",
        5: b"<< /Fields [6 0 R] /NeedAppearances true /SigFlags "
        + sig_flags
        + b" /DA (/Helv 0 Tf 0 g) /DR << /Font << /Helv << /Type /Font "
        b"/Subtype /Type1 /BaseFont /Helvetica >> >> >> >>",
        6: b"<< /FT /Tx /Subtype /Widget /T (customer.name) /V (Alice) "
        b"/Rect [72 700 240 724] /Ff 0 >>",
    }
    return _build_pdf(objects)


@pytest.mark.parametrize("sig_flags", [b"1", b"2", b"3"])
def test_pdf_form_parser_inherits_sigflags_signature_policy(sig_flags: bytes) -> None:
    parsed = parse_pdf_source(_sigflags_form_pdf(sig_flags))

    assert parsed.snapshot.has_signature is True
    assert "pdf.security.signature_present" in parsed.diagnostics
    assert len(parsed.form_fields) == 1
    assert parsed.form_fields[0].writable is False
    assert parsed.form_fields[0].reason_code == "pdf.form.source_policy"


def test_pdf_form_parser_fails_closed_on_malformed_sigflags() -> None:
    parsed = parse_pdf_source(_sigflags_form_pdf(b"(1)"))

    assert parsed.snapshot.has_signature is True
    assert "pdf.security.signature_present" in parsed.diagnostics
    assert len(parsed.form_fields) == 1
    assert parsed.form_fields[0].writable is False
    assert parsed.form_fields[0].reason_code == "pdf.form.source_policy"
