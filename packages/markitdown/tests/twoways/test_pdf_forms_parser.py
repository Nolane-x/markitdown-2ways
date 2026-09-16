from __future__ import annotations

import pytest

from markitdown.twoways.formats.pdf.limits import PdfNativeLimits
from markitdown.twoways.formats.pdf.model import PdfParseError
from markitdown.twoways.formats.pdf.parser import parse_pdf_source

from ._pdf_fixtures import make_text_form_pdf


READ_ONLY = 1
MULTILINE = 1 << 12
PASSWORD = 1 << 13
FILE_SELECT = 1 << 20
COMB = 1 << 24
RICH_TEXT = 1 << 25


def _field(**kwargs):
    parsed = parse_pdf_source(make_text_form_pdf(**kwargs))
    assert len(parsed.form_fields) == 1
    return parsed, parsed.form_fields[0]


def test_parser_materializes_writable_terminal_plain_text_field() -> None:
    parsed, field = _field()

    assert field.field_name == "customer.name"
    assert field.field_objgen == (6, 0)
    assert field.page_index == 0
    assert field.annotation_index == 0
    assert field.value == "Alice"
    assert field.field_type == "/Tx"
    assert field.field_flags == 0
    assert field.max_len is None
    assert field.acroform_objgen == (5, 0)
    assert field.need_appearances is True
    assert len(field.locator_digest) == 64
    assert len(field.immutable_digest) == 64
    assert field.writable is True
    assert field.reason_code is None
    assert parsed.snapshot.acroform_objgen == (5, 0)
    assert parsed.snapshot.need_appearances is True


@pytest.mark.parametrize("need_appearances", [None, False])
def test_parser_requires_existing_true_need_appearances(need_appearances) -> None:
    _, field = _field(need_appearances=need_appearances)

    assert field.writable is False
    assert field.reason_code == "pdf.form.need_appearances_required"


def test_parser_rejects_existing_appearance_stream() -> None:
    _, field = _field(with_ap=True)

    assert field.writable is False
    assert field.reason_code == "pdf.form.appearance_present"


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"with_xfa": True}, "pdf.form.xfa"),
        ({"with_co": True}, "pdf.form.calculation_order"),
        ({"with_aa": True}, "pdf.form.additional_actions"),
        ({"with_action": True}, "pdf.form.additional_actions"),
        ({"with_parent": True}, "pdf.form.field_hierarchy"),
        ({"with_kids": True}, "pdf.form.field_hierarchy"),
        ({"field_flags": READ_ONLY}, "pdf.form.read_only"),
        ({"field_flags": MULTILINE}, "pdf.form.unsupported_text_mode"),
        ({"field_flags": PASSWORD}, "pdf.form.unsupported_text_mode"),
        ({"field_flags": FILE_SELECT}, "pdf.form.unsupported_text_mode"),
        ({"field_flags": COMB}, "pdf.form.unsupported_text_mode"),
        ({"field_flags": RICH_TEXT}, "pdf.form.unsupported_text_mode"),
        ({"non_text_value": True}, "pdf.form.non_text_value"),
    ],
)
def test_parser_marks_unsupported_form_shapes_read_only(kwargs, reason) -> None:
    _, field = _field(**kwargs)

    assert field.writable is False
    assert field.reason_code == reason


def test_parser_enforces_max_len_as_field_capability() -> None:
    _, field = _field(value="Alice", max_len=4)

    assert field.max_len == 4
    assert field.writable is False
    assert field.reason_code == "pdf.form.max_length"


def test_parser_marks_duplicate_fully_qualified_names_read_only() -> None:
    parsed = parse_pdf_source(make_text_form_pdf(duplicate_field_name=True))

    assert len(parsed.form_fields) == 2
    assert {field.field_name for field in parsed.form_fields} == {"customer.name"}
    assert {field.reason_code for field in parsed.form_fields} == {
        "pdf.form.tree_ambiguous"
    }
    assert all(not field.writable for field in parsed.form_fields)


def test_parser_marks_duplicate_page_binding_read_only() -> None:
    parsed = parse_pdf_source(make_text_form_pdf(duplicate_page_binding=True))

    assert len(parsed.form_fields) == 1
    field = parsed.form_fields[0]
    assert field.writable is False
    assert field.reason_code == "pdf.form.widget_binding"


def test_parser_does_not_authorize_direct_root_field() -> None:
    parsed = parse_pdf_source(make_text_form_pdf(direct_field=True))

    assert parsed.form_fields == ()


def test_parser_enforces_field_name_character_limit() -> None:
    with pytest.raises(PdfParseError) as excinfo:
        parse_pdf_source(
            make_text_form_pdf(field_name="customer.name"),
            limits=PdfNativeLimits(max_field_name_chars=4),
        )

    assert excinfo.value.reason == "pdf.form.value_too_large"


def test_parser_enforces_form_value_character_limit() -> None:
    with pytest.raises(PdfParseError) as excinfo:
        parse_pdf_source(
            make_text_form_pdf(value="Alice"),
            limits=PdfNativeLimits(max_form_value_chars=4),
        )

    assert excinfo.value.reason == "pdf.form.value_too_large"


def test_parser_enforces_total_form_value_character_limit() -> None:
    with pytest.raises(PdfParseError) as excinfo:
        parse_pdf_source(
            make_text_form_pdf(second_field=True),
            limits=PdfNativeLimits(max_total_form_value_chars=8),
        )

    assert excinfo.value.reason == "pdf.form.total_value_too_large"


def test_parser_enforces_total_form_field_limit() -> None:
    with pytest.raises(PdfParseError) as excinfo:
        parse_pdf_source(
            make_text_form_pdf(second_field=True),
            limits=PdfNativeLimits(max_total_form_fields=1),
        )

    assert excinfo.value.reason == "pdf.form.too_many_fields"
