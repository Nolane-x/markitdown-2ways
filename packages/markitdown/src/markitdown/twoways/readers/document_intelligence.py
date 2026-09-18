from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import BinaryIO

from ..._stream_info import StreamInfo
from ..capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from ..ir.document import (
    Canvas,
    Diagnostic,
    DocumentIdFactory,
    DocumentIR,
    DocumentMetadata,
    SourceDescriptor,
)
from ..ir.nodes import Node, TextPayload
from ..ir.provenance import Provenance
from ..ir.serialization import validate_document


_DOCUMENT_INTELLIGENCE_EVIDENCE_KEY = "twoways.document_intelligence_analysis.v1"
_DOCUMENT_INTELLIGENCE_CONVERTER_BLOB_SHA = "f8a5c8e8c82638fc5186105679ff1af0175992c8"

_DEFAULT_EXTENSIONS = frozenset(
    {
        ".docx",
        ".pptx",
        ".xlsx",
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".tiff",
    }
)
_DEFAULT_MIME_TYPE_PREFIXES = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/pdf",
    "application/x-pdf",
    "image/jpeg",
    "image/png",
    "image/bmp",
    "image/tiff",
)


@dataclass(frozen=True)
class DocumentIntelligenceDerivedLimits:
    max_source_bytes: int = 64 * 1024 * 1024
    max_analysis_utf8_bytes: int = 32 * 1024 * 1024
    max_markdown_utf8_bytes: int = 32 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in (
            "max_source_bytes",
            "max_analysis_utf8_bytes",
            "max_markdown_utf8_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class DocumentIntelligenceAnalysisSnapshot:
    content: str
    provider: str = "caller-materialized"
    model_id: str = "prebuilt-layout"
    content_format: str = "markdown"
    api_version: str | None = None
    analysis_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise TypeError("content must be a string")

        for name in ("provider", "model_id", "content_format"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string")
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")

        for name in ("api_version", "analysis_id"):
            value = getattr(self, name)
            if value is None:
                continue
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string when provided")
            if not value.strip():
                raise ValueError(f"{name} must be non-empty when provided")

        if self.model_id != "prebuilt-layout":
            raise ValueError("model_id must be prebuilt-layout for H22 parity")
        if self.content_format != "markdown":
            raise ValueError("content_format must be markdown for H22 parity")


def _is_owned_by_default_converter(stream_info: StreamInfo) -> bool:
    extension = (stream_info.extension or "").lower()
    mimetype = (stream_info.mimetype or "").lower()

    if extension in _DEFAULT_EXTENSIONS:
        return True
    return any(mimetype.startswith(prefix) for prefix in _DEFAULT_MIME_TYPE_PREFIXES)


def _capture_source(source_stream: BinaryIO, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= max_bytes:
        remaining = max_bytes + 1 - total
        if remaining <= 0:
            break
        chunk = source_stream.read(min(64 * 1024, remaining))
        if isinstance(chunk, str):
            raise TypeError("Document Intelligence source stream must return bytes")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError(
                "Document Intelligence source stream returned a non-bytes value"
            )
        data = bytes(chunk)
        if not data:
            break
        chunks.append(data)
        total += len(data)
        if total > max_bytes:
            raise ValueError("Document Intelligence source exceeds max_source_bytes")
    return b"".join(chunks)


def _project_markdown(content: str) -> str:
    return re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)


def _derived_capability() -> tuple[dict[str, object], ...]:
    return encode_capabilities(
        (
            CapabilityDecision(
                operation="replace_text",
                state=CapabilityState.DERIVED,
                reason_code="analysis.output.not_native_writable",
                constraints={
                    "identity_markdown": False,
                    "remote_writeback": False,
                    "native_owner": False,
                    "materialization": "explicit-local-only",
                },
            ),
        )
    )


def read_document_intelligence_analysis_ir(
    source_stream: BinaryIO,
    *,
    stream_info: StreamInfo,
    analysis: DocumentIntelligenceAnalysisSnapshot,
    limits: DocumentIntelligenceDerivedLimits | None = None,
) -> DocumentIR:
    if not isinstance(analysis, DocumentIntelligenceAnalysisSnapshot):
        raise TypeError("analysis must be a DocumentIntelligenceAnalysisSnapshot")

    if not _is_owned_by_default_converter(stream_info):
        raise ValueError(
            "source is not owned by the default existing "
            "DocumentIntelligenceConverter file surface"
        )

    active_limits = limits or DocumentIntelligenceDerivedLimits()
    source_bytes = _capture_source(
        source_stream,
        max_bytes=active_limits.max_source_bytes,
    )

    analysis_bytes = analysis.content.encode("utf-8")
    if len(analysis_bytes) > active_limits.max_analysis_utf8_bytes:
        raise ValueError("analysis content exceeds max_analysis_utf8_bytes")

    markdown = _project_markdown(analysis.content)
    markdown_bytes = markdown.encode("utf-8")
    if len(markdown_bytes) > active_limits.max_markdown_utf8_bytes:
        raise ValueError("derived Markdown exceeds max_markdown_utf8_bytes")

    source_digest = sha256(source_bytes).hexdigest()
    analysis_digest = sha256(analysis_bytes).hexdigest()
    markdown_digest = sha256(markdown_bytes).hexdigest()
    uri = stream_info.url

    identity_seed = "\0".join(
        (
            "document-intelligence-derived-analysis",
            source_digest,
            stream_info.filename or "",
            stream_info.mimetype or "",
            stream_info.extension or "",
            uri or "",
            analysis.provider,
            analysis.model_id,
            analysis.content_format,
            analysis.api_version or "",
            analysis.analysis_id or "",
            analysis_digest,
            markdown_digest,
            "DocumentIntelligenceConverter",
        )
    )
    ids = DocumentIdFactory(seed=identity_seed)
    document_id = ids.new("document")
    canvas_id = ids.new("canvas")
    node_id = ids.new("root")

    evidence: dict[str, object] = {
        "kind": "document-intelligence",
        "source_sha256": source_digest,
        "source_size_bytes": len(source_bytes),
        "analysis_provider": analysis.provider,
        "model_id": analysis.model_id,
        "content_format": analysis.content_format,
        "analysis_content_sha256": analysis_digest,
        "analysis_content_utf8_size_bytes": len(analysis_bytes),
        "markdown_sha256": markdown_digest,
        "markdown_utf8_size_bytes": len(markdown_bytes),
        "converter": "DocumentIntelligenceConverter",
        "converter_blob_sha": _DOCUMENT_INTELLIGENCE_CONVERTER_BLOB_SHA,
        "network_performed_by_twoways": False,
        "azure_sdk_used_by_twoways": False,
        "credentials_used_by_twoways": False,
    }
    if analysis.api_version is not None:
        evidence["api_version"] = analysis.api_version
    if analysis.analysis_id is not None:
        evidence["analysis_id"] = analysis.analysis_id
    if stream_info.filename is not None:
        evidence["filename"] = stream_info.filename
    if stream_info.mimetype is not None:
        evidence["mimetype"] = stream_info.mimetype
    if stream_info.extension is not None:
        evidence["extension"] = stream_info.extension
    if uri is not None:
        evidence["uri"] = uri

    node = Node(
        node_id=node_id,
        kind="text",
        semantic_role="derived_document",
        order=0,
        canvas_id=canvas_id,
        provenance=(
            Provenance(
                source_format="document-intelligence-analysis",
                canvas_index=0,
                extraction_method=(
                    "DocumentIntelligenceConverter-materialized-analysis"
                ),
                metadata={
                    "source_sha256": source_digest,
                    "analysis_content_sha256": analysis_digest,
                    "markdown_sha256": markdown_digest,
                    "model_id": analysis.model_id,
                    "provider": analysis.provider,
                    "remote_writeback": False,
                },
            ),
        ),
        native_locator=None,
        payload=TextPayload(text=markdown),
        metadata={
            CAPABILITY_METADATA_KEY: _derived_capability(),
            "twoways.document_intelligence_analysis.markdown_sha256": (markdown_digest),
        },
    )

    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(
            format="document-intelligence-analysis-source",
            filename=stream_info.filename,
            mimetype=stream_info.mimetype,
            uri=uri,
            sha256=source_digest,
            size_bytes=len(source_bytes),
        ),
        metadata=DocumentMetadata(
            custom={_DOCUMENT_INTELLIGENCE_EVIDENCE_KEY: evidence},
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="derived-analysis",
                name=stream_info.filename or "Document Intelligence analysis",
                root_node_ids=(node_id,),
                native_locator=None,
            ),
        ),
        nodes={node_id: node},
        root_node_ids=(node_id,),
        diagnostics=(
            Diagnostic(
                code="analysis.output.not_native_writable",
                severity="info",
                message=(
                    "Visible Markdown is derived from caller-materialized "
                    "Document Intelligence analysis and has no H22 native or "
                    "remote writeback authority."
                ),
                node_id=node_id,
                canvas_id=canvas_id,
                details={
                    "model_id": analysis.model_id,
                    "provider": analysis.provider,
                    "remote_writeback": False,
                },
            ),
        ),
    )
    validate_document(document)
    return document


__all__ = [
    "DocumentIntelligenceAnalysisSnapshot",
    "DocumentIntelligenceDerivedLimits",
    "read_document_intelligence_analysis_ir",
]
