from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
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


_CONTENT_UNDERSTANDING_EVIDENCE_KEY = "twoways.content_understanding_analysis.v1"
_CONTENT_UNDERSTANDING_CONVERTER_BLOB_SHA = "230e3d86bf533241b68dfc3d023e48b3effdc788"

_EXTENSION_MAP = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".html": "html",
    ".txt": "txt",
    ".md": "md",
    ".rtf": "rtf",
    ".xml": "xml",
    ".eml": "eml",
    ".msg": "msg",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".jpe": "jpeg",
    ".png": "png",
    ".bmp": "bmp",
    ".tiff": "tiff",
    ".heif": "heif",
    ".heic": "heif",
    ".mp4": "mp4",
    ".m4v": "m4v",
    ".mov": "mov",
    ".avi": "avi",
    ".mkv": "mkv",
    ".webm": "webm",
    ".flv": "flv",
    ".wmv": "wmv",
    ".wav": "wav",
    ".mp3": "mp3",
    ".m4a": "m4a",
    ".flac": "flac",
    ".ogg": "ogg",
    ".aac": "aac",
    ".wma": "wma",
}

_MIME_PREFIXES: dict[str, tuple[str, ...]] = {
    "pdf": ("application/pdf", "application/x-pdf"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "pptx": ("application/vnd.openxmlformats-officedocument.presentationml",),
    "xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    "html": ("text/html", "application/xhtml+xml"),
    "txt": ("text/plain",),
    "md": ("text/markdown",),
    "rtf": ("text/rtf", "application/rtf"),
    "xml": ("text/xml", "application/xml"),
    "eml": ("message/rfc822",),
    "msg": ("application/vnd.ms-outlook",),
    "jpeg": ("image/jpeg",),
    "png": ("image/png",),
    "bmp": ("image/bmp",),
    "tiff": ("image/tiff",),
    "heif": ("image/heif", "image/heic"),
    "mp4": ("video/mp4",),
    "m4v": ("video/x-m4v",),
    "mov": ("video/quicktime",),
    "avi": ("video/x-msvideo",),
    "mkv": ("video/x-matroska",),
    "webm": ("video/webm",),
    "flv": ("video/x-flv",),
    "wmv": ("video/x-ms-wmv",),
    "wav": ("audio/wav", "audio/x-wav"),
    "mp3": ("audio/mpeg", "audio/mp3"),
    "m4a": ("audio/mp4", "audio/m4a", "audio/x-m4a"),
    "flac": ("audio/flac", "audio/x-flac"),
    "ogg": ("audio/ogg",),
    "aac": ("audio/aac",),
    "wma": ("audio/x-ms-wma",),
}

_MIME_ALIASES = {
    "audio/x-wav": "audio/wav",
    "audio/x-flac": "audio/flac",
    "audio/x-m4a": "audio/mp4",
    "video/x-m4v": "video/mp4",
}

_DOCUMENT_TYPES = frozenset(
    {
        "pdf",
        "docx",
        "pptx",
        "xlsx",
        "html",
        "txt",
        "md",
        "rtf",
        "xml",
        "eml",
        "msg",
    }
)
_IMAGE_TYPES = frozenset({"jpeg", "png", "bmp", "tiff", "heif"})
_VIDEO_TYPES = frozenset({"mp4", "m4v", "mov", "avi", "mkv", "webm", "flv", "wmv"})
_AUDIO_TYPES = frozenset({"wav", "mp3", "m4a", "flac", "ogg", "aac", "wma"})

_PREBUILT_ANALYZERS = {
    "document": "prebuilt-documentSearch",
    "image": "prebuilt-documentSearch",
    "video": "prebuilt-videoSearch",
    "audio": "prebuilt-audioSearch",
}


@dataclass(frozen=True)
class ContentUnderstandingDerivedLimits:
    max_source_bytes: int = 64 * 1024 * 1024
    max_analysis_utf8_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in ("max_source_bytes", "max_analysis_utf8_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class ContentUnderstandingAnalysisSnapshot:
    content: str
    provider: str
    analyzer_id: str
    content_type: str
    api_version: str | None = None
    analysis_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise TypeError("content must be a string")

        for name in ("provider", "analyzer_id", "content_type"):
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


@dataclass(frozen=True)
class _ContentUnderstandingRoute:
    file_type: str
    modality: str
    analyzer_id: str
    content_type: str


def _clean_mime_type(mimetype: str | None) -> str:
    return (mimetype or "").split(";", 1)[0].strip().lower()


def _canonical_mime_type(mimetype: str | None) -> str:
    cleaned = _clean_mime_type(mimetype)
    return _MIME_ALIASES.get(cleaned, cleaned) or "application/octet-stream"


def _detect_file_type(stream_info: StreamInfo) -> str | None:
    extension = (stream_info.extension or "").lower()
    file_type = _EXTENSION_MAP.get(extension)
    if file_type is not None:
        return file_type

    mimetype = _clean_mime_type(stream_info.mimetype)
    if not mimetype:
        return None

    for candidate, prefixes in _MIME_PREFIXES.items():
        for prefix in prefixes:
            if mimetype.startswith(prefix):
                return candidate
    return None


def _get_modality(file_type: str) -> str:
    if file_type in _DOCUMENT_TYPES:
        return "document"
    if file_type in _IMAGE_TYPES:
        return "image"
    if file_type in _VIDEO_TYPES:
        return "video"
    if file_type in _AUDIO_TYPES:
        return "audio"
    raise ValueError(f"Unknown Content Understanding file type: {file_type}")


def _content_type_for(file_type: str, mimetype: str | None) -> str:
    prefixes = _MIME_PREFIXES[file_type]
    canonical = _canonical_mime_type(mimetype)

    if canonical != "application/octet-stream":
        for prefix in prefixes:
            if canonical.startswith(prefix):
                return canonical

    return _canonical_mime_type(prefixes[0])


def _resolve_route(stream_info: StreamInfo) -> _ContentUnderstandingRoute | None:
    file_type = _detect_file_type(stream_info)
    if file_type is None:
        return None

    modality = _get_modality(file_type)
    return _ContentUnderstandingRoute(
        file_type=file_type,
        modality=modality,
        analyzer_id=_PREBUILT_ANALYZERS[modality],
        content_type=_content_type_for(file_type, stream_info.mimetype),
    )


def _capture_source(source_stream: BinaryIO, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= max_bytes:
        remaining = max_bytes + 1 - total
        if remaining <= 0:
            break

        chunk = source_stream.read(min(64 * 1024, remaining))
        if isinstance(chunk, str):
            raise TypeError("Content Understanding source stream must return bytes")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError(
                "Content Understanding source stream returned a non-bytes value"
            )

        data = bytes(chunk)
        if not data:
            break

        chunks.append(data)
        total += len(data)
        if total > max_bytes:
            raise ValueError("Content Understanding source exceeds max_source_bytes")

    return b"".join(chunks)


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


def read_content_understanding_analysis_ir(
    source_stream: BinaryIO,
    *,
    stream_info: StreamInfo,
    analysis: ContentUnderstandingAnalysisSnapshot,
    limits: ContentUnderstandingDerivedLimits | None = None,
) -> DocumentIR:
    if not isinstance(analysis, ContentUnderstandingAnalysisSnapshot):
        raise TypeError("analysis must be a ContentUnderstandingAnalysisSnapshot")

    route = _resolve_route(stream_info)
    if route is None:
        raise ValueError(
            "source is not owned by the default existing "
            "ContentUnderstandingConverter file surface"
        )

    if analysis.analyzer_id != route.analyzer_id:
        raise ValueError(
            "analysis analyzer_id does not match the default "
            f"ContentUnderstandingConverter route: {route.analyzer_id}"
        )
    if analysis.content_type != route.content_type:
        raise ValueError(
            "analysis content_type does not match the default "
            f"ContentUnderstandingConverter route: {route.content_type}"
        )

    active_limits = limits or ContentUnderstandingDerivedLimits()
    source_bytes = _capture_source(
        source_stream,
        max_bytes=active_limits.max_source_bytes,
    )

    analysis_bytes = analysis.content.encode("utf-8")
    if len(analysis_bytes) > active_limits.max_analysis_utf8_bytes:
        raise ValueError("analysis content exceeds max_analysis_utf8_bytes")

    source_digest = sha256(source_bytes).hexdigest()
    analysis_digest = sha256(analysis_bytes).hexdigest()
    uri = stream_info.url

    identity_seed = "\\0".join(
        (
            "content-understanding-derived-analysis",
            source_digest,
            stream_info.filename or "",
            stream_info.mimetype or "",
            stream_info.extension or "",
            uri or "",
            route.file_type,
            route.modality,
            route.analyzer_id,
            route.content_type,
            analysis.provider,
            analysis.api_version or "",
            analysis.analysis_id or "",
            analysis_digest,
            "ContentUnderstandingConverter",
        )
    )
    ids = DocumentIdFactory(seed=identity_seed)
    document_id = ids.new("document")
    canvas_id = ids.new("canvas")
    node_id = ids.new("root")

    evidence: dict[str, object] = {
        "kind": "content-understanding",
        "source_sha256": source_digest,
        "source_size_bytes": len(source_bytes),
        "file_type": route.file_type,
        "modality": route.modality,
        "analyzer_id": route.analyzer_id,
        "content_type": route.content_type,
        "analysis_provider": analysis.provider,
        "analysis_content_sha256": analysis_digest,
        "analysis_content_utf8_size_bytes": len(analysis_bytes),
        "converter": "ContentUnderstandingConverter",
        "converter_blob_sha": _CONTENT_UNDERSTANDING_CONVERTER_BLOB_SHA,
        "network_performed_by_twoways": False,
        "azure_sdk_used_by_twoways": False,
        "credentials_used_by_twoways": False,
        "to_llm_input_called_by_twoways": False,
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
                source_format="content-understanding-analysis",
                canvas_index=0,
                extraction_method=(
                    "ContentUnderstandingConverter-materialized-to-llm-input"
                ),
                metadata={
                    "source_sha256": source_digest,
                    "analysis_content_sha256": analysis_digest,
                    "file_type": route.file_type,
                    "modality": route.modality,
                    "analyzer_id": route.analyzer_id,
                    "content_type": route.content_type,
                    "provider": analysis.provider,
                    "remote_writeback": False,
                },
            ),
        ),
        native_locator=None,
        payload=TextPayload(text=analysis.content),
        metadata={
            CAPABILITY_METADATA_KEY: _derived_capability(),
            "twoways.content_understanding_analysis.content_sha256": analysis_digest,
        },
    )

    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(
            format="content-understanding-analysis-source",
            filename=stream_info.filename,
            mimetype=stream_info.mimetype,
            uri=uri,
            sha256=source_digest,
            size_bytes=len(source_bytes),
        ),
        metadata=DocumentMetadata(
            custom={_CONTENT_UNDERSTANDING_EVIDENCE_KEY: evidence},
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="derived-analysis",
                name=stream_info.filename or "Content Understanding analysis",
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
                    "Content Understanding analysis and has no H23 native or "
                    "remote writeback authority."
                ),
                node_id=node_id,
                canvas_id=canvas_id,
                details={
                    "file_type": route.file_type,
                    "modality": route.modality,
                    "analyzer_id": route.analyzer_id,
                    "provider": analysis.provider,
                    "remote_writeback": False,
                },
            ),
        ),
    )
    validate_document(document)
    return document


__all__ = [
    "ContentUnderstandingAnalysisSnapshot",
    "ContentUnderstandingDerivedLimits",
    "read_content_understanding_analysis_ir",
]
