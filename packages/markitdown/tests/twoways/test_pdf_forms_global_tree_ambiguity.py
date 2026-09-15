from __future__ import annotations

from markitdown.twoways.formats.pdf.parser import parse_pdf_source

from ._pdf_fixtures import _build_pdf


def _field(name: bytes, value: bytes, *, left: int) -> bytes:
    return (
        b"<< /FT /Tx /Subtype /Widget /T ("
        + name
        + b") /V ("
        + value
        + b") /Rect ["
        + str(left).encode("ascii")
        + b" 700 "
        + str(left + 168).encode("ascii")
        + b" 724] /Ff 0 >>"
    )


def _source(*, fields: bytes, annots: bytes, objects: dict[int, bytes]) -> bytes:
    base = {
        1: b"<< /Type /Catalog /Pages 2 0 R /AcroForm 5 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Annots "
            + annots
            + b" >>"
        ),
        4: b"<< /Title (H11 global ambiguity) >>",
        5: (
            b"<< /Fields "
            + fields
            + b" /NeedAppearances true /DA (/Helv 0 Tf 0 g) "
            + b"/DR << /Font << /Helv << /Type /Font /Subtype /Type1 "
            + b"/BaseFont /Helvetica >> >> >> >>"
        ),
    }
    base.update(objects)
    return _build_pdf(base)


def test_pdf_form_parser_blocks_clean_sibling_when_any_owner_is_aliased() -> None:
    source = _source(
        fields=b"[6 0 R 6 0 R 7 0 R]",
        annots=b"[6 0 R 7 0 R]",
        objects={
            6: _field(b"customer.name", b"Alice", left=72),
            7: _field(b"customer.email", b"a@example.test", left=300),
        },
    )

    parsed = parse_pdf_source(source)

    assert {field.field_name for field in parsed.form_fields} == {
        "customer.name",
        "customer.email",
    }
    assert all(not field.writable for field in parsed.form_fields)
    assert {field.reason_code for field in parsed.form_fields} == {
        "pdf.form.tree_ambiguous"
    }


def test_pdf_form_parser_blocks_clean_sibling_when_any_name_is_duplicated() -> None:
    source = _source(
        fields=b"[6 0 R 7 0 R 8 0 R]",
        annots=b"[6 0 R 7 0 R 8 0 R]",
        objects={
            6: _field(b"duplicate.name", b"Alice", left=72),
            7: _field(b"duplicate.name", b"Bob", left=260),
            8: _field(b"clean.sibling", b"Carol", left=448),
        },
    )

    parsed = parse_pdf_source(source)

    assert {field.field_name for field in parsed.form_fields} == {
        "duplicate.name",
        "clean.sibling",
    }
    assert all(not field.writable for field in parsed.form_fields)
    assert {field.reason_code for field in parsed.form_fields} == {
        "pdf.form.tree_ambiguous"
    }
