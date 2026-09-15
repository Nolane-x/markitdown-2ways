from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.pdf import writer as pdf_writer
from markitdown.twoways.formats.pdf.parser import parse_pdf_source
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.formats.pdf.writer import patch_pdf
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition

from ._pdf_fixtures import make_text_form_pdf


def _form_node(document):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "pdf-form-text-value"
    )


def _form_edit(document, value: str = "Bob") -> EditOperation:
    node = _form_node(document)
    return EditOperation(
        operation_id="hardening-form",
        type="update_pdf_text_field_value",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_old_value=node.payload.text),
        payload={
            "field_name": node.metadata["pdf.form_field_name"],
            "old_value": node.payload.text,
            "value": value,
        },
    )


def _with_xmp_source_policy(source: bytes) -> bytes:
    writer = PdfWriter(BytesIO(source), incremental=True, strict=True)
    xmp = DecodedStreamObject()
    xmp.set_data(b"<x:xmpmeta xmlns:x='adobe:ns:meta/'></x:xmpmeta>")
    xmp[NameObject("/Type")] = NameObject("/Metadata")
    xmp[NameObject("/Subtype")] = NameObject("/XML")
    writer._root_object[NameObject("/Metadata")] = writer._add_object(xmp)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_form_parser_inherits_source_policy_block() -> None:
    source = _with_xmp_source_policy(make_text_form_pdf())

    parsed = parse_pdf_source(source)

    assert parsed.snapshot.has_xmp is True
    assert len(parsed.form_fields) == 1
    assert parsed.form_fields[0].writable is False
    assert parsed.form_fields[0].reason_code == "pdf.form.source_policy"


def test_pdf_form_writer_never_calls_generic_pypdf_form_updater(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    output = BytesIO()

    def forbidden(*args, **kwargs):
        raise AssertionError("generic pypdf form updater must not be called")

    monkeypatch.setattr(
        pdf_writer.PdfWriter,
        "update_page_form_field_values",
        forbidden,
    )

    patch_pdf(
        document,
        BytesIO(source),
        output,
        edits=(_form_edit(document),),
    )

    candidate = parse_pdf_source(output.getvalue())
    assert candidate.form_fields[0].value == "Bob"


def test_pdf_form_writer_verifier_failure_leaves_caller_output_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    output = BytesIO()

    def reject(*args, **kwargs):
        raise RoundTripVerificationError(
            "forced verifier failure",
            details={"reason": "pdf.candidate.forced_failure"},
        )

    monkeypatch.setattr(pdf_writer, "verify_pdf_candidate", reject)

    with pytest.raises(RoundTripVerificationError) as exc:
        patch_pdf(
            document,
            BytesIO(source),
            output,
            edits=(_form_edit(document),),
        )

    assert exc.value.details["reason"] == "pdf.candidate.forced_failure"
    assert output.getvalue() == b""
