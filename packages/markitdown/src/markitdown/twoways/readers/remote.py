from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import re
from typing import BinaryIO
from urllib.parse import urlsplit

from ..._stream_info import StreamInfo
from ...converters._wikipedia_converter import WikipediaConverter
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


_REMOTE_EVIDENCE_KEY = "twoways.remote_snapshot.v1"
_WIKIPEDIA_CONVERTER_BLOB_SHA = (
    "ba0c751092fa9e37fcf982f1fae9c4dcd774e049"
)


@dataclass(frozen=True)
class RemoteDerivedLimits:
    max_source_bytes: int = 32 * 1024 * 1024
    max_markdown_utf8_bytes: int = 16 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in ("max_source_bytes", "max_markdown_utf8_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")


def _capture_source(source_stream: BinaryIO, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= max_bytes:
        remaining = max_bytes + 1 - total
        if remaining <= 0:
            break
        chunk = source_stream.read(min(64 * 1024, remaining))
        if isinstance(chunk, str):
            raise TypeError("remote snapshot source stream must return bytes")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("remote snapshot source stream returned a non-bytes value")
        data = bytes(chunk)
        if not data:
            break
        chunks.append(data)
        total += len(data)
        if total > max_bytes:
            raise ValueError("remote snapshot exceeds max_source_bytes")
    return b"".join(chunks)


def _validate_remote_url(stream_info: StreamInfo) -> str:
    uri = stream_info.url
    if not isinstance(uri, str) or not uri.strip():
        raise ValueError("Wikipedia snapshot requires stream_info.url")
    uri = uri.strip()
    try:
        parsed = urlsplit(uri)
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
    except ValueError as exc:
        raise ValueError("Wikipedia snapshot URL is malformed") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Wikipedia snapshot URL must use http or https")
    if not hostname:
        raise ValueError("Wikipedia snapshot URL must contain a host")
    if username is not None or password is not None:
        raise ValueError("Wikipedia snapshot URL must not contain credentials")
    return uri


def _normalize_one_way_markdown(markdown: str) -> str:
    normalized = "\n".join(
        line.rstrip() for line in re.split(r"\r?\n", markdown)
    )
    return re.sub(r"\n{3,}", "\n\n", normalized)


def _derived_capability() -> tuple[dict[str, object], ...]:
    return encode_capabilities(
        (
            CapabilityDecision(
                operation="replace_text",
                state=CapabilityState.DERIVED,
                reason_code="remote.source.not_native_writable",
                constraints={
                    "identity_markdown": False,
                    "remote_writeback": False,
                    "native_owner": False,
                    "materialization": "explicit-local-only",
                },
            ),
        )
    )


def read_wikipedia_snapshot_ir(
    source_stream: BinaryIO,
    *,
    stream_info: StreamInfo,
    limits: RemoteDerivedLimits | None = None,
) -> DocumentIR:
    active_limits = limits or RemoteDerivedLimits()
    uri = _validate_remote_url(stream_info)
    source_bytes = _capture_source(
        source_stream,
        max_bytes=active_limits.max_source_bytes,
    )

    converter = WikipediaConverter()
    private_stream = BytesIO(source_bytes)
    if not converter.accepts(private_stream, stream_info):
        raise ValueError(
            "snapshot is not owned by the existing WikipediaConverter "
            "under the supplied StreamInfo"
        )

    result = converter.convert(BytesIO(source_bytes), stream_info)
    markdown = _normalize_one_way_markdown(result.markdown)
    markdown_bytes = markdown.encode("utf-8")
    if len(markdown_bytes) > active_limits.max_markdown_utf8_bytes:
        raise ValueError("derived Markdown exceeds max_markdown_utf8_bytes")

    source_digest = sha256(source_bytes).hexdigest()
    markdown_digest = sha256(markdown_bytes).hexdigest()
    identity_seed = "\0".join(
        (
            "remote-wikipedia-snapshot",
            uri,
            source_digest,
            markdown_digest,
            "WikipediaConverter",
        )
    )
    ids = DocumentIdFactory(seed=identity_seed)
    document_id = ids.new("document")
    canvas_id = ids.new("canvas")
    node_id = ids.new("root")

    evidence: dict[str, object] = {
        "kind": "wikipedia",
        "uri": uri,
        "source_sha256": source_digest,
        "source_size_bytes": len(source_bytes),
        "converter": "WikipediaConverter",
        "converter_blob_sha": _WIKIPEDIA_CONVERTER_BLOB_SHA,
        "markdown_sha256": markdown_digest,
        "markdown_utf8_size_bytes": len(markdown_bytes),
        "network_performed_by_twoways": False,
    }
    if stream_info.filename is not None:
        evidence["filename"] = stream_info.filename
    if stream_info.mimetype is not None:
        evidence["mimetype"] = stream_info.mimetype
    if stream_info.charset is not None:
        evidence["charset"] = stream_info.charset

    node = Node(
        node_id=node_id,
        kind="text",
        semantic_role="derived_document",
        order=0,
        canvas_id=canvas_id,
        provenance=(
            Provenance(
                source_format="remote-wikipedia-snapshot",
                canvas_index=0,
                extraction_method="WikipediaConverter",
                metadata={
                    "uri": uri,
                    "source_sha256": source_digest,
                    "markdown_sha256": markdown_digest,
                    "remote_writeback": False,
                },
            ),
        ),
        native_locator=None,
        payload=TextPayload(text=markdown),
        metadata={
            CAPABILITY_METADATA_KEY: _derived_capability(),
            "twoways.remote_snapshot.kind": "wikipedia",
            "twoways.remote_snapshot.markdown_sha256": markdown_digest,
        },
    )

    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(
            format="remote-wikipedia-snapshot",
            filename=stream_info.filename,
            mimetype=stream_info.mimetype,
            uri=uri,
            sha256=source_digest,
            size_bytes=len(source_bytes),
        ),
        metadata=DocumentMetadata(
            title=result.title,
            custom={_REMOTE_EVIDENCE_KEY: evidence},
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="remote-derived",
                name=result.title or stream_info.filename,
                root_node_ids=(node_id,),
                native_locator=None,
            ),
        ),
        nodes={node_id: node},
        root_node_ids=(node_id,),
        diagnostics=(
            Diagnostic(
                code="remote.source.not_native_writable",
                severity="info",
                message=(
                    "Visible Markdown is derived from a materialized remote "
                    "Wikipedia snapshot and has no H18 remote writeback authority."
                ),
                node_id=node_id,
                canvas_id=canvas_id,
                details={
                    "uri": uri,
                    "remote_writeback": False,
                },
            ),
        ),
    )
    validate_document(document)
    return document


__all__ = [
    "RemoteDerivedLimits",
    "read_wikipedia_snapshot_ir",
]
