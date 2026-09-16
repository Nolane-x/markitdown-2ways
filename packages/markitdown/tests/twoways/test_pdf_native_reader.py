from __future__ import annotations

from io import BytesIO

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.pdf.reader import PdfIRReader, read_pdf_ir
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document

from ._pdf_fixtures import make_metadata_pdf


def _field(document, key: str):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("pdf.info_key") == key
    )


def test_pdf_reader_builds_deterministic_metadata_ir() -> None:
    source = make_metadata_pdf()

    first = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    second = read_pdf_ir(BytesIO(source), filename="sample.pdf")

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    assert first.source is not None
    assert first.source.format == "pdf"
    assert first.source.filename == "sample.pdf"
    assert first.source.size_bytes == len(source)
    assert first.canvases[0].kind == "document"

    root = first.nodes[first.root_node_ids[0]]
    assert root.semantic_role == "pdf-document"
    assert len(root.children) == 4

    title = _field(first, "/Title")
    assert title.semantic_role == "pdf-metadata"
    assert title.payload.text == "Alpha"
    assert title.parent_id == root.node_id
    assert title.metadata["pdf.info_objgen"] == (4, 0)
    assert title.metadata["pdf.identity_markdown"] is False
    assert title.native_locator is not None
    assert title.native_locator.backend == "pdf"
    assert title.native_locator.object_id == "4:0"
    assert title.native_locator.path == "/Title"

    decision = capabilities_for_node(title).for_operation("update_pdf_metadata")
    assert decision.state is CapabilityState.WRITABLE
    assert decision.reason_code is None
    assert decision.constraints["identity_markdown"] is False
    assert decision.constraints["source_preservation"] == "incremental-source-prefix"


def test_pdf_reader_missing_info_is_structural_read_only() -> None:
    source = make_metadata_pdf(include_info=False)
    document = read_pdf_ir(BytesIO(source), filename="sample.pdf")
    root = document.nodes[document.root_node_ids[0]]

    decision = capabilities_for_node(root).for_operation("update_pdf_metadata")
    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "pdf.metadata.info_missing"
    assert not any(
        node.semantic_role == "pdf-metadata" for node in document.nodes.values()
    )


def test_pdf_ir_reader_accepts_pdf_extension_and_mimetype() -> None:
    reader = PdfIRReader()

    class Info:
        extension = ".pdf"
        mimetype = "application/pdf"
        filename = "sample.pdf"

    source = BytesIO(make_metadata_pdf())
    assert reader.accepts(source, Info()) is True
    source.seek(0)
    document = reader.read(source, Info())
    assert document.source is not None
    assert document.source.format == "pdf"
