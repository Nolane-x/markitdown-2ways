from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    CapabilityState,
    DocumentIntelligenceAnalysisSnapshot,
    build_capability_report,
    canonical_json_bytes,
    canonical_json_digest,
    capabilities_for_node,
    decode_document,
    read_document_intelligence_analysis_ir,
)
from markitdown.twoways.ir.nodes import TextPayload


SOURCE = b"%PDF-1.7\nH22 fixture\n"
ANALYSIS_CONTENT = "# Demo\n<!--hidden service note-->\nVisible body\n"


def _info(**updates: object) -> StreamInfo:
    values = {
        "mimetype": "application/pdf",
        "extension": ".pdf",
        "filename": "demo.pdf",
    }
    values.update(updates)
    return StreamInfo(**values)


def _analysis(**updates: object) -> DocumentIntelligenceAnalysisSnapshot:
    values = {
        "content": ANALYSIS_CONTENT,
        "provider": "offline-fixture",
        "model_id": "prebuilt-layout",
        "content_format": "markdown",
        "api_version": "2024-11-30",
        "analysis_id": "analysis-001",
    }
    values.update(updates)
    return DocumentIntelligenceAnalysisSnapshot(**values)


def _root(document):
    assert len(document.root_node_ids) == 1
    return document.nodes[document.root_node_ids[0]]


def test_reader_binds_source_analysis_and_derived_markdown() -> None:
    analysis = _analysis()
    document = read_document_intelligence_analysis_ir(
        BytesIO(SOURCE),
        stream_info=_info(),
        analysis=analysis,
    )

    assert document.source is not None
    assert document.source.format == "document-intelligence-analysis-source"
    assert document.source.filename == "demo.pdf"
    assert document.source.mimetype == "application/pdf"
    assert document.source.sha256 == sha256(SOURCE).hexdigest()
    assert document.source.size_bytes == len(SOURCE)
    assert document.source.preserved_source_ref is None

    node = _root(document)
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == "# Demo\n\nVisible body\n"
    assert node.semantic_role == "derived_document"
    assert node.native_locator is None
    assert document.canvases[0].kind == "derived-analysis"
    assert document.canvases[0].native_locator is None

    evidence = document.metadata.custom["twoways.document_intelligence_analysis.v1"]
    analysis_bytes = ANALYSIS_CONTENT.encode("utf-8")
    markdown_bytes = node.payload.text.encode("utf-8")

    assert evidence["source_sha256"] == sha256(SOURCE).hexdigest()
    assert evidence["source_size_bytes"] == len(SOURCE)
    assert evidence["analysis_provider"] == "offline-fixture"
    assert evidence["model_id"] == "prebuilt-layout"
    assert evidence["content_format"] == "markdown"
    assert evidence["api_version"] == "2024-11-30"
    assert evidence["analysis_id"] == "analysis-001"
    assert evidence["analysis_content_sha256"] == sha256(analysis_bytes).hexdigest()
    assert evidence["analysis_content_utf8_size_bytes"] == len(analysis_bytes)
    assert evidence["markdown_sha256"] == sha256(markdown_bytes).hexdigest()
    assert evidence["markdown_utf8_size_bytes"] == len(markdown_bytes)
    assert evidence["network_performed_by_twoways"] is False
    assert evidence["azure_sdk_used_by_twoways"] is False
    assert evidence["credentials_used_by_twoways"] is False


def test_root_is_derived_and_has_no_native_write_authority() -> None:
    document = read_document_intelligence_analysis_ir(
        BytesIO(SOURCE),
        stream_info=_info(),
        analysis=_analysis(),
    )
    node = _root(document)

    decision = capabilities_for_node(node).for_operation("replace_text")
    assert decision.state is CapabilityState.DERIVED
    assert decision.reason_code == "analysis.output.not_native_writable"
    assert decision.constraints == {
        "identity_markdown": False,
        "remote_writeback": False,
        "native_owner": False,
        "materialization": "explicit-local-only",
    }

    report = build_capability_report(document)
    assert report.total_nodes == 1
    assert report.derived_nodes == 1
    assert report.writable_nodes == 0
    assert dict(report.writable_by_operation) == {}

    assert len(document.diagnostics) == 1
    assert document.diagnostics[0].code == "analysis.output.not_native_writable"


def test_repeated_reads_and_canonical_round_trip_are_deterministic() -> None:
    kwargs = {"stream_info": _info(), "analysis": _analysis()}
    first = read_document_intelligence_analysis_ir(BytesIO(SOURCE), **kwargs)
    second = read_document_intelligence_analysis_ir(BytesIO(SOURCE), **kwargs)

    assert canonical_json_digest(first) == canonical_json_digest(second)
    encoded = canonical_json_bytes(first)
    decoded = decode_document(encoded)
    assert canonical_json_bytes(decoded) == encoded
    assert decoded.schema_version == "0.1.0"


@pytest.mark.parametrize(
    ("extension", "mimetype"),
    (
        (".docx", None),
        (".pptx", None),
        (".xlsx", None),
        (".pdf", None),
        (".jpg", None),
        (".jpeg", None),
        (".png", None),
        (".bmp", None),
        (".tiff", None),
        (None, "application/pdf"),
        (None, "image/jpeg"),
        (None, "image/png"),
        (None, "image/bmp"),
        (None, "image/tiff"),
    ),
)
def test_default_one_way_file_surface_is_accepted(
    extension: str | None,
    mimetype: str | None,
) -> None:
    document = read_document_intelligence_analysis_ir(
        BytesIO(SOURCE),
        stream_info=_info(extension=extension, mimetype=mimetype),
        analysis=_analysis(),
    )
    assert document.root_node_ids


@pytest.mark.parametrize(
    ("extension", "mimetype"),
    (
        (".html", "text/html"),
        (".txt", "text/plain"),
        (".csv", "text/csv"),
        (None, None),
    ),
)
def test_outside_default_file_surface_fails_closed(
    extension: str | None,
    mimetype: str | None,
) -> None:
    with pytest.raises(ValueError, match="DocumentIntelligenceConverter"):
        read_document_intelligence_analysis_ir(
            BytesIO(SOURCE),
            stream_info=_info(extension=extension, mimetype=mimetype),
            analysis=_analysis(),
        )
