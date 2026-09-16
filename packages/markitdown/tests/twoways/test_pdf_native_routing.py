from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.formats.pdf.routing import resolve_pdf_metadata_edit
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.provenance import NativeLocator

from ._pdf_fixtures import make_metadata_pdf


def _field(document, key: str):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("pdf.info_key") == key
    )


def _edit(document, key: str, value: str, *, operation_id: str = "op-1"):
    node = _field(document, key)
    return EditOperation(
        operation_id=operation_id,
        type="update_pdf_metadata",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_old_value=node.payload.text),
        payload={"field": node.metadata["pdf.info_field"], "value": value},
    )


def _replace_node(document, node):
    nodes = dict(document.nodes)
    nodes[node.node_id] = node
    return replace(document, nodes=nodes)


def test_pdf_routing_revalidates_fresh_info_authority() -> None:
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    edit = _edit(document, "/Title", "Updated")

    routed = resolve_pdf_metadata_edit(document, source, edit)

    assert routed.operation_id == "op-1"
    assert routed.target_node_id == edit.target_node_id
    assert routed.field == "Title"
    assert routed.key == "/Title"
    assert routed.old_value == "Alpha"
    assert routed.value == "Updated"
    assert routed.info_objgen == (4, 0)


def test_pdf_routing_rejects_stale_source() -> None:
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    stale = make_metadata_pdf(title="Different")

    with pytest.raises(SourcePackageMismatchError):
        resolve_pdf_metadata_edit(document, stale, _edit(document, "/Title", "Updated"))


def test_pdf_routing_rejects_forged_locator_objgen() -> None:
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    title = _field(document, "/Title")
    assert title.native_locator is not None
    forged = replace(
        title,
        native_locator=NativeLocator(
            backend="pdf",
            part_uri="/Info",
            object_id="99:0",
            path="/Title",
        ),
    )
    forged_document = _replace_node(document, forged)

    with pytest.raises(PatchPreconditionError) as exc:
        resolve_pdf_metadata_edit(
            forged_document,
            source,
            _edit(forged_document, "/Title", "Updated"),
        )
    assert exc.value.details["reason"] == "pdf.native_locator"


def test_pdf_routing_rejects_forged_key() -> None:
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    title = _field(document, "/Title")
    forged_metadata = dict(title.metadata)
    forged_metadata["pdf.info_key"] = "/Author"
    forged = replace(title, metadata=forged_metadata)
    forged_document = _replace_node(document, forged)

    with pytest.raises(PatchPreconditionError) as exc:
        resolve_pdf_metadata_edit(
            forged_document,
            source,
            _edit(forged_document, "/Author", "Updated"),
        )
    assert exc.value.details["reason"] in {"pdf.field_binding", "pdf.target_ownership"}


def test_pdf_routing_rejects_stale_expected_old_value() -> None:
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    title = _field(document, "/Title")
    edit = EditOperation(
        operation_id="op-stale",
        type="update_pdf_metadata",
        target_node_id=title.node_id,
        precondition=EditPrecondition(expected_old_value="Stale"),
        payload={"field": "Title", "value": "Updated"},
    )

    with pytest.raises(PatchPreconditionError):
        resolve_pdf_metadata_edit(document, source, edit)


def test_pdf_routing_rejects_unsupported_field_name() -> None:
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    title = _field(document, "/Title")
    edit = EditOperation(
        operation_id="op-unsupported",
        type="update_pdf_metadata",
        target_node_id=title.node_id,
        payload={"field": "Producer", "value": "Updated"},
    )

    with pytest.raises(UnsupportedEditError) as exc:
        resolve_pdf_metadata_edit(document, source, edit)
    assert exc.value.details["reason"] == "pdf.metadata.unsupported_field"
