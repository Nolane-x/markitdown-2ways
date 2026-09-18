from __future__ import annotations

from hashlib import sha256
from typing import Any, BinaryIO

from ...capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from ...ir.document import Canvas, DocumentIR, DocumentMetadata, SourceDescriptor
from ...ir.nodes import Node, TextPayload
from ...ir.provenance import NativeLocator, Provenance
from ...ir.serialization import validate_document
from ...readers.base import DocumentIRReader
from .limits import Mp3Limits
from .model import Mp3Id3v1Owner, ParsedMp3
from .parser import parse_mp3

_MP3_READ_LIMITS_KEY = "mp3.read_limits.v1"
_MP3_READ_LIMITS_SHA256_KEY = "mp3.read_limits.sha256"
_LIMIT_FIELD_NAMES = (
    "max_source_bytes",
    "max_audio_frames",
    "max_frame_bytes",
    "max_terminal_metadata_bytes",
)
_BLOCKER_PRIORITY = (
    "mp3.metadata.id3v2_read_only",
    "mp3.metadata.ape_read_only",
    "mp3.metadata.lyrics3_read_only",
    "mp3.structure.invalid",
    "mp3.audio.unsupported_layer",
    "mp3.audio.free_format_unsupported",
    "mp3.audio_structure_unproven",
)


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("MP3 source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("MP3 source stream returned a non-bytes value")
    return bytes(data)


def _limits_metadata(limits: Mp3Limits) -> dict[str, int]:
    return {
        "max_source_bytes": limits.max_source_bytes,
        "max_audio_frames": limits.max_audio_frames,
        "max_frame_bytes": limits.max_frame_bytes,
        "max_terminal_metadata_bytes": limits.max_terminal_metadata_bytes,
    }


def _limits_fingerprint(limits: Mp3Limits) -> str:
    payload = "\n".join(
        f"{name}={getattr(limits, name)}" for name in _LIMIT_FIELD_NAMES
    ).encode("ascii")
    return sha256(payload).hexdigest()


def _reason_from_blockers(blockers: tuple[str, ...]) -> str | None:
    blocker_set = set(blockers)
    for reason in _BLOCKER_PRIORITY:
        if reason in blocker_set:
            return reason
    return next(
        (reason for reason in blockers if reason != "mp3.id3v1.invalid_padding"),
        None,
    )


def _text_capability(
    parsed: ParsedMp3,
    owner: Mp3Id3v1Owner,
) -> CapabilityDecision:
    reason = _reason_from_blockers(parsed.blockers)
    if reason is None and not parsed.audio_authoritative:
        reason = "mp3.audio_structure_unproven"
    if reason is None and not owner.canonical_padding:
        reason = "mp3.id3v1.invalid_padding"
    if reason is not None:
        return CapabilityDecision(
            operation="update_mp3_id3v1_text",
            state=CapabilityState.READ_ONLY,
            reason_code=reason,
        )
    return CapabilityDecision(
        operation="update_mp3_id3v1_text",
        state=CapabilityState.WRITABLE,
        constraints={
            "identity_markdown": False,
            "existing_owner_only": True,
            "fixed_allocation": True,
            "source_preservation": "mp3-exact-outside-target-slot",
            "field_identity_immutable": True,
        },
    )


def _owner_metadata(
    parsed: ParsedMp3,
    owner: Mp3Id3v1Owner,
) -> dict[str, Any]:
    return {
        "mp3.id3v1_field": owner.field,
        "mp3.id3v1_tag_start": parsed.id3v1_start,
        "mp3.id3v1_tag_end": parsed.id3v1_end,
        "mp3.slot_start": owner.slot_start,
        "mp3.slot_end": owner.slot_end,
        "mp3.slot_length": owner.slot_length,
        "mp3.slot_sha256": owner.slot_sha256,
        "mp3.id3v1_sha256": parsed.id3v1_sha256,
        "mp3.id3v1_version": parsed.id3v1_version,
        "mp3.encoding": "iso-8859-1",
        "mp3.full_width": owner.full_width,
        "mp3.canonical_padding": owner.canonical_padding,
        "mp3.audio_frame_count": len(parsed.audio_frames),
        "mp3.audio_authoritative": parsed.audio_authoritative,
        "mp3.track": parsed.track,
        "mp3.native_source": True,
    }


def read_mp3_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    limits: Mp3Limits | None = None,
) -> DocumentIR:
    active_limits = limits or Mp3Limits()
    source_bytes = _read_source_bytes(source)
    parsed = parse_mp3(source_bytes, limits=active_limits)
    source_digest = sha256(source_bytes).hexdigest()

    document_id = f"mp3-document-{source_digest[:24]}"
    canvas_id = f"mp3-canvas-{source_digest[:24]}"
    canvas_locator = NativeLocator(
        backend="mp3",
        part_uri="/",
        object_id="mp3-audio",
    )

    nodes: dict[str, Node] = {}
    root_node_ids: list[str] = []
    for order, owner in enumerate(parsed.owners):
        node_id = f"mp3-id3v1-{source_digest[:16]}-{owner.field.lower()}"
        locator = NativeLocator(
            backend="mp3",
            part_uri="/",
            object_id=f"id3v1:{owner.field}",
            name=owner.field,
            attributes={
                "field": owner.field,
                "slot_start": owner.slot_start,
                "slot_end": owner.slot_end,
                "slot_length": owner.slot_length,
            },
        )
        capability = _text_capability(parsed, owner)
        metadata = _owner_metadata(parsed, owner)
        metadata[CAPABILITY_METADATA_KEY] = encode_capabilities((capability,))
        node = Node(
            node_id=node_id,
            kind="text",
            semantic_role="mp3-id3v1-text",
            order=order,
            canvas_id=canvas_id,
            provenance=(
                Provenance(
                    source_format="mp3",
                    canvas_index=0,
                    part_uri="/",
                    extraction_method="mp3-id3v1-latin1",
                    metadata={
                        "field": owner.field,
                        "slot_start": owner.slot_start,
                        "slot_end": owner.slot_end,
                    },
                ),
            ),
            native_locator=locator,
            payload=TextPayload(text=owner.value),
            metadata=metadata,
        )
        nodes[node_id] = node
        root_node_ids.append(node_id)

    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(
            format="mp3",
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"mp3:sha256:{source_digest}",
        ),
        metadata=DocumentMetadata(
            custom={
                _MP3_READ_LIMITS_KEY: _limits_metadata(active_limits),
                _MP3_READ_LIMITS_SHA256_KEY: _limits_fingerprint(active_limits),
            }
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="audio",
                name=filename,
                root_node_ids=tuple(root_node_ids),
                native_locator=canvas_locator,
            ),
        ),
        nodes=nodes,
        root_node_ids=tuple(root_node_ids),
    )
    validate_document(document)
    return document


class Mp3IRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (
            (getattr(stream_info, "mimetype", None) or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        return extension == ".mp3" or mimetype == "audio/mpeg"

    def read(
        self,
        file_stream: BinaryIO,
        stream_info: Any,
        **kwargs: Any,
    ) -> DocumentIR:
        limits = kwargs.pop("limits", None)
        if kwargs:
            raise TypeError(f"unexpected MP3 reader options: {sorted(kwargs)}")
        return read_mp3_ir(
            file_stream,
            filename=getattr(stream_info, "filename", None),
            mimetype=getattr(stream_info, "mimetype", None),
            limits=limits,
        )
