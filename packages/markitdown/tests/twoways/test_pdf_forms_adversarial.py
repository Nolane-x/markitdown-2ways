from __future__ import annotations

import pytest

from markitdown.twoways.formats.pdf.parser import parse_pdf_source

from ._pdf_fixtures import _build_pdf


def _form_pdf(*, fields: bytes, field: bytes) -> bytes:
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R /AcroForm 5 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Annots [6 0 R] >>",
        4: b"<< /Title (H11 adversarial) >>",
        5: b"<< /Fields " + fields + b" /NeedAppearances true /DA (/Helv 0 Tf 0 g) >>",
        6: field,
    }
    return _build_pdf(objects)


def _plain_field(extra: bytes = b"") -> bytes:
    return (
        b"<< /FT /Tx /Subtype /Widget /T (customer.name) /V (Alice) "
        b"/Rect [72 700 240 724] /Ff 0" + extra + b" >>"
    )


def _field_with_flags(flags: bytes) -> bytes:
    return (
        b"<< /FT /Tx /Subtype /Widget /T (customer.name) /V (Alice) "
        b"/Rect [72 700 240 724] /Ff " + flags + b" >>"
    )


def _field_with_max_len(max_len: bytes) -> bytes:
    return (
        b"<< /FT /Tx /Subtype /Widget /T (customer.name) /V (Alice) "
        b"/Rect [72 700 240 724] /Ff 0 /MaxLen " + max_len + b" >>"
    )


def test_pdf_form_parser_fails_closed_on_aliased_field_owner() -> None:
    source = _form_pdf(fields=b"[6 0 R 6 0 R]", field=_plain_field())

    parsed = parse_pdf_source(source)

    assert len(parsed.form_fields) == 1
    assert parsed.form_fields[0].writable is False
    assert parsed.form_fields[0].reason_code == "pdf.form.tree_ambiguous"


def test_pdf_form_parser_fails_closed_on_field_tree_cycle_without_recursion() -> None:
    source = _form_pdf(fields=b"[6 0 R]", field=_plain_field(b" /Kids [6 0 R]"))

    parsed = parse_pdf_source(source)

    assert len(parsed.form_fields) == 1
    assert parsed.form_fields[0].writable is False
    assert parsed.form_fields[0].reason_code == "pdf.form.tree_ambiguous"


def test_pdf_form_parser_marks_malformed_max_len_read_only() -> None:
    source = _form_pdf(fields=b"[6 0 R]", field=_plain_field(b" /MaxLen (bad)"))

    parsed = parse_pdf_source(source)

    assert len(parsed.form_fields) == 1
    assert parsed.form_fields[0].writable is False
    assert parsed.form_fields[0].reason_code == "pdf.form.max_length"


@pytest.mark.parametrize("flags", [b"(0)", b"0.0"])
def test_pdf_form_parser_rejects_coerced_non_integer_field_flags(flags: bytes) -> None:
    source = _form_pdf(fields=b"[6 0 R]", field=_field_with_flags(flags))

    parsed = parse_pdf_source(source)

    assert len(parsed.form_fields) == 1
    assert parsed.form_fields[0].writable is False
    assert parsed.form_fields[0].reason_code == "pdf.form.unsupported_text_mode"


@pytest.mark.parametrize("max_len", [b"(10)", b"10.0"])
def test_pdf_form_parser_rejects_coerced_non_integer_max_len(max_len: bytes) -> None:
    source = _form_pdf(fields=b"[6 0 R]", field=_field_with_max_len(max_len))

    parsed = parse_pdf_source(source)

    assert len(parsed.form_fields) == 1
    assert parsed.form_fields[0].writable is False
    assert parsed.form_fields[0].reason_code == "pdf.form.max_length"
