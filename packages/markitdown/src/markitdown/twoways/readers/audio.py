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


_AUDIO_EVIDENCE_KEY = "twoways.audio_converter_snapshot.v1"
_AUDIO_CONVERTER_BLOB_SHA = "3d96b53c85490021269f198df94e50096f738b19"

_ACCEPTED_EXTENSIONS = frozenset({".wav", ".mp3", ".m4a", ".mp4"})
_ACCEPTED_MIME_PREFIXES = ("audio/x-wav", "audio/mpeg", "video/mp4")


@dataclass(frozen=True)
class AudioDerivedLimits:
    max_source_bytes: int = 64 * 1024 * 1024
    max_markdown_utf8_bytes: int = 32 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in ("max_source_bytes", "max_markdown_utf8_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class AudioConverterSnapshot:
    content: str
    provider: str
    materialization_id: str | None = None
    metadata_provider: str | None = None
    transcript_provider: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise TypeError("content must be a string")
        if not isinstance(self.provider, str):
            raise TypeError("provider must be a string")
        if not self.provider.strip():
            raise ValueError("provider must be non-empty")

        for name in (
            "materialization_id",
            "metadata_provider",
            "transcript_provider",
        ):
            value = getattr(self, name)
            if value is None:
                continue
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string when provided")
            if not value.strip():
                raise ValueError(f"{name} must be non-empty when provided")


def _accepted_by(stream_info: StreamInfo) -> str | None:
    extension = (stream_info.extension or "").lower()
    mimetype = (stream_info.mimetype or "").lower()

    if extension in _ACCEPTED_EXTENSIONS:
        return "extension"
    if any(mimetype.startswith(prefix) for prefix in _ACCEPTED_MIME_PREFIXES):
        return "mimetype"
    return None


def _transcription_format(stream_info: StreamInfo) -> str | None:
    # Mirror AudioConverter.convert() exactly, including its raw StreamInfo equality
    # checks and branch order. Do not normalize/lowercase here.
    if stream_info.extension == ".wav" or stream_info.mimetype == "audio/x-wav":
        return "wav"
    if stream_info.extension == ".mp3" or stream_info.mimetype == "audio/mpeg":
        return "mp3"
    if stream_info.extension in (".mp4", ".m4a") or stream_info.mimetype == "video/mp4":
        return "mp4"
    return None


def _capture_source(source_stream: BinaryIO, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= max_bytes:
        remaining = max_bytes + 1 - total
        if remaining <= 0:
            break

        chunk = source_stream.read(min(64 * 1024, remaining))
        if isinstance(chunk, str):
            raise TypeError("AudioConverter source stream must return bytes")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("AudioConverter source stream returned a non-bytes value")

        data = bytes(chunk)
        if not data:
            break

        chunks.append(data)
        total += len(data)
        if total > max_bytes:
            raise ValueError("AudioConverter source exceeds max_source_bytes")

    return b"".join(chunks)


def _derived_capability() -> tuple[dict[str, object], ...]:
    return encode_capabilities(
        (
            CapabilityDecision(
                operation="replace_text",
                state=CapabilityState.DERIVED,
                reason_code="audio.output.not_native_writable",
                constraints={
                    "identity_markdown": False,
                    "native_owner": False,
                    "remote_writeback": False,
                    "materialization": "explicit-local-only",
                },
            ),
        )
    )


def read_audio_snapshot_ir(
    source_stream: BinaryIO,
    *,
    stream_info: StreamInfo,
    snapshot: AudioConverterSnapshot,
    limits: AudioDerivedLimits | None = None,
) -> DocumentIR:
    if not isinstance(snapshot, AudioConverterSnapshot):
        raise TypeError("snapshot must be an AudioConverterSnapshot")

    accepted_by = _accepted_by(stream_info)
    if accepted_by is None:
        raise ValueError(
            "source is not owned by the existing AudioConverter acceptance surface"
        )

    active_limits = limits or AudioDerivedLimits()
    source_bytes = _capture_source(
        source_stream,
        max_bytes=active_limits.max_source_bytes,
    )

    markdown_bytes = snapshot.content.encode("utf-8")
    if len(markdown_bytes) > active_limits.max_markdown_utf8_bytes:
        raise ValueError("materialized Markdown exceeds max_markdown_utf8_bytes")

    source_digest = sha256(source_bytes).hexdigest()
    markdown_digest = sha256(markdown_bytes).hexdigest()
    transcription_format = _transcription_format(stream_info)
    uri = stream_info.url

    identity_seed = "\0".join(
        (
            "audio-converter-derived-snapshot",
            source_digest,
            stream_info.filename or "",
            stream_info.mimetype or "",
            stream_info.extension or "",
            uri or "",
            accepted_by,
            transcription_format or "",
            snapshot.provider,
            snapshot.materialization_id or "",
            snapshot.metadata_provider or "",
            snapshot.transcript_provider or "",
            markdown_digest,
            "AudioConverter",
        )
    )
    ids = DocumentIdFactory(seed=identity_seed)
    document_id = ids.new("document")
    canvas_id = ids.new("canvas")
    node_id = ids.new("root")

    evidence: dict[str, object] = {
        "kind": "audio-converter-derived",
        "source_sha256": source_digest,
        "source_size_bytes": len(source_bytes),
        "accepted_by": accepted_by,
        "transcription_format": transcription_format,
        "markdown_sha256": markdown_digest,
        "markdown_utf8_size_bytes": len(markdown_bytes),
        "provider": snapshot.provider,
        "converter": "AudioConverter",
        "converter_blob_sha": _AUDIO_CONVERTER_BLOB_SHA,
        "exiftool_executed_by_twoways": False,
        "transcription_executed_by_twoways": False,
        "network_performed_by_twoways": False,
        "subprocess_performed_by_twoways": False,
    }
    if snapshot.materialization_id is not None:
        evidence["materialization_id"] = snapshot.materialization_id
    if snapshot.metadata_provider is not None:
        evidence["metadata_provider"] = snapshot.metadata_provider
    if snapshot.transcript_provider is not None:
        evidence["transcript_provider"] = snapshot.transcript_provider
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
        semantic_role="derived_audio",
        order=0,
        canvas_id=canvas_id,
        provenance=(
            Provenance(
                source_format="audio-converter-derived",
                canvas_index=0,
                extraction_method="AudioConverter-materialized-markdown",
                metadata={
                    "source_sha256": source_digest,
                    "markdown_sha256": markdown_digest,
                    "accepted_by": accepted_by,
                    "transcription_format": transcription_format,
                    "provider": snapshot.provider,
                    "native_owner": False,
                },
            ),
        ),
        native_locator=None,
        payload=TextPayload(text=snapshot.content),
        metadata={
            CAPABILITY_METADATA_KEY: _derived_capability(),
            "twoways.audio_converter_snapshot.markdown_sha256": markdown_digest,
        },
    )

    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(
            format="audio-converter-derived-source",
            filename=stream_info.filename,
            mimetype=stream_info.mimetype,
            uri=uri,
            sha256=source_digest,
            size_bytes=len(source_bytes),
        ),
        metadata=DocumentMetadata(custom={_AUDIO_EVIDENCE_KEY: evidence}),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="derived-audio",
                name=stream_info.filename or "AudioConverter derived output",
                root_node_ids=(node_id,),
                native_locator=None,
            ),
        ),
        nodes={node_id: node},
        root_node_ids=(node_id,),
        diagnostics=(
            Diagnostic(
                code="audio.output.not_native_writable",
                severity="info",
                message=(
                    "Materialized AudioConverter Markdown is derived and has no H24 "
                    "native write authority. H15 remains the native MP3 ID3v1 authority."
                ),
                node_id=node_id,
                canvas_id=canvas_id,
                details={
                    "accepted_by": accepted_by,
                    "transcription_format": transcription_format,
                    "provider": snapshot.provider,
                    "native_owner": False,
                },
            ),
        ),
    )
    validate_document(document)
    return document


__all__ = [
    "AudioConverterSnapshot",
    "AudioDerivedLimits",
    "read_audio_snapshot_ir",
]
