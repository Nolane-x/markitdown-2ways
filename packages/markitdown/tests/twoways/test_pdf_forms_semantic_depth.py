from __future__ import annotations

import pytest

from markitdown.twoways.formats.pdf.limits import PdfNativeLimits
from markitdown.twoways.formats.pdf.model import PdfParseError
from markitdown.twoways.formats.pdf.parser import parse_pdf_source

from ._pdf_fixtures import _build_pdf


def test_pdf_form_parser_bounds_nested_field_semantics() -> None:
    nested = b"<< /A << /B << /C (deep) >> >> >>"
    field = (
        b"<< /FT /Tx /Subtype /Widget /T (customer.name) /V (Alice) "
        b"/Rect [72 700 240 724] /Ff 0 /Custom "
        + nested
        + b" >>"
    )
    source = _build_pdf(
        {
            1: b"<< /Type /Catalog /Pages 2 0 R /AcroForm 5 0 R >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            3: (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Annots [6 0 R] >>"
            ),
            4: b"<< /Title (H11 semantic depth) >>",
            5: (
                b"<< /Fields [6 0 R] /NeedAppearances true "
                b"/DA (/Helv 0 Tf 0 g) "
                b"/DR << /Font << /Helv << /Type /Font /Subtype /Type1 "
                b"/BaseFont /Helvetica >> >> >> >>"
            ),
            6: field,
        }
    )

    with pytest.raises(PdfParseError) as excinfo:
        parse_pdf_source(source, limits=PdfNativeLimits(max_field_tree_depth=2))

    assert excinfo.value.reason == "pdf.form.tree_ambiguous"
