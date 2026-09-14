from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from markitdown.twoways.formats.pdf.reader import read_pdf_ir
from markitdown.twoways.formats.pdf.writer import patch_pdf
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition

from ._pdf_fixtures import make_metadata_pdf


def _field(document, key: str):
    return next(node for node in document.nodes.values() if node.metadata.get("pdf.info_key") == key)


def _edit(document, key: str, value: str, operation_id: str):
    node = _field(document, key)
    return EditOperation(
        operation_id=operation_id,
        type="update_pdf_metadata",
        target_node_id=node.node_id,
        precondition=EditPrecondition(expected_old_value=node.payload.text),
        payload={"field": node.metadata["pdf.info_field"], "value": value},
    )


def test_pdf_zero_edit_is_exact_source_bytes() -> None:
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    output = BytesIO()

    result = patch_pdf(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.bytes_written == len(source)
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_pdf_one_field_update_is_incremental_source_prefix() -> None:
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    output = BytesIO()

    result = patch_pdf(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "/Title", "Updated", "op-title"),),
    )
    candidate = output.getvalue()

    assert candidate.startswith(source)
    assert len(candidate) > len(source)
    metadata = PdfReader(BytesIO(candidate), strict=True).metadata
    assert metadata is not None
    assert metadata.title == "Updated"
    assert metadata.author == "Ada"
    assert metadata.subject == "Spec"
    assert metadata.keywords == "one,two"
    assert result.bytes_written == len(candidate)
    assert result.fidelity.claimed_tier == "high"


def test_pdf_multiple_fields_update_in_one_transaction() -> None:
    source = make_metadata_pdf()
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    output = BytesIO()

    patch_pdf(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(document, "/Title", "Updated", "op-title"),
            _edit(document, "/Author", "Grace", "op-author"),
            _edit(document, "/Keywords", "three,four", "op-keywords"),
        ),
    )

    metadata = PdfReader(BytesIO(output.getvalue()), strict=True).metadata
    assert metadata is not None
    assert metadata.title == "Updated"
    assert metadata.author == "Grace"
    assert metadata.subject == "Spec"
    assert metadata.keywords == "three,four"
