from __future__ import annotations

from dataclasses import fields
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
from .limits import MsgLimits
from .model import MsgSubjectOwner, ParsedMsg
from .parser import parse_msg

_MSG_READ_LIMITS_KEY = "msg.read_limits.v1"
_MSG_READ_LIMITS_SHA256_KEY = "msg.read_limits.sha256"

_BLOCKER_PRIORITY = (
    "msg.subject.duplicate_property",
    "msg.subject.duplicate_stream",
    "msg.subject.ansi_read_only",
    "msg.subject.property_not_writable",
    "msg.subject.competing_semantics",
    "msg.subject.size_mismatch",
    "msg.subject.invalid_utf16",
    "msg.subject.embedded_nul",
    "msg.subject.missing",
    "msg.structure.invalid",
)


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("MSG source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("MSG source stream returned a non-bytes value")
    return bytes(data)


def _limit_field_names() -> tuple[str, ...]:
    return tuple(field.name for field in fields(MsgLimits))


def _limits_metadata(limits: MsgLimits) -> dict[str, int]:
    return {name: getattr(limits, name) for name in _limit_field_names()}


def _limits_fingerprint(limits: MsgLimits) -> str:
    payload = "\n".join(
        f"{name}={getattr(limits, name)}" for name in _limit_field_names()
    ).encode("ascii")
    return sha256(payload).hexdigest()


def _ranges_metadata(owner: MsgSubjectOwner) -> list[dict[str, int]]:
    return [
        {"start": physical.start, "length": physical.length}
        for physical in owner.stream.physical_ranges
    ]


def _entry_ranges_metadata(owner: MsgSubjectOwner) -> list[dict[str, int]]:
    return [
        {"start": physical.start, "length": physical.length}
        for physical in owner.property_entry.physical_ranges
    ]


def _reason_from_blockers(blockers: tuple[str, ...]) -> str | None:
    blocker_set = set(blockers)
    for reason in _BLOCKER_PRIORITY:
        if reason in blocker_set:
            return reason
    return blockers[0] if blockers else None


def _subject_capability(parsed: ParsedMsg) -> CapabilityDecision:
    reason = _reason_from_blockers(parsed.blockers)
    if reason is not None:
        return CapabilityDecision(
            operation="update_msg_subject_text",
            state=CapabilityState.READ_ONLY,
            reason_code=reason,
        )
    return CapabilityDecision(
        operation="update_msg_subject_text",
        state=CapabilityState.WRITABLE,
        constraints={
            "identity_markdown": False,
            "existing_owner_only": True,
            "fixed_allocation": True,
            "exact_encoded_length": True,
            "encoding": "utf-16-le",
            "source_preservation": "msg-exact-outside-subject-ranges",
            "property_identity_immutable": True,
            "cfb_topology_immutable": True,
        },
    )


def _subject_metadata(
    parsed: ParsedMsg,
    owner: MsgSubjectOwner,
) -> dict[str, Any]:
    directory_entry = parsed.cfb.directory_entries[owner.stream.directory_id]
    return {
        "msg.property_id": owner.property_id,
        "msg.property_type": owner.property_type,
        "msg.property_tag": owner.property_tag,
        "msg.property_name": "PidTagSubject",
        "msg.stream_name": owner.stream.name,
        "msg.property_stream_name": parsed.properties_stream.name,
        "msg.property_entry_index": owner.property_entry.index,
        "msg.property_entry_offset": owner.property_entry.logical_offset,
        "msg.property_entry_sha256": owner.property_entry.raw_sha256,
        "msg.property_entry_flags": owner.property_entry.flags,
        "msg.property_entry_physical_ranges": _entry_ranges_metadata(owner),
        "msg.declared_size": owner.declared_size,
        "msg.subject_stream_size": owner.stream.stream_size,
        "msg.subject_stream_sha256": owner.stream.sha256,
        "msg.subject_directory_id": owner.stream.directory_id,
        "msg.subject_directory_entry_sha256": directory_entry.directory_entry_sha256,
        "msg.subject_chain_kind": owner.stream.chain_kind,
        "msg.subject_chain": list(owner.stream.chain),
        "msg.subject_physical_ranges": _ranges_metadata(owner),
        "msg.cfb_topology_sha256": parsed.cfb.topology_sha256,
        "msg.encoding": "utf-16-le",
        "msg.native_source": True,
    }


def read_msg_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    limits: MsgLimits | None = None,
) -> DocumentIR:
    active_limits = limits or MsgLimits()
    source_bytes = _read_source_bytes(source)
    parsed = parse_msg(source_bytes, limits=active_limits)
    source_digest = sha256(source_bytes).hexdigest()

    document_id = f"msg-document-{source_digest[:24]}"
    canvas_id = f"msg-canvas-{source_digest[:24]}"
    canvas_locator = NativeLocator(
        backend="msg",
        part_uri="/",
        object_id="msg-message",
    )

    nodes: dict[str, Node] = {}
    root_node_ids: list[str] = []
    owner = parsed.subject_owner
    if owner is not None:
        node_id = f"msg-subject-{source_digest[:24]}"
        locator = NativeLocator(
            backend="msg",
            part_uri="/",
            object_id="mapi:0037001F",
            name="PidTagSubject",
            attributes={
                "property_tag": owner.property_tag,
                "directory_id": owner.stream.directory_id,
                "property_entry_index": owner.property_entry.index,
                "property_entry_offset": owner.property_entry.logical_offset,
                "stream_size": owner.stream.stream_size,
                "chain_kind": owner.stream.chain_kind,
                "chain": list(owner.stream.chain),
                "physical_ranges": _ranges_metadata(owner),
            },
        )
        metadata = _subject_metadata(parsed, owner)
        metadata[CAPABILITY_METADATA_KEY] = encode_capabilities(
            (_subject_capability(parsed),)
        )
        node = Node(
            node_id=node_id,
            kind="text",
            semantic_role="msg-subject-text",
            order=0,
            canvas_id=canvas_id,
            provenance=(
                Provenance(
                    source_format="msg",
                    canvas_index=0,
                    part_uri="/",
                    extraction_method="msg-mapi-unicode-subject",
                    metadata={
                        "property_tag": owner.property_tag,
                        "stream_name": owner.stream.name,
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
            format="msg",
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"msg:sha256:{source_digest}",
        ),
        metadata=DocumentMetadata(
            title=owner.value if owner is not None else None,
            subject=owner.value if owner is not None else None,
            custom={
                _MSG_READ_LIMITS_KEY: _limits_metadata(active_limits),
                _MSG_READ_LIMITS_SHA256_KEY: _limits_fingerprint(active_limits),
                "msg.cfb_major_version": parsed.cfb.header.major_version,
                "msg.cfb_sector_size": parsed.cfb.header.sector_size,
                "msg.cfb_mini_sector_size": parsed.cfb.header.mini_sector_size,
                "msg.cfb_mini_stream_cutoff": parsed.cfb.header.mini_stream_cutoff,
                "msg.cfb_topology_sha256": parsed.cfb.topology_sha256,
            },
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="message",
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


class MsgIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (
            (getattr(stream_info, "mimetype", None) or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        return extension == ".msg" or mimetype == "application/vnd.ms-outlook"

    def read(
        self,
        file_stream: BinaryIO,
        stream_info: Any,
        **kwargs: Any,
    ) -> DocumentIR:
        limits = kwargs.pop("limits", None)
        if kwargs:
            raise TypeError(f"unexpected MSG reader options: {sorted(kwargs)}")
        return read_msg_ir(
            file_stream,
            filename=getattr(stream_info, "filename", None),
            mimetype=getattr(stream_info, "mimetype", None),
            limits=limits,
        )
