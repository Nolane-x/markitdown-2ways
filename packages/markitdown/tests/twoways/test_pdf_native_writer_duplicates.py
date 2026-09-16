from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import UnsupportedEditError
from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.formats.pdf.writer import patch_pdf
from markitdown.twoways.ir.edits import EditOperation

from ._pdf_fixtures import make_metadata_pdf


def _field(document, key: str):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("pdf.info_key") == key
    )


def _edit(document, key: str, value: str, operation_id: str):
    node = _field(document, key)
    return EditOperation(
        operation_id=operation_id,
        type="update_pdf_metadata",
        target_node_id=node.node_id,
        payload={"field": node.metadata["pdf.info_field"], "value": value},
    )


def test_pdf_duplicate_operation_id_is_rejected_before_output() -> None:
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError) as exc:
        patch_pdf(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(document, "/Title", "Updated", "same"),
                _edit(document, "/Author", "Grace", "same"),
            ),
        )
    assert exc.value.details["reason"] == "pdf.metadata.duplicate_operation_id"
    assert output.getvalue() == b""


def test_pdf_duplicate_logical_target_is_rejected_before_output() -> None:
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError) as exc:
        patch_pdf(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(document, "/Title", "One", "one"),
                _edit(document, "/Title", "Two", "two"),
            ),
        )
    assert exc.value.details["reason"] == "pdf.metadata.duplicate_target"
    assert output.getvalue() == b""
