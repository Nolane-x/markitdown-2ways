from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError, UnsupportedEditError
from markitdown.twoways.formats.pdf.limits import PdfNativeLimits
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


def _edit(document, key: str, value: str, operation_id: str, field: str | None = None):
    node = _field(document, key)
    return EditOperation(
        operation_id=operation_id,
        type="update_pdf_metadata",
        target_node_id=node.node_id,
        payload={"field": field or node.metadata["pdf.info_field"], "value": value},
    )


def test_pdf_noop_edit_is_rejected_and_output_stays_empty() -> None:
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError) as exc:
        patch_pdf(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "/Title", "Alpha", "noop"),),
        )
    assert exc.value.details["reason"] == "pdf.metadata.semantic_noop"
    assert output.getvalue() == b""


def test_pdf_failed_transaction_leaves_output_empty() -> None:
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_pdf(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(document, "/Title", "Updated", "good"),
                _edit(document, "/Author", "Changed", "bad", "Producer"),
            ),
        )
    assert output.getvalue() == b""


def test_pdf_oversized_increment_is_rejected_before_output() -> None:
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    output = BytesIO()

    with pytest.raises(RoundTripVerificationError) as exc:
        patch_pdf(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "/Title", "Updated", "bounded"),),
            limits=PdfNativeLimits(max_increment_bytes=1),
        )

    assert exc.value.details["reason"] == "pdf.writer.increment_too_large"
    assert output.getvalue() == b""
