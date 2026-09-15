from __future__ import annotations

import pytest

from markitdown.twoways.formats.pdf.limits import PdfNativeLimits
from markitdown.twoways.formats.pdf.model import PdfParseError
from markitdown.twoways.formats.pdf.parser import parse_pdf_source

from ._pdf_fixtures import _build_pdf


def _form_pdf(
    *,
    fields: bytes,
    field: bytes,
    include_da: bool = True,
    include_dr: bool = True,
) -> bytes:
    appearance = b""
    if include_da:
        appearance += b" /DA (/Helv 0 Tf 0 g)"
    if include_dr:
        appearance += (
            b" /DR << /Font << /Helv << /Type /Font /Subtype /Type1 "
            b"/BaseFont /Helvetica >> >> >>"
        )
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R /AcroForm 5 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Annots [6 0 R] >>",
        4: b"<< /Title (H11 adversarial) >>",
        5: b"<< /Fields "
        + fields
        + b" /NeedAppearances true"
        + appearance
        + b" >>",
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


def _field_with_name(name: bytes) -> bytes:
    return (
        b"<< /FT /Tx /Subtype /Widget /T "
        + name
        + b" /V (Alice) /Rect [72 700 240 724] /Ff 0 >>"
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


def test_pdf_form_parser_rejects_empty_terminal_field_name() -> None:
    source = _form_pdf(fields=b"[6 0 R]", field=_field_with_name(b"()"))

    parsed = parse_pdf_source(source)

    assert len(parsed.form_fields) == 1
    assert parsed.form_fields[0].writable is False
    assert parsed.form_fields[0].reason_code == "pdf.form.field_name"


def test_pdf_form_parser_counts_direct_field_entries_against_budget() -> None:
    direct = _plain_field()
    source = _form_pdf(fields=b"[" + direct + b" " + direct + b"]", field=_plain_field())

    with pytest.raises(PdfParseError) as excinfo:
        parse_pdf_source(source, limits=PdfNativeLimits(max_total_form_fields=1))

    assert excinfo.value.reason == "pdf.form.too_many_fields"


@pytest.mark.parametrize(
    ("include_da", "include_dr"),
    [(False, True), (True, False)],
)
def test_pdf_form_parser_requires_default_appearance_authority(
    include_da: bool,
    include_dr: bool,
) -> None:
    source = _form_pdf(
        fields=b"[6 0 R]",
        field=_plain_field(),
        include_da=include_da,
        include_dr=include_dr,
    )

    parsed = parse_pdf_source(source)

    assert len(parsed.form_fields) == 1
    assert parsed.form_fields[0].writable is False
    assert parsed.form_fields[0].reason_code == "pdf.form.appearance_authority"
