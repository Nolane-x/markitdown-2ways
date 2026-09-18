from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
from .limits import Mp3Limits
from .model import Mp3Id3v1Owner, ParsedMp3
from .parser import Mp3FormatError, parse_mp3
from .verification import verify_mp3_candidate

_MP3_READ_LIMITS_KEY = "mp3.read_limits.v1"
_MP3_READ_LIMITS_SHA256_KEY = "mp3.read_limits.sha256"
_LIMIT_FIELD_NAMES = (
    "max_source_bytes",
    "max_audio_frames",
    "max_frame_bytes",
    "max_terminal_metadata_bytes",
)
_SUPPORTED_FIELDS = frozenset({"Title", "Artist", "Album"})
_BLOCKER_MESSAGES = {
    "mp3.metadata.id3v2_read_only": "MP3 source has ID3v2 metadata authority and is read-only.",
    "mp3.metadata.ape_read_only": "MP3 source has APEv2 metadata authority and is read-only.",
    "mp3.metadata.lyrics3_read_only": "MP3 source has Lyrics3 metadata authority and is read-only.",
    "mp3.structure.invalid": "MP3 source structure is not writable in H15.",
    "mp3.audio.unsupported_layer": "MP3 source uses an unsupported MPEG layer.",
    "mp3.audio.free_format_unsupported": "MP3 free-format audio is not writable in H15.",
    "mp3.audio_structure_unproven": "MP3 audio topology cannot be proven for H15 mutation.",
}
_BLOCKER_PRIORITY = tuple(_BLOCKER_MESSAGES)


@dataclass(frozen=True)
class _PreparedEdit:
    node: Node
    owner: Mp3Id3v1Owner
    old_value: str
    value: str
    replacement_slot: bytes

    @property
    def field(self) -> str:
        return self.owner.field

    @property
    def span(self) -> tuple[int, int]:
        return (self.owner.slot_start, self.owner.slot_end)


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("MP3 source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("MP3 source stream returned a non-bytes value")
    return bytes(data)


def _validate_source_authority(document: DocumentIR, source_bytes: bytes) -> None:
    source = document.source
    actual_digest = sha256(source_bytes).hexdigest()
    if source is None or source.format != "mp3" or not source.sha256:
        raise SourcePackageMismatchError(
            "DocumentIR does not contain authoritative MP3 source metadata.",
            details={"reason": "missing_source_authority", "actual": actual_digest},
        )
    if source.sha256 != actual_digest:
        raise SourcePackageMismatchError(
            "Provided MP3 source does not match the DocumentIR source authority.",
            details={
                "reason": "source_digest_mismatch",
                "expected": source.sha256,
                "actual": actual_digest,
            },
        )
    if source.size_bytes is not None and source.size_bytes != len(source_bytes):
        raise SourcePackageMismatchError(
            "Provided MP3 source size does not match the DocumentIR source authority.",
            details={
                "reason": "source_size_mismatch",
                "expected": source.size_bytes,
                "actual": len(source_bytes),
            },
        )


def _limits_fingerprint(limits: Mp3Limits) -> str:
    payload = "\n".join(
        f"{name}={getattr(limits, name)}" for name in _LIMIT_FIELD_NAMES
    ).encode("ascii")
    return sha256(payload).hexdigest()


def _read_time_limits(document: DocumentIR) -> Mp3Limits:
    raw = document.metadata.custom.get(_MP3_READ_LIMITS_KEY)
    if not isinstance(raw, Mapping) or set(raw) != set(_LIMIT_FIELD_NAMES):
        raise PatchPreconditionError(
            "MP3 DocumentIR is missing authoritative read-time limits.",
            details={"reason": "mp3_read_limits_missing_or_invalid"},
        )
    try:
        values = {name: raw[name] for name in _LIMIT_FIELD_NAMES}
        read_time = Mp3Limits(**values)
    except (KeyError, TypeError, ValueError) as exc:
        raise PatchPreconditionError(
            "MP3 DocumentIR contains invalid authoritative read-time limits.",
            details={"reason": "mp3_read_limits_missing_or_invalid"},
        ) from exc

    recorded_fingerprint = document.metadata.custom.get(_MP3_READ_LIMITS_SHA256_KEY)
    actual_fingerprint = _limits_fingerprint(read_time)
    if (
        not isinstance(recorded_fingerprint, str)
        or recorded_fingerprint != actual_fingerprint
    ):
        raise PatchPreconditionError(
            "MP3 authoritative read-time limits are stale or forged.",
            details={
                "reason": "mp3_read_limits_stale_or_forged",
                "expected": recorded_fingerprint,
                "actual": actual_fingerprint,
            },
        )
    return read_time


def _intersect_limits(requested: Mp3Limits, read_time: Mp3Limits) -> Mp3Limits:
    return Mp3Limits(
        max_source_bytes=min(requested.max_source_bytes, read_time.max_source_bytes),
        max_audio_frames=min(requested.max_audio_frames, read_time.max_audio_frames),
        max_frame_bytes=min(requested.max_frame_bytes, read_time.max_frame_bytes),
        max_terminal_metadata_bytes=min(
            requested.max_terminal_metadata_bytes,
            read_time.max_terminal_metadata_bytes,
        ),
    )


def _fresh_parse(source_bytes: bytes, limits: Mp3Limits) -> ParsedMp3:
    try:
        return parse_mp3(source_bytes, limits=limits)
    except Mp3FormatError as exc:
        raise PatchPreconditionError(
            "Authoritative MP3 source no longer satisfies the H15 structural contract.",
            details={"reason": "mp3.structure.invalid", "error": str(exc)},
        ) from exc


def _fresh_blocker(fresh: ParsedMp3) -> str | None:
    blocker_set = set(fresh.blockers)
    for reason in _BLOCKER_PRIORITY:
        if reason in blocker_set:
            return reason
    return next(
        (reason for reason in fresh.blockers if reason != "mp3.id3v1.invalid_padding"),
        None,
    )


def _reject_fresh_authority(fresh: ParsedMp3) -> None:
    reason = _fresh_blocker(fresh)
    if reason is None and not fresh.audio_authoritative:
        reason = "mp3.audio_structure_unproven"
    if reason is None:
        return
    raise UnsupportedEditError(
        _BLOCKER_MESSAGES.get(reason, "MP3 source is read-only for H15 mutation."),
        details={"reason": reason},
    )


def _validate_native_binding(node: Node, fresh: ParsedMp3) -> Mp3Id3v1Owner:
    locator = node.native_locator
    field = node.metadata.get("mp3.id3v1_field")
    slot_start = node.metadata.get("mp3.slot_start")
    slot_end = node.metadata.get("mp3.slot_end")
    slot_length = node.metadata.get("mp3.slot_length")
    if (
        field not in _SUPPORTED_FIELDS
        or not isinstance(slot_start, int)
        or isinstance(slot_start, bool)
        or not isinstance(slot_end, int)
        or isinstance(slot_end, bool)
        or not isinstance(slot_length, int)
        or isinstance(slot_length, bool)
        or locator is None
        or locator.backend != "mp3"
        or locator.part_uri != "/"
        or locator.object_id != f"id3v1:{field}"
        or locator.name != field
        or locator.attributes.get("field") != field
        or locator.attributes.get("slot_start") != slot_start
        or locator.attributes.get("slot_end") != slot_end
        or locator.attributes.get("slot_length") != slot_length
    ):
        raise PatchPreconditionError(
            "MP3 ID3v1 target native locator/binding is invalid or stale.",
            details={
                "reason": "mp3.id3v1.stale_owner",
                "target_node_id": node.node_id,
            },
        )

    try:
        owner = fresh.owner(field)
    except KeyError as exc:
        raise PatchPreconditionError(
            "MP3 ID3v1 native owner is missing in the authoritative source.",
            details={
                "reason": "mp3.id3v1.stale_owner",
                "target_node_id": node.node_id,
            },
        ) from exc

    expected_metadata = {
        "mp3.id3v1_field": owner.field,
        "mp3.id3v1_tag_start": fresh.id3v1_start,
        "mp3.id3v1_tag_end": fresh.id3v1_end,
        "mp3.slot_start": owner.slot_start,
        "mp3.slot_end": owner.slot_end,
        "mp3.slot_length": owner.slot_length,
        "mp3.slot_sha256": owner.slot_sha256,
        "mp3.id3v1_sha256": fresh.id3v1_sha256,
        "mp3.id3v1_version": fresh.id3v1_version,
        "mp3.encoding": "iso-8859-1",
        "mp3.full_width": owner.full_width,
        "mp3.canonical_padding": owner.canonical_padding,
        "mp3.audio_frame_count": len(fresh.audio_frames),
        "mp3.audio_authoritative": fresh.audio_authoritative,
        "mp3.track": fresh.track,
        "mp3.native_source": True,
    }
    for key, expected in expected_metadata.items():
        actual = node.metadata.get(key)
        if actual != expected:
            raise PatchPreconditionError(
                "MP3 ID3v1 immutable native evidence is stale or forged.",
                details={
                    "reason": "mp3.id3v1.stale_owner",
                    "metadata_key": key,
                    "expected": expected,
                    "actual": actual,
                    "target_node_id": node.node_id,
                },
            )
    if not isinstance(node.payload, TextPayload) or node.payload.text != owner.value:
        raise PatchPreconditionError(
            "MP3 ID3v1 semantic owner is stale relative to the authoritative source.",
            details={
                "reason": "mp3.id3v1.stale_owner",
                "target_node_id": node.node_id,
            },
        )
    return owner


def _encode_replacement_slot(owner: Mp3Id3v1Owner, value: str) -> bytes:
    if "\x00" in value:
        raise UnsupportedEditError(
            "MP3 ID3v1 text replacement cannot contain NUL.",
            details={"reason": "mp3.id3v1.invalid_text_encoding"},
        )
    try:
        encoded = value.encode("iso-8859-1")
    except UnicodeEncodeError as exc:
        raise UnsupportedEditError(
            "MP3 ID3v1 replacement must be representable in ISO-8859-1 Latin text.",
            details={"reason": "mp3.id3v1.invalid_text_encoding"},
        ) from exc
    if len(encoded) > owner.slot_length:
        raise UnsupportedEditError(
            "MP3 ID3v1 replacement growth exceeds the existing 30-byte slot.",
            details={"reason": "mp3.id3v1.value_growth"},
        )
    return encoded + b"\x00" * (owner.slot_length - len(encoded))


def _prepare_edits(
    document: DocumentIR,
    fresh: ParsedMp3,
    edits: tuple[EditOperation, ...],
) -> tuple[_PreparedEdit, ...]:
    prepared: list[_PreparedEdit] = []
    seen_fields: set[str] = set()

    for edit in edits:
        if edit.type != "update_mp3_id3v1_text":
            raise UnsupportedEditError(
                "MP3 H15 supports only update_mp3_id3v1_text.",
                details={"reason": "unsupported_edit_type", "edit_type": edit.type},
            )
        if edit.target_node_id is None or edit.target_node_id not in document.nodes:
            raise PatchPreconditionError(
                "MP3 ID3v1 edit target node does not exist in the source IR.",
                details={
                    "reason": "missing_target",
                    "target_node_id": edit.target_node_id,
                },
            )
        node = document.nodes[edit.target_node_id]
        if node.semantic_role != "mp3-id3v1-text" or not isinstance(
            node.payload, TextPayload
        ):
            raise UnsupportedEditError(
                "update_mp3_id3v1_text requires an MP3 native ID3v1 text node.",
                details={"reason": "wrong_node_kind", "target_node_id": node.node_id},
            )

        _reject_fresh_authority(fresh)
        owner = _validate_native_binding(node, fresh)
        if not owner.canonical_padding:
            raise UnsupportedEditError(
                "MP3 ID3v1 target slot has noncanonical padding and is read-only.",
                details={"reason": "mp3.id3v1.invalid_padding", "field": owner.field},
            )
        if owner.field in seen_fields:
            raise UnsupportedEditError(
                "MP3 patch contains a duplicate transaction target.",
                details={"reason": "duplicate_mp3_target", "field": owner.field},
            )
        seen_fields.add(owner.field)

        decision = capabilities_for_node(node).for_operation("update_mp3_id3v1_text")
        if decision.state is not CapabilityState.WRITABLE:
            raise UnsupportedEditError(
                "MP3 ID3v1 capability is read-only for this owner.",
                details={
                    "reason": decision.reason_code or "capability.read_only",
                    "target_node_id": node.node_id,
                },
            )

        if set(edit.payload) != {"field", "old_value", "value"}:
            raise UnsupportedEditError(
                "MP3 ID3v1 payload must contain field, old_value and value only.",
                details={"reason": "invalid_mp3_id3v1_payload"},
            )
        field = edit.payload.get("field")
        old_value = edit.payload.get("old_value")
        value = edit.payload.get("value")
        if not all(isinstance(item, str) for item in (field, old_value, value)):
            raise UnsupportedEditError(
                "MP3 ID3v1 payload fields must all be strings.",
                details={"reason": "invalid_mp3_id3v1_payload"},
            )
        assert isinstance(field, str)
        assert isinstance(old_value, str)
        assert isinstance(value, str)
        if field != owner.field or field != node.metadata.get("mp3.id3v1_field"):
            raise PatchPreconditionError(
                "MP3 ID3v1 field identity is immutable in H15.",
                details={"reason": "mp3.id3v1.field_immutable", "field": field},
            )
        if old_value != owner.value or old_value != node.payload.text:
            raise PatchPreconditionError(
                "MP3 ID3v1 old_value is stale.",
                details={
                    "reason": "mp3.id3v1.stale_owner",
                    "expected": owner.value,
                    "actual": old_value,
                },
            )
        validate_edit_preconditions(document, node, edit, format_label="MP3")

        prepared.append(
            _PreparedEdit(
                node=node,
                owner=owner,
                old_value=old_value,
                value=value,
                replacement_slot=_encode_replacement_slot(owner, value),
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
        start, end = item.span
        candidate[start:end] = item.replacement_slot
    if len(candidate) != len(source_bytes):
        raise PatchPreconditionError(
            "MP3 H15 candidate changed byte length before verification.",
            details={"reason": "mp3.id3v1.candidate_length_drift"},
        )
    return bytes(candidate)


def patch_mp3(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation] = (),
    limits: Mp3Limits | None = None,
) -> WriterResult:
    validate_document(document)
    requested_limits = limits or Mp3Limits()
    active_limits = _intersect_limits(requested_limits, _read_time_limits(document))
    source_bytes = _read_source_bytes(source_stream)
    _validate_source_authority(document, source_bytes)
    fresh = _fresh_parse(source_bytes, active_limits)
    prepared = _prepare_edits(document, fresh, tuple(edits))
    candidate = _construct_candidate(source_bytes, prepared)

    if prepared:
        requested_values = {item.field: item.value for item in prepared}
        requested_ranges = {item.field: item.span for item in prepared}
        verify_mp3_candidate(
            source_bytes,
            candidate,
            requested_values=requested_values,
            requested_ranges=requested_ranges,
            limits=active_limits,
        )

    exact = candidate == source_bytes
    if exact:
        fidelity = FidelityReport(
            claimed_tier="exact-preserve",
            evidence=(
                FidelityEvidence(
                    check_code="mp3.byte_identity",
                    status=FidelityStatus.PASSED,
                    description="MP3 patch preserved source bytes exactly.",
                    expected=sha256(source_bytes).hexdigest(),
                    actual=sha256(candidate).hexdigest(),
                ),
            ),
        )
    else:
        fidelity = FidelityReport(
            claimed_tier="high",
            evidence=(
                FidelityEvidence(
                    check_code="mp3.id3v1.semantic_readback",
                    status=FidelityStatus.PASSED,
                    description="Requested MP3 ID3v1 values passed strict semantic re-read.",
                    expected={item.field: item.value for item in prepared},
                    actual={item.field: item.value for item in prepared},
                    affected_node_ids=tuple(item.node.node_id for item in prepared),
                ),
                FidelityEvidence(
                    check_code="mp3.id3v1.outside_slot_identity",
                    status=FidelityStatus.PASSED,
                    description="Every byte outside authorized ID3v1 slots remained exact.",
                    expected="exact",
                    actual="exact",
                    affected_node_ids=tuple(item.node.node_id for item in prepared),
                ),
            ),
        )

    written = output.write(candidate)
    return WriterResult(
        format="mp3",
        mode="patch",
        bytes_written=len(candidate) if written is None else written,
        fidelity=fidelity,
        metadata={
            "touched_nodes": tuple(item.node.node_id for item in prepared),
            "touched_fields": tuple(item.field for item in prepared),
            "touched_slot_spans": tuple(item.span for item in prepared),
        },
    )


class Mp3PatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        source_format = document.source.format if document.source is not None else None
        if source_format != "mp3":
            return False
        extension = (target.extension or "").lower()
        return target.format.lower() == "mp3" or extension == ".mp3"

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
            raise TypeError("Mp3PatchWriter.write requires source_stream= and edits=")
        if kwargs:
            raise TypeError(f"unexpected MP3 writer options: {sorted(kwargs)}")
        return patch_mp3(
            document,
            source_stream,
            output,
            edits=tuple(edits),
            limits=limits,
        )
