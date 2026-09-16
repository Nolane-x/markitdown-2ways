from __future__ import annotations

from io import BytesIO

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats import pdf as pdf_api
from markitdown.twoways.formats.pdf import PdfPatchWriter, patch_pdf, read_pdf_ir
from markitdown.twoways.formats.pdf.parser import parse_pdf_source
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.writers.base import TargetInfo

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
        operation_id="public-form",
        type="update_pdf_text_field_value",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_old_value=node.payload.text),
        payload={
            "field_name": node.metadata["pdf.form_field_name"],
            "old_value": node.payload.text,
            "value": value,
        },
    )


def _value(data: bytes) -> str:
    field = next(
        item
        for item in parse_pdf_source(data).form_fields
        if item.field_name == "customer.name"
    )
    return field.value


def test_pdf_public_reader_exposes_h11_capability_without_new_api_surface() -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    node = _form_node(document)

    decision = capabilities_for_node(node).for_operation("update_pdf_text_field_value")
    assert decision.state is CapabilityState.WRITABLE
    assert set(pdf_api.__all__) == {
        "PdfIRReader",
        "PdfNativeLimits",
        "PdfParseError",
        "PdfPatchWriter",
        "parse_pdf_source",
        "patch_pdf",
        "read_pdf_ir",
    }


def test_pdf_public_patch_surface_accepts_h11_text_field_edit() -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    output = BytesIO()

    result = patch_pdf(
        document,
        BytesIO(source),
        output,
        edits=(_form_edit(document),),
    )

    candidate = output.getvalue()
    assert result.format == "pdf"
    assert candidate.startswith(source)
    assert _value(candidate) == "Bob"


def test_pdf_patch_writer_adapter_accepts_h11_text_field_edit() -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    output = BytesIO()

    result = PdfPatchWriter().write(
        document,
        output,
        TargetInfo(format="pdf", extension=".pdf"),
        source_stream=BytesIO(source),
        edits=(_form_edit(document, "Carol"),),
    )

    candidate = output.getvalue()
    assert result.format == "pdf"
    assert candidate.startswith(source)
    assert _value(candidate) == "Carol"
