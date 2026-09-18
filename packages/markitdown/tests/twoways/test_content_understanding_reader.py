from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    CapabilityState,
    ContentUnderstandingAnalysisSnapshot,
    build_capability_report,
    canonical_json_bytes,
    canonical_json_digest,
    capabilities_for_node,
    decode_document,
    read_content_understanding_analysis_ir,
)
from markitdown.twoways.ir.nodes import TextPayload


SOURCE = b"content-understanding source bytes"
OUTPUT = "---\ncontentType: document\n---\n# Demo\n"
PDF_INFO = StreamInfo(
    extension=".pdf",
    mimetype="application/pdf",
    filename="demo.pdf",
)


def _snapshot(**updates: object) -> ContentUnderstandingAnalysisSnapshot:
    values = {
        "content": OUTPUT,
        "provider": "offline-fixture",
        "analyzer_id": "prebuilt-documentSearch",
        "content_type": "application/pdf",
        "api_version": "2025-05-01-preview",
        "analysis_id": "analysis-001",
    }
    values.update(updates)
    return ContentUnderstandingAnalysisSnapshot(**values)


def _root(document):
    assert len(document.root_node_ids) == 1
    return document.nodes[document.root_node_ids[0]]


def test_reader_binds_source_routing_and_exact_materialized_output() -> None:
    document = read_content_understanding_analysis_ir(
        BytesIO(SOURCE),
        stream_info=PDF_INFO,
        analysis=_snapshot(),
    )

    assert document.source is not None
    assert document.source.format == "content-understanding-analysis-source"
    assert document.source.filename == "demo.pdf"
    assert document.source.mimetype == "application/pdf"
    assert document.source.sha256 == sha256(SOURCE).hexdigest()
    assert document.source.size_bytes == len(SOURCE)
    assert document.source.preserved_source_ref is None

    node = _root(document)
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == OUTPUT
    assert node.semantic_role == "derived_document"
    assert node.native_locator is None
    assert document.canvases[0].kind == "derived-analysis"
    assert document.canvases[0].native_locator is None

    evidence = document.metadata.custom["twoways.content_understanding_analysis.v1"]
    output_bytes = OUTPUT.encode("utf-8")
    assert evidence["source_sha256"] == sha256(SOURCE).hexdigest()
    assert evidence["source_size_bytes"] == len(SOURCE)
    assert evidence["file_type"] == "pdf"
    assert evidence["modality"] == "document"
    assert evidence["analyzer_id"] == "prebuilt-documentSearch"
    assert evidence["content_type"] == "application/pdf"
    assert evidence["analysis_provider"] == "offline-fixture"
    assert evidence["analysis_content_sha256"] == sha256(output_bytes).hexdigest()
    assert evidence["analysis_content_utf8_size_bytes"] == len(output_bytes)
    assert evidence["network_performed_by_twoways"] is False
    assert evidence["azure_sdk_used_by_twoways"] is False
    assert evidence["credentials_used_by_twoways"] is False
    assert evidence["to_llm_input_called_by_twoways"] is False


def test_root_is_derived_and_has_no_native_write_authority() -> None:
    document = read_content_understanding_analysis_ir(
        BytesIO(SOURCE),
        stream_info=PDF_INFO,
        analysis=_snapshot(),
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


def test_repeated_reads_and_canonical_round_trip_are_deterministic() -> None:
    first = read_content_understanding_analysis_ir(
        BytesIO(SOURCE),
        stream_info=PDF_INFO,
        analysis=_snapshot(),
    )
    second = read_content_understanding_analysis_ir(
        BytesIO(SOURCE),
        stream_info=PDF_INFO,
        analysis=_snapshot(),
    )

    assert canonical_json_digest(first) == canonical_json_digest(second)
    encoded = canonical_json_bytes(first)
    decoded = decode_document(encoded)
    assert canonical_json_bytes(decoded) == encoded
    assert decoded.schema_version == "0.1.0"


def test_source_and_analysis_are_independent_identity_authorities() -> None:
    baseline = read_content_understanding_analysis_ir(
        BytesIO(SOURCE),
        stream_info=PDF_INFO,
        analysis=_snapshot(),
    )
    changed_source = read_content_understanding_analysis_ir(
        BytesIO(SOURCE + b"-changed"),
        stream_info=PDF_INFO,
        analysis=_snapshot(),
    )
    changed_analysis = read_content_understanding_analysis_ir(
        BytesIO(SOURCE),
        stream_info=PDF_INFO,
        analysis=_snapshot(content=OUTPUT + "changed"),
    )

    assert baseline.source is not None
    assert changed_source.source is not None
    assert changed_analysis.source is not None
    assert baseline.document_id != changed_source.document_id
    assert baseline.document_id != changed_analysis.document_id
    assert baseline.source.sha256 != changed_source.source.sha256
    assert baseline.source.sha256 == changed_analysis.source.sha256


@pytest.mark.parametrize(
    ("extension", "file_type", "modality", "analyzer_id", "content_type"),
    (
        (".pdf", "pdf", "document", "prebuilt-documentSearch", "application/pdf"),
        (
            ".docx",
            "docx",
            "document",
            "prebuilt-documentSearch",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            ".pptx",
            "pptx",
            "document",
            "prebuilt-documentSearch",
            "application/vnd.openxmlformats-officedocument.presentationml",
        ),
        (
            ".xlsx",
            "xlsx",
            "document",
            "prebuilt-documentSearch",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (".html", "html", "document", "prebuilt-documentSearch", "text/html"),
        (".txt", "txt", "document", "prebuilt-documentSearch", "text/plain"),
        (".md", "md", "document", "prebuilt-documentSearch", "text/markdown"),
        (".rtf", "rtf", "document", "prebuilt-documentSearch", "text/rtf"),
        (".xml", "xml", "document", "prebuilt-documentSearch", "text/xml"),
        (".eml", "eml", "document", "prebuilt-documentSearch", "message/rfc822"),
        (
            ".msg",
            "msg",
            "document",
            "prebuilt-documentSearch",
            "application/vnd.ms-outlook",
        ),
        (".jpg", "jpeg", "image", "prebuilt-documentSearch", "image/jpeg"),
        (".jpeg", "jpeg", "image", "prebuilt-documentSearch", "image/jpeg"),
        (".jpe", "jpeg", "image", "prebuilt-documentSearch", "image/jpeg"),
        (".png", "png", "image", "prebuilt-documentSearch", "image/png"),
        (".bmp", "bmp", "image", "prebuilt-documentSearch", "image/bmp"),
        (".tiff", "tiff", "image", "prebuilt-documentSearch", "image/tiff"),
        (".heif", "heif", "image", "prebuilt-documentSearch", "image/heif"),
        (".heic", "heif", "image", "prebuilt-documentSearch", "image/heif"),
        (".mp4", "mp4", "video", "prebuilt-videoSearch", "video/mp4"),
        (".m4v", "m4v", "video", "prebuilt-videoSearch", "video/mp4"),
        (".mov", "mov", "video", "prebuilt-videoSearch", "video/quicktime"),
        (".avi", "avi", "video", "prebuilt-videoSearch", "video/x-msvideo"),
        (".mkv", "mkv", "video", "prebuilt-videoSearch", "video/x-matroska"),
        (".webm", "webm", "video", "prebuilt-videoSearch", "video/webm"),
        (".flv", "flv", "video", "prebuilt-videoSearch", "video/x-flv"),
        (".wmv", "wmv", "video", "prebuilt-videoSearch", "video/x-ms-wmv"),
        (".wav", "wav", "audio", "prebuilt-audioSearch", "audio/wav"),
        (".mp3", "mp3", "audio", "prebuilt-audioSearch", "audio/mpeg"),
        (".m4a", "m4a", "audio", "prebuilt-audioSearch", "audio/mp4"),
        (".flac", "flac", "audio", "prebuilt-audioSearch", "audio/flac"),
        (".ogg", "ogg", "audio", "prebuilt-audioSearch", "audio/ogg"),
        (".aac", "aac", "audio", "prebuilt-audioSearch", "audio/aac"),
        (".wma", "wma", "audio", "prebuilt-audioSearch", "audio/x-ms-wma"),
    ),
)
def test_complete_default_extension_surface_routes_deterministically(
    extension: str,
    file_type: str,
    modality: str,
    analyzer_id: str,
    content_type: str,
) -> None:
    document = read_content_understanding_analysis_ir(
        BytesIO(SOURCE),
        stream_info=StreamInfo(extension=extension),
        analysis=_snapshot(
            analyzer_id=analyzer_id,
            content_type=content_type,
            api_version=None,
            analysis_id=None,
        ),
    )
    evidence = document.metadata.custom["twoways.content_understanding_analysis.v1"]
    assert evidence["file_type"] == file_type
    assert evidence["modality"] == modality
    assert evidence["analyzer_id"] == analyzer_id
    assert evidence["content_type"] == content_type
