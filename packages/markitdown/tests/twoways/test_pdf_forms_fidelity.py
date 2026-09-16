from __future__ import annotations

from io import BytesIO

from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.formats.pdf.writer import patch_pdf
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition

from ._pdf_fixtures import make_text_form_pdf


def test_pdf_form_writer_reports_viewer_regenerated_appearance_boundary() -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    node = next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "pdf-form-text-value"
    )
    edit = EditOperation(
        operation_id="form-fidelity",
        type="update_pdf_text_field_value",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_old_value=node.payload.text),
        payload={
            "field_name": node.metadata["pdf.form_field_name"],
            "old_value": node.payload.text,
            "value": "Bob",
        },
    )
    output = BytesIO()

    result = patch_pdf(document, BytesIO(source), output, edits=(edit,))

    evidence = {item.check_code: item for item in result.fidelity.evidence}
    item = evidence["pdf.form.viewer_regenerated_appearance"]
    description = item.description.lower()
    assert "viewer" in description
    assert "needappearances" in description
    assert "visual" in description
    assert "not" in description
