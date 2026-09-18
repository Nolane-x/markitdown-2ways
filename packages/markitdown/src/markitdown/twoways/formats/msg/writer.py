from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from hashlib import sha256
from typing import Any, BinaryIO

from ..._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus, WriterResult
from ...capabilities import CapabilityState, capabilities_for_node
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import Node, TextPayload
from ...ir.semantics import validate_edit_preconditions
from ...ir.serialization import validate_document
from ...writers.base import DocumentWriter, TargetInfo
from .limits import MsgLimits
from .model import MsgFormatError, MsgSubjectOwner, ParsedMsg
from .parser import parse_msg
from .verification import verify_msg_candidate

_MSG_READ_LIMITS_KEY = "msg.read_limits.v1"
_MSG_READ_LIMITS_SHA256_KEY = "msg.read_limits.sha256"
_SUBJECT_TAG = 0x0037001F

_BLOCKER_MESSAGES = {
    "msg.subject.duplicate_property": "MSG has duplicate Unicode Subject property authority.",
    "msg.subject.duplicate_stream": "MSG has duplicate Unicode Subject stream authority.",
    "msg.subject.ansi_read_only": "MSG does not have exclusive Unicode Subject authority.",
    "msg.subject.property_not_writable": "MSG Subject property is not writable by its MAPI flags.",
    "msg.subject.competing_semantics": "MSG has competing Subject semantic properties.",
    "msg.subject.size_mismatch": "MSG Subject property size disagrees with its value stream.",
    "msg.subject.invalid_utf16": "MSG Subject is not strict UTF-16LE.",
    "msg.subject.embedded_nul": "MSG Subject contains an embedded NUL.",
    "msg.subject.missing": "MSG Unicode Subject owner is missing.",
    "msg.structure.invalid": "MSG source structure is not writable in H16.",
}


@dataclass(frozen=True)
class _PreparedEdit:
    node: Node
    owner: MsgSubjectOwner
    old_value: str
    value: str
    replacement: bytes

    @property
    def ranges(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (physical.start, physical.end)
            for physical in self.owner.stream.physical_ranges
        )


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("MSG source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("MSG source stream returned a non-bytes value")
    return bytes(data)


def _validate_source_authority(document: DocumentIR, source_bytes: bytes) -> None:
    source = document.source
    actual_digest = sha256(source_bytes).hexdigest()
    if source is None or source.format != "msg" or not source.sha256:
        raise SourcePackageMismatchError(
            "DocumentIR does not contain authoritative MSG source metadata.",
            details={"reason": "missing_source_authority", "actual": actual_digest},
        )
    if source.sha256 != actual_digest:
        raise SourcePackageMismatchError(
            "Provided MSG source does not match the DocumentIR source authority.",
            details={
                "reason": "source_digest_mismatch",
                "expected": source.sha256,
                "actual": actual_digest,
            },
        )
    if source.size_bytes is not None and source.size_bytes != len(source_bytes):
        raise SourcePackageMismatchError(
            "Provided MSG source size does not match the DocumentIR source authority.",
            details={
                "reason": "source_size_mismatch",
                "expected": source.size_bytes,
                "actual": len(source_bytes),
            },
        )


def _limit_field_names() -> tuple[str, ...]:
    return tuple(field.name for field in fields(MsgLimits))


def _limits_fingerprint(limits: MsgLimits) -> str:
    payload = "\n".join(
        f"{name}={getattr(limits, name)}" for name in _limit_field_names()
    ).encode("ascii")
    return sha256(payload).hexdigest()


def _read_time_limits(document: DocumentIR) -> MsgLimits:
    names = _limit_field_names()
    raw = document.metadata.custom.get(_MSG_READ_LIMITS_KEY)
    if not isinstance(raw, Mapping) or set(raw) != set(names):
        raise PatchPreconditionError(
            "MSG DocumentIR is missing authoritative read-time limits.",
            details={"reason": "msg_read_limits_missing_or_invalid"},
        )
    try:
        values = {name: raw[name] for name in names}
        read_time = MsgLimits(**values)
    except (KeyError, TypeError, ValueError) as exc:
        raise PatchPreconditionError(
            "MSG DocumentIR contains invalid authoritative read-time limits.",
            details={"reason": "msg_read_limits_missing_or_invalid"},
        ) from exc

    recorded = document.metadata.custom.get(_MSG_READ_LIMITS_SHA256_KEY)
    actual = _limits_fingerprint(read_time)
    if not isinstance(recorded, str) or recorded != actual:
        raise PatchPreconditionError(
            "MSG authoritative read-time limits are stale or forged.",
            details={
                "reason": "msg_read_limits_stale_or_forged",
                "expected": recorded,
                "actual": actual,
            },
        )
    return read_time


def _intersect_limits(requested: MsgLimits, read_time: MsgLimits) -> MsgLimits:
    return MsgLimits(
        **{
            name: min(getattr(requested, name), getattr(read_time, name))
            for name in _limit_field_names()
        }
    )


def _fresh_parse(source_bytes: bytes, limits: MsgLimits) -> ParsedMsg:
    try:
        return parse_msg(source_bytes, limits=limits)
    except MsgFormatError as exc:
        raise PatchPreconditionError(
            "Authoritative MSG source no longer satisfies the H16 structural contract.",
            details={"reason": "msg.structure.invalid", "error": str(exc)},
        ) from exc


def _reject_fresh_authority(fresh: ParsedMsg) -> None:
    if not fresh.blockers and fresh.subject_owner is not None:
        return
    reason = fresh.blockers[0] if fresh.blockers else "msg.subject.missing"
    raise UnsupportedEditError(
        _BLOCKER_MESSAGES.get(reason, "MSG source is read-only for H16 Subject mutation."),
        details={"reason": reason},
    )


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


def _validate_native_binding(
    node: Node,
    fresh: ParsedMsg,
) -> MsgSubjectOwner:
    owner = fresh.subject_owner
    if owner is None:
        raise PatchPreconditionError(
            "MSG Unicode Subject native owner is missing.",
            details={"reason": "msg.subject.stale_owner", "target_node_id": node.node_id},
        )

    locator = node.native_locator
    if (
        locator is None
        or locator.backend != "msg"
        or locator.part_uri != "/"
        or locator.object_id != "mapi:0037001F"
        or locator.name != "PidTagSubject"
        or locator.attributes.get("property_tag") != owner.property_tag
        or locator.attributes.get("directory_id") != owner.stream.directory_id
        or locator.attributes.get("property_entry_index") != owner.property_entry.index
        or locator.attributes.get("property_entry_offset")
        != owner.property_entry.logical_offset
        or locator.attributes.get("stream_size") != owner.stream.stream_size
        or locator.attributes.get("chain_kind") != owner.stream.chain_kind
        or locator.attributes.get("chain") != list(owner.stream.chain)
        or locator.attributes.get("physical_ranges") != _ranges_metadata(owner)
    ):
        raise PatchPreconditionError(
            "MSG Subject target native locator/binding is invalid or stale.",
            details={"reason": "msg.subject.stale_owner", "target_node_id": node.node_id},
        )

    directory_entry = fresh.cfb.directory_entries[owner.stream.directory_id]
    expected_metadata: dict[str, object] = {
        "msg.property_id": owner.property_id,
        "msg.property_type": owner.property_type,
        "msg.property_tag": owner.property_tag,
        "msg.property_name": "PidTagSubject",
        "msg.stream_name": owner.stream.name,
        "msg.property_stream_name": fresh.properties_stream.name,
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
        "msg.cfb_topology_sha256": fresh.cfb.topology_sha256,
        "msg.encoding": "utf-16-le",
        "msg.native_source": True,
    }
    for key, expected in expected_metadata.items():
        actual = node.metadata.get(key)
        if actual != expected:
            raise PatchPreconditionError(
                "MSG Subject immutable native evidence is stale or forged.",
                details={
                    "reason": "msg.subject.stale_owner",
                    "metadata_key": key,
                    "expected": expected,
                    "actual": actual,
                    "target_node_id": node.node_id,
                },
            )

    if not isinstance(node.payload, TextPayload) or node.payload.text != owner.value:
        raise PatchPreconditionError(
            "MSG Subject semantic owner is stale relative to the authoritative source.",
            details={"reason": "msg.subject.stale_owner", "target_node_id": node.node_id},
        )
    return owner


def _encode_replacement(owner: MsgSubjectOwner, value: str) -> bytes:
    if "\x00" in value:
        raise UnsupportedEditError(
            "MSG Subject replacement cannot contain NUL.",
            details={"reason": "msg.subject.embedded_nul"},
        )
    try:
        encoded = value.encode("utf-16-le", errors="strict")
    except UnicodeEncodeError as exc:
        raise UnsupportedEditError(
            "MSG Subject replacement must be valid UTF-16LE text.",
            details={"reason": "msg.subject.invalid_utf16"},
        ) from exc
    if len(encoded) != owner.stream.stream_size:
        raise UnsupportedEditError(
            "MSG Subject replacement must preserve the exact encoded allocation length.",
            details={
                "reason": "msg.subject.value_size_change",
                "expected": owner.stream.stream_size,
                "actual": len(encoded),
            },
        )
    return encoded


def _prepare_edits(
    document: DocumentIR,
    fresh: ParsedMsg,
    edits: tuple[EditOperation, ...],
) -> tuple[_PreparedEdit, ...]:
    prepared: list[_PreparedEdit] = []
    seen = False

    for edit in edits:
        if edit.type != "update_msg_subject_text":
            raise UnsupportedEditError(
                "MSG H16 supports only update_msg_subject_text.",
                details={"reason": "unsupported_edit_type", "edit_type": edit.type},
            )
        if seen:
            raise UnsupportedEditError(
                "MSG patch contains a duplicate Subject transaction target.",
                details={"reason": "duplicate_msg_subject_target"},
            )
        seen = True
        if edit.target_node_id is None or edit.target_node_id not in document.nodes:
            raise PatchPreconditionError(
                "MSG Subject edit target node does not exist in the source IR.",
                details={"reason": "missing_target", "target_node_id": edit.target_node_id},
            )
        node = document.nodes[edit.target_node_id]
        if node.semantic_role != "msg-subject-text" or not isinstance(
            node.payload, TextPayload
        ):
            raise UnsupportedEditError(
                "update_msg_subject_text requires an MSG native Subject text node.",
                details={"reason": "wrong_node_kind", "target_node_id": node.node_id},
            )

        _reject_fresh_authority(fresh)
        owner = _validate_native_binding(node, fresh)

        decision = capabilities_for_node(node).for_operation("update_msg_subject_text")
        if decision.state is not CapabilityState.WRITABLE:
            raise UnsupportedEditError(
                "MSG Subject capability is read-only for this owner.",
                details={
                    "reason": decision.reason_code or "capability.read_only",
                    "target_node_id": node.node_id,
                },
            )

        if set(edit.payload) != {"property_tag", "old_value", "value"}:
            raise UnsupportedEditError(
                "MSG Subject payload must contain property_tag, old_value and value only.",
                details={"reason": "invalid_msg_subject_payload"},
            )
        property_tag = edit.payload.get("property_tag")
        old_value = edit.payload.get("old_value")
        value = edit.payload.get("value")
        if (
            isinstance(property_tag, bool)
            or not isinstance(property_tag, int)
            or not isinstance(old_value, str)
            or not isinstance(value, str)
        ):
            raise UnsupportedEditError(
                "MSG Subject payload has invalid value types.",
                details={"reason": "invalid_msg_subject_payload"},
            )
        if property_tag != _SUBJECT_TAG or property_tag != owner.property_tag:
            raise PatchPreconditionError(
                "MSG Subject property tag is immutable in H16.",
                details={"reason": "msg.subject.property_tag_immutable"},
            )
        if old_value != owner.value or old_value != node.payload.text:
            raise PatchPreconditionError(
                "MSG Subject old_value is stale.",
                details={
                    "reason": "msg.subject.stale_owner",
                    "expected": owner.value,
                    "actual": old_value,
                },
            )
        validate_edit_preconditions(document, node, edit, format_label="MSG")

        prepared.append(
            _PreparedEdit(
                node=node,
                owner=owner,
                old_value=old_value,
                value=value,
                replacement=_encode_replacement(owner, value),
            )
        )

    return tuple(prepared)


def _construct_candidate(
    source_bytes: bytes,
    prepared: tuple[_PreparedEdit, ...],
) -> bytes:
    candidate = bytearray(source_bytes)
    for item in prepared:
        if item.value == item.old_value:
            continue
        cursor = 0
        for physical in item.owner.stream.physical_ranges:
            take = physical.length
            chunk = item.replacement[cursor : cursor + take]
            if len(chunk) != take:
                raise PatchPreconditionError(
                    "MSG Subject physical range map is incomplete.",
                    details={"reason": "msg.subject.stale_owner"},
                )
            candidate[physical.start : physical.end] = chunk
            cursor += take
        if cursor != len(item.replacement):
            raise PatchPreconditionError(
                "MSG Subject physical range map does not match stream size.",
                details={"reason": "msg.subject.stale_owner"},
            )
    if len(candidate) != len(source_bytes):
        raise PatchPreconditionError(
            "MSG H16 candidate changed byte length before verification.",
            details={"reason": "msg_candidate_length_drift"},
        )
    return bytes(candidate)


def patch_msg(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation] = (),
    limits: MsgLimits | None = None,
) -> WriterResult:
    validate_document(document)
    requested_limits = limits or MsgLimits()
    active_limits = _intersect_limits(requested_limits, _read_time_limits(document))
    source_bytes = _read_source_bytes(source_stream)
    _validate_source_authority(document, source_bytes)
    fresh = _fresh_parse(source_bytes, active_limits)
    prepared = _prepare_edits(document, fresh, tuple(edits))
    candidate = _construct_candidate(source_bytes, prepared)

    if prepared:
        verify_msg_candidate(
            source_bytes,
            candidate,
            requested_subject=prepared[0].value,
            authorized_ranges=prepared[0].ranges,
            limits=active_limits,
        )

    exact = candidate == source_bytes
    affected = tuple(item.node.node_id for item in prepared)
    if exact:
        fidelity = FidelityReport(
            claimed_tier="exact-preserve",
            evidence=(
                FidelityEvidence(
                    check_code="msg.byte_identity",
                    status=FidelityStatus.PASSED,
                    description="MSG patch preserved source bytes exactly.",
                    expected=sha256(source_bytes).hexdigest(),
                    actual=sha256(candidate).hexdigest(),
                    affected_node_ids=affected,
                ),
            ),
        )
    else:
        fidelity = FidelityReport(
            claimed_tier="high",
            evidence=(
                FidelityEvidence(
                    check_code="msg.subject.semantic_readback",
                    status=FidelityStatus.PASSED,
                    description="Requested MSG Subject passed strict semantic re-read.",
                    expected=prepared[0].value,
                    actual=prepared[0].value,
                    affected_node_ids=affected,
                ),
                FidelityEvidence(
                    check_code="msg.subject.outside_range_identity",
                    status=FidelityStatus.PASSED,
                    description="Every byte outside authorized MSG Subject ranges remained exact.",
                    expected="exact",
                    actual="exact",
                    affected_node_ids=affected,
                ),
            ),
        )

    written = output.write(candidate)
    return WriterResult(
        format="msg",
        mode="patch",
        bytes_written=len(candidate) if written is None else written,
        fidelity=fidelity,
        metadata={
            "touched_nodes": affected,
            "touched_property_tags": tuple(item.owner.property_tag for item in prepared),
            "touched_subject_ranges": tuple(
                range_item for item in prepared for range_item in item.ranges
            ),
        },
    )


class MsgPatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        source_format = document.source.format if document.source is not None else None
        if source_format != "msg":
            return False
        extension = (target.extension or "").lower()
        mimetype = (target.mimetype or "").split(";", 1)[0].strip().lower()
        return (
            target.format.lower() == "msg"
            or extension == ".msg"
            or mimetype == "application/vnd.ms-outlook"
        )

    def write(
        self,
        document: DocumentIR,
        output: BinaryIO,
        target: TargetInfo,
        **kwargs: Any,
    ) -> WriterResult:
        source_stream = kwargs.pop("source_stream", None)
        edits = kwargs.pop("edits", None)
        limits = kwargs.pop("limits", None)
        if source_stream is None or edits is None:
            raise TypeError("MsgPatchWriter.write requires source_stream= and edits=")
        if kwargs:
            raise TypeError(f"unexpected MSG writer options: {sorted(kwargs)}")
        return patch_msg(
            document,
            source_stream,
            output,
            edits=tuple(edits),
            limits=limits,
        )
