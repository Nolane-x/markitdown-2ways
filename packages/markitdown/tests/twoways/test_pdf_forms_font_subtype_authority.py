from __future__ import annotations

import pytest

from markitdown.twoways.formats.pdf.parser import parse_pdf_source

from ._pdf_fixtures import _build_pdf


@pytest.mark.parametrize("subtype", [b"/Bogus", b"/CIDFontType0", b"/CIDFontType2"])
def test_pdf_form_parser_rejects_non_resource_font_subtypes(subtype: bytes) -> None:
    source = _build_pdf(
        {
            1: b"<< /Type /Catalog /Pages 2 0 R /AcroForm 5 0 R >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            3: (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Annots [6 0 R] >>"
            ),
            4: b"<< /Title (H11 font subtype authority) >>",
            5: (
                b"<< /Fields [6 0 R] /NeedAppearances true "
                b"/DA (/Helv 0 Tf 0 g) /DR << /Font << /Helv "
                b"<< /Type /Font /Subtype "
                + subtype
                + b" /BaseFont /Helvetica >> >> >> >>"
            ),
            6: (
                b"<< /FT /Tx /Subtype /Widget /T (customer.name) /V (Alice) "
                b"/Rect [72 700 240 724] /Ff 0 >>"
            ),
        }
    )

    parsed = parse_pdf_source(source)

    assert len(parsed.form_fields) == 1
    assert parsed.form_fields[0].writable is False
    assert parsed.form_fields[0].reason_code == "pdf.form.appearance_authority"
