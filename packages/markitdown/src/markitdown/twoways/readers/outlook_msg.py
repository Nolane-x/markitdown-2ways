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


_MSG_EVIDENCE_KEY = "twoways.outlook_msg_converter_snapshot.v1"
_OUTLOOK_MSG_CONVERTER_BLOB_SHA = "79d7656e5bd32d3b6aaa143a32635d5fb3e8f087"
_ACCEPTED_EXTENSIONS = frozenset({".msg"})
_ACCEPTED_MIME_PREFIXES = ("application/vnd.ms-outlook",)
_SEMANTIC_FIELDS = ("sender", "recipients", "subject", "body")


@dataclass(frozen=True)
class OutlookMsgDerivedLimits:
    max_source_bytes: int = 64 * 1024 * 1024
    max_snapshot_utf8_bytes: int = 32 * 1024 * 1024
    max_markdown_utf8_bytes: int = 32 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in (
            "max_source_bytes",
            "max_snapshot_utf8_bytes",
            "max_markdown_utf8_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class OutlookMsgConverterSnapshot:
    sender: str | None = None
    recipients: str | None = None
    subject: str | None = None
    body: str | None = None
    provider: str = "caller-materialized"
    materialization_id: str | None = None
    message_encoding: str | None = None
    internet_encoding: str | None = None

    def __post_init__(self) -> None:
        for name in _SEMANTIC_FIELDS:
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{name} must be a string or None")

        if not isinstance(self.provider, str):
            raise TypeError("provider must be a string")
        if not self.provider.strip():
            raise ValueError("provider must be non-empty")

        for name in ("materialization_id", "message_encoding", "internet_encoding"):
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


def _capture_source(source_stream: BinaryIO, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= max_bytes:
        remaining = max_bytes + 1 - total
        if remaining <= 0:
            break
        chunk = source_stream.read(min(64 * 1024, remaining))
        if isinstance(chunk, str):
            raise TypeError("OutlookMsgConverter source stream must return bytes")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError(\n                "OutlookMsgConverter source stream returned a non-bytes value"\n            )
        data = bytes(chunk)
        if not data:
            break
        chunks.append(data)
        total += len(data)
        if total > max_bytes:
            raise ValueError("OutlookMsgConverter source exceeds max_source_bytes")
    return b"".join(chunks)


def _value_bytes(value: str | None) -> bytes:
    return b"" if value is None else value.encode("utf-8")


def _value_digest(value: str | None) -> str:
    return sha256(_value_bytes(value)).hexdigest()


def _project_markdown(snapshot: OutlookMsgConverterSnapshot) -> str:
    markdown = "# Email Message\n\n"
    for label, value in (
        ("From", snapshot.sender),
        ("To", snapshot.recipients),
        ("Subject", snapshot.subject),
    ):
        if value:
            markdown += f"**{label}:** {value}\n"
    markdown += "\n## Content\n\n"
    if snapshot.body:
        markdown += snapshot.body
    return markdown.strip()


def _derived_capability() -> tuple[dict[str, object], ...]:
    return encode_capabilities(
        (
            CapabilityDecision(
                operation="replace_text",
                state=CapabilityState.DERIVED,
                reason_code="msg.output.not_native_writable",
                constraints={
                    "identity_markdown": False,
                    "native_owner": False,
                    "remote_writeback": False,
                    "materialization": "explicit-local-only",
                },
            ),
        )
    )


def read_outlook_msg_snapshot_ir(
    source_stream: BinaryIO,
    *,
    stream_info: StreamInfo,
    snapshot: OutlookMsgConverterSnapshot,
    limits: OutlookMsgDerivedLimits | None = None,
) -> DocumentIR:
    if not isinstance(snapshot, OutlookMsgConverterSnapshot):
        raise TypeError("snapshot must be an OutlookMsgConverterSnapshot")

    accepted_by = _accepted_by(stream_info)
    if accepted_by is None:
        raise ValueError(
            "source is not owned by the explicit OutlookMsgConverter extension/MIME acceptance surface"
        )

    active_limits = limits or OutlookMsgDerivedLimits()
    source_bytes = _capture_source(\n        source_stream, max_bytes=active_limits.max_source_bytes\n    )
    semantic_values = tuple(getattr(snapshot, name) for name in _SEMANTIC_FIELDS)
    snapshot_utf8_size = sum(len(_value_bytes(value)) for value in semantic_values)
    if snapshot_utf8_size > active_limits.max_snapshot_utf8_bytes:
        raise ValueError("MSG semantic snapshot exceeds max_snapshot_utf8_bytes")

    markdown = _project_markdown(snapshot)
    markdown_bytes = markdown.encode("utf-8")
    if len(markdown_bytes) > active_limits.max_markdown_utf8_bytes:
        raise ValueError("derived Markdown exceeds max_markdown_utf8_bytes")

    source_digest = sha256(source_bytes).hexdigest()
    markdown_digest = sha256(markdown_bytes).hexdigest()
    uri = stream_info.url

    identity_fields: list[str] = []
    for name, value in zip(_SEMANTIC_FIELDS, semantic_values):
        identity_fields.extend(
            (name, "present" if value is not None else "absent", _value_digest(value))
        )

    identity_seed = "\0".join(
        (
            "outlook-msg-converter-derived-snapshot",
            source_digest,
            stream_info.filename or "",
            stream_info.mimetype or "",
            stream_info.extension or "",
            uri or "",
            accepted_by,
            *identity_fields,
            snapshot.provider,
            snapshot.materialization_id or "",
            snapshot.message_encoding or "",
            snapshot.internet_encoding or "",
            markdown_digest,
            "OutlookMsgConverter",
        )
    )
    ids = DocumentIdFactory(seed=identity_seed)
    document_id = ids.new("document")
    canvas_id = ids.new("canvas")
    node_id = ids.new("root")

    evidence: dict[str, object] = {
        "kind": "outlook-msg-converter-derived",
        "source_sha256": source_digest,
        "source_size_bytes": len(source_bytes),
        "accepted_by": accepted_by,
        "provider": snapshot.provider,
        "snapshot_utf8_size_bytes": snapshot_utf8_size,
        "markdown_sha256": markdown_digest,
        "markdown_utf8_size_bytes": len(markdown_bytes),
        "converter": "OutlookMsgConverter",
        "converter_blob_sha": _OUTLOOK_MSG_CONVERTER_BLOB_SHA,
        "ole_parser_executed_by_twoways": False,
        "charset_detection_executed_by_twoways": False,
        "network_performed_by_twoways": False,
        "subprocess_performed_by_twoways": False,
    }
    for name, value in zip(_SEMANTIC_FIELDS, semantic_values):
        encoded = _value_bytes(value)
        evidence[f"{name}_present"] = value is not None
        evidence[f"{name}_sha256"] = sha256(encoded).hexdigest()
        evidence[f"{name}_utf8_size_bytes"] = len(encoded)

    if snapshot.materialization_id is not None:
        evidence["materialization_id"] = snapshot.materialization_id
    if snapshot.message_encoding is not None:
        evidence["message_encoding"] = snapshot.message_encoding
    if snapshot.internet_encoding is not None:
        evidence["internet_encoding"] = snapshot.internet_encoding
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
        semantic_role="derived_message",
        order=0,
        canvas_id=canvas_id,
        provenance=(
            Provenance(
                source_format="outlook-msg-converter-derived",
                canvas_index=0,
                extraction_method="OutlookMsgConverter-caller-materialization",
                metadata={
                    "source_sha256": source_digest,
                    "sender_sha256": _value_digest(snapshot.sender),
                    "recipients_sha256": _value_digest(snapshot.recipients),
                    "subject_sha256": _value_digest(snapshot.subject),
                    "body_sha256": _value_digest(snapshot.body),
                    "markdown_sha256": markdown_digest,
                    "provider": snapshot.provider,
                    "native_owner": False,
                },
            ),
        ),
        native_locator=None,
        payload=TextPayload(text=markdown),
        metadata={
            CAPABILITY_METADATA_KEY: _derived_capability(),
            "twoways.outlook_msg_converter_snapshot.markdown_sha256": markdown_digest,
        },
    )

    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(
            format="outlook-msg-converter-derived-source",
            filename=stream_info.filename,
            mimetype=stream_info.mimetype,
            uri=uri,
            sha256=source_digest,
            size_bytes=len(source_bytes),
        ),
        metadata=DocumentMetadata(
            title=snapshot.subject,
            subject=snapshot.subject,
            custom={_MSG_EVIDENCE_KEY: evidence},
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="derived-message",
                name=stream_info.filename or "OutlookMsgConverter derived output",
                root_node_ids=(node_id,),
                native_locator=None,
            ),
        ),
        nodes={node_id: node},
        root_node_ids=(node_id,),
        diagnostics=(
            Diagnostic(
                code="msg.output.not_native_writable",
                severity="info",
                message=(
                    "Materialized OutlookMsgConverter message text is derived and has no "
                    "H26 native write authority. H16 remains the native PidTagSubject authority."
                ),
                node_id=node_id,
                canvas_id=canvas_id,
                details={
                    "accepted_by": accepted_by,
                    "provider": snapshot.provider,
                    "native_owner": False,
                },
            ),
        ),
    )
    validate_document(document)
    return document


__all__ = [
    "OutlookMsgConverterSnapshot",
    "OutlookMsgDerivedLimits",
    "read_outlook_msg_snapshot_ir",
]
