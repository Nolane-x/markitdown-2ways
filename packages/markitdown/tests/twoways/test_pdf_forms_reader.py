from __future__ import annotations

from io import BytesIO

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document

from ._pdf_fixtures import make_text_form_pdf


def _form_node(document):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "pdf-form-text-value"
    )


def _root_node(document):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "pdf-document"
    )


def test_pdf_reader_materializes_deterministic_writable_text_field() -> None:
    source = make_text_form_pdf()

    first = read_pdf_ir(BytesIO(source), filename="form.pdf")
    second = read_pdf_ir(BytesIO(source), filename="form.pdf")

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    field = _form_node(first)
    assert field.payload.text == "Alice"
    assert field.metadata["pdf.form_field_name"] == "customer.name"
    assert field.metadata["pdf.form_field_objgen"] == (6, 0)
    assert field.metadata["pdf.page_index"] == 0
    assert field.metadata["pdf.annotation_index"] == 0
    assert field.metadata["pdf.acroform_objgen"] == (5, 0)
    assert field.metadata["pdf.form_field_flags"] == 0
    assert field.metadata["pdf.form_max_len"] is None
    assert len(field.metadata["pdf.form_locator_digest"]) == 64
    assert len(field.metadata["pdf.form_immutable_digest"]) == 64
    assert field.metadata["pdf.identity_markdown"] is False
    assert field.native_locator is not None
    assert field.native_locator.backend == "pdf"
    assert field.native_locator.path == "/V"

    decision = capabilities_for_node(field).for_operation(
        "update_pdf_text_field_value"
    )
    assert decision.state is CapabilityState.WRITABLE
    assert decision.reason_code is None
    assert decision.constraints["identity_markdown"] is False
    assert decision.constraints["source_preservation"] == "incremental-source-prefix"
    assert decision.constraints["existing_value_only"] is True
    assert decision.constraints["viewer_regenerated_appearance"] is True

    root = _root_node(first)
    assert root.metadata["pdf.acroform_objgen"] == (5, 0)
    assert root.metadata["pdf.need_appearances"] is True
    assert root.metadata["pdf.form_h11_count"] == 1
    assert root.metadata["pdf.form_h11_supported"] is True


def test_pdf_reader_materializes_policy_read_only_text_field() -> None:
    document = read_pdf_ir(
        BytesIO(make_text_form_pdf(with_ap=True)),
        filename="form.pdf",
    )
    field = _form_node(document)

    decision = capabilities_for_node(field).for_operation(
        "update_pdf_text_field_value"
    )
    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "pdf.form.appearance_present"

    root = _root_node(document)
    assert root.metadata["pdf.form_h11_count"] == 1
    assert root.metadata["pdf.form_h11_supported"] is False


def test_pdf_reader_appends_form_nodes_after_existing_pdf_nodes() -> None:
    document = read_pdf_ir(BytesIO(make_text_form_pdf()), filename="form.pdf")
    root = _root_node(document)
    children = [document.nodes[node_id] for node_id in root.children]

    metadata_orders = [
        node.order for node in children if node.semantic_role == "pdf-metadata"
    ]
    form = _form_node(document)
    assert metadata_orders
    assert form.order > max(metadata_orders)
