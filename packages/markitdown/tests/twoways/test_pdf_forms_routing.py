from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import PatchPreconditionError, UnsupportedEditError
from markitdown.twoways.formats.pdf.limits import PdfNativeLimits
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.formats.pdf.routing import resolve_pdf_text_field_value_edit
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.provenance import NativeLocator

from ._pdf_fixtures import make_text_form_pdf


def _field(document):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "pdf-form-text-value"
    )


def _metadata_node(document):
    return next(
        node for node in document.nodes.values() if node.semantic_role == "pdf-metadata"
    )


def _edit(document, value: str = "Bob") -> EditOperation:
    node = _field(document)
    return EditOperation(
        operation_id="form-1",
        type="update_pdf_text_field_value",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_old_value=node.payload.text),
        payload={
            "field_name": node.metadata["pdf.form_field_name"],
            "old_value": node.payload.text,
            "value": value,
        },
    )


def _replace_node(document, node):
    nodes = dict(document.nodes)
    nodes[node.node_id] = node
    return replace(document, nodes=nodes)


def test_pdf_form_routing_revalidates_fresh_native_authority() -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")

    routed = resolve_pdf_text_field_value_edit(document, source, _edit(document))

    field = _field(document)
    assert routed.operation_id == "form-1"
    assert routed.target_node_id == field.node_id
    assert routed.field_name == "customer.name"
    assert routed.field_objgen == (6, 0)
    assert routed.page_index == 0
    assert routed.annotation_index == 0
    assert routed.acroform_objgen == (5, 0)
    assert routed.old_value == "Alice"
    assert routed.value == "Bob"
    assert routed.locator_digest == field.metadata["pdf.form_locator_digest"]
    assert routed.immutable_digest == field.metadata["pdf.form_immutable_digest"]


def test_pdf_form_routing_rejects_wrong_target_role() -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    edit = replace(_edit(document), target_node_id=_metadata_node(document).node_id)

    with pytest.raises(UnsupportedEditError):
        resolve_pdf_text_field_value_edit(document, source, edit)


@pytest.mark.parametrize(
    "payload",
    [
        {"field_name": "customer.name", "value": "Bob"},
        {
            "field_name": "customer.name",
            "old_value": "Alice",
            "value": "Bob",
            "extra": True,
        },
    ],
)
def test_pdf_form_routing_rejects_payload_shape(payload: dict[str, object]) -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    edit = replace(_edit(document), payload=payload)

    with pytest.raises(UnsupportedEditError) as exc:
        resolve_pdf_text_field_value_edit(document, source, edit)
    assert exc.value.details["reason"] == "pdf.form.payload_shape"


@pytest.mark.parametrize(
    "key,value,reason",
    [
        ("field_name", 42, "pdf.form.field_name"),
        ("field_name", "", "pdf.form.field_name"),
        ("old_value", 42, "pdf.form.value_type"),
        ("value", 42, "pdf.form.value_type"),
    ],
)
def test_pdf_form_routing_rejects_invalid_payload_values(
    key: str, value: object, reason: str
) -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    edit = _edit(document)
    edit = replace(edit, payload={**edit.payload, key: value})

    with pytest.raises(UnsupportedEditError) as exc:
        resolve_pdf_text_field_value_edit(document, source, edit)
    assert exc.value.details["reason"] == reason


def test_pdf_form_routing_rejects_semantic_noop() -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")

    with pytest.raises(UnsupportedEditError) as exc:
        resolve_pdf_text_field_value_edit(document, source, _edit(document, value="Alice"))
    assert exc.value.details["reason"] == "pdf.form.semantic_noop"


def test_pdf_form_routing_rejects_stale_old_value() -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    edit = _edit(document)
    edit = replace(edit, payload={**edit.payload, "old_value": "Mallory"})

    with pytest.raises(PatchPreconditionError) as exc:
        resolve_pdf_text_field_value_edit(document, source, edit)
    assert exc.value.details["reason"] == "pdf.form.old_value"


def test_pdf_form_routing_rejects_forged_field_name_payload() -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    edit = _edit(document)
    edit = replace(edit, payload={**edit.payload, "field_name": "forged.name"})

    with pytest.raises(PatchPreconditionError) as exc:
        resolve_pdf_text_field_value_edit(document, source, edit)
    assert exc.value.details["reason"] == "pdf.form.field_name"


@pytest.mark.parametrize(
    "metadata_key,forged,reason",
    [
        ("pdf.form_field_name", "forged.name", "pdf.form.field_name"),
        ("pdf.form_field_objgen", (999, 0), "pdf.form.native_binding"),
        ("pdf.page_index", 9, "pdf.form.native_binding"),
        ("pdf.annotation_index", 9, "pdf.form.native_binding"),
        ("pdf.acroform_objgen", (999, 0), "pdf.form.native_binding"),
        ("pdf.form_locator_digest", "0" * 64, "pdf.form.native_binding"),
        ("pdf.form_immutable_digest", "1" * 64, "pdf.form.native_binding"),
    ],
)
def test_pdf_form_routing_rejects_forged_native_binding(
    metadata_key: str, forged: object, reason: str
) -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    edit = _edit(document)
    node = _field(document)
    metadata = dict(node.metadata)
    metadata[metadata_key] = forged
    forged_node = replace(node, metadata=metadata)
    forged_document = _replace_node(document, forged_node)

    with pytest.raises(PatchPreconditionError) as exc:
        resolve_pdf_text_field_value_edit(forged_document, source, edit)
    assert exc.value.details["reason"] == reason


def test_pdf_form_routing_rejects_forged_native_locator() -> None:
    source = make_text_form_pdf()
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    node = _field(document)
    assert node.native_locator is not None
    forged_node = replace(
        node,
        native_locator=NativeLocator(
            backend="pdf",
            part_uri=node.native_locator.part_uri,
            object_id="999:0",
            path="/V",
        ),
    )
    forged_document = _replace_node(document, forged_node)

    with pytest.raises(PatchPreconditionError) as exc:
        resolve_pdf_text_field_value_edit(
            forged_document, source, _edit(forged_document)
        )
    assert exc.value.details["reason"] == "pdf.form.native_locator"


def test_pdf_form_routing_rejects_per_value_limit() -> None:
    source = make_text_form_pdf(value="Al")
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")
    limits = PdfNativeLimits(max_form_value_chars=3)

    with pytest.raises(UnsupportedEditError) as exc:
        resolve_pdf_text_field_value_edit(
            document, source, _edit(document, value="Robert"), limits=limits
        )
    assert exc.value.details["reason"] == "pdf.form.value_too_large"


def test_pdf_form_routing_rejects_max_len() -> None:
    source = make_text_form_pdf(max_len=5)
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")

    with pytest.raises(UnsupportedEditError) as exc:
        resolve_pdf_text_field_value_edit(
            document, source, _edit(document, value="Robert")
        )
    assert exc.value.details["reason"] == "pdf.form.max_length"


def test_pdf_form_routing_rejects_read_only_fresh_authority() -> None:
    source = make_text_form_pdf(with_ap=True)
    document = read_pdf_ir(BytesIO(source), filename="form.pdf")

    with pytest.raises(UnsupportedEditError) as exc:
        resolve_pdf_text_field_value_edit(document, source, _edit(document))
    assert exc.value.details["reason"] == "pdf.form.appearance_present"
