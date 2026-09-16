from __future__ import annotations

from markitdown.twoways.formats.pdf.parser import parse_pdf_source

from ._pdf_fixtures import _build_pdf


def test_pdf_form_parser_blocks_indirect_field_with_direct_owner() -> None:
    direct_field = (
        b"<< /FT /Tx /Subtype /Widget /T (direct.name) /V (Direct) "
        b"/Rect [300 700 468 724] /Ff 0 >>"
    )
    indirect_field = (
        b"<< /FT /Tx /Subtype /Widget /T (customer.name) /V (Alice) "
        b"/Rect [72 700 240 724] /Ff 0 >>"
    )
    source = _build_pdf(
        {
            1: b"<< /Type /Catalog /Pages 2 0 R /AcroForm 5 0 R >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Annots [6 0 R] >>",
            4: b"<< /Title (H11 direct-owner contamination) >>",
            5: (
                b"<< /Fields ["
                + direct_field
                + b" 6 0 R] /NeedAppearances true "
                + b"/DA (/Helv 0 Tf 0 g) "
                + b"/DR << /Font << /Helv << /Type /Font /Subtype /Type1 "
                + b"/BaseFont /Helvetica >> >> >> >>"
            ),
            6: indirect_field,
        }
    )

    parsed = parse_pdf_source(source)

    assert len(parsed.form_fields) == 1
    assert parsed.form_fields[0].field_name == "customer.name"
    assert parsed.form_fields[0].writable is False
    assert parsed.form_fields[0].reason_code == "pdf.form.tree_ambiguous"
