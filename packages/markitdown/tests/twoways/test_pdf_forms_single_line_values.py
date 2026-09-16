from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import UnsupportedEditError
from markitdown.twoways.formats.pdf.parser import parse_pdf_source
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.formats.pdf.routing import resolve_pdf_text_field_value_edit
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition

from ._pdf_fixtures import make_text_form_pdf


@pytest.mark.parametrize("value", ["Alice\nMallory", "Alice\rMallory"])
def test_pdf_form_parser_rejects_line_breaks_in_single_line_source_value(
    value: str,
) -> None:
    parsed = parse_pdf_source(make_text_form_pdf(value=value))

    assert len(parsed.form_fields) == 1
    assert parsed.form_fields[0].writable is False
    assert parsed.form_fields[0].reason_code == "pdf.form.unsupported_text_mode"


@pytest.mark.parametrize("value", ["Bob\nMallory", "Bob\rMallory"])
def test_pdf_form_routing_rejects_line_breaks_in_single_line_replacement(
    value: str,
) -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    node = next(
        item
        for item in document.nodes.values()
        if item.semantic_role == "pdf-form-text-value"
    )
    edit = EditOperation(
        operation_id="single-line-value",
        type="update_pdf_text_field_value",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_old_value=node.payload.text),
        payload={
            "field_name": node.metadata["pdf.form_field_name"],
            "old_value": node.payload.text,
            "value": value,
        },
    )

    with pytest.raises(UnsupportedEditError) as excinfo:
        resolve_pdf_text_field_value_edit(document, source, edit)

    assert excinfo.value.details["reason"] == "pdf.form.unsupported_text_mode"
