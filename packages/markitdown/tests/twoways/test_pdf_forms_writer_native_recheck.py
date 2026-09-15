from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.pdf import writer as pdf_writer
from markitdown.twoways.formats.pdf.limits import PdfNativeLimits
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.formats.pdf.routing import resolve_pdf_text_field_value_edit
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition

from ._pdf_fixtures import make_text_form_pdf


def _routed_form_edit(source: bytes):
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    node = next(
        item
        for item in document.nodes.values()
        if item.semantic_role == "pdf-form-text-value"
    )
    edit = EditOperation(
        operation_id="native-recheck",
        type="update_pdf_text_field_value",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_old_value=node.payload.text),
        payload={
            "field_name": node.metadata["pdf.form_field_name"],
            "old_value": node.payload.text,
            "value": "Bob",
        },
    )
    return resolve_pdf_text_field_value_edit(document, source, edit)


@pytest.mark.parametrize(
    "drift",
    ("action", "additional_action", "flags", "max_len", "rect"),
)
def test_pdf_form_native_apply_rechecks_complete_immutable_owner_shape(
    drift: str,
) -> None:
    source = make_text_form_pdf(max_len=40)
    routed = _routed_form_edit(source)
    writer = PdfWriter(BytesIO(source), incremental=True, strict=True)
    owner = pdf_writer._owner_object(writer, routed.field_objgen)

    if drift == "action":
        owner[NameObject("/A")] = DictionaryObject(
            {
                NameObject("/S"): NameObject("/JavaScript"),
                NameObject("/JS"): TextStringObject("blocked"),
            }
        )
    elif drift == "additional_action":
        owner[NameObject("/AA")] = DictionaryObject()
    elif drift == "flags":
        owner[NameObject("/Ff")] = NumberObject(1)
    elif drift == "max_len":
        owner[NameObject("/MaxLen")] = NumberObject(2)
    else:
        owner[NameObject("/Rect")] = ArrayObject(
            [NumberObject(0), NumberObject(0), NumberObject(1), NumberObject(1)]
        )

    with pytest.raises(RoundTripVerificationError) as exc:
        pdf_writer._apply_form_edit(writer, routed, limits=PdfNativeLimits())

    assert exc.value.details["reason"] == "pdf.writer.native_owner_drift"
    assert str(owner.raw_get("/V")) == "Alice"
