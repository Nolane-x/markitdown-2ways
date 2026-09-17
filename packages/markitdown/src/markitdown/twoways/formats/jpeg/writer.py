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
from .limits import JpegLimits
from .model import JpegExifTextOwner, ParsedJpeg
from .parser import JpegFormatError, parse_jpeg
from .verification import OwnerKey, verify_jpeg_candidate

_JPEG_READ_LIMITS_KEY = "jpeg.read_limits.v1"
_LIMIT_FIELD_NAMES = (
    "max_source_bytes",
    "max_markers",
    "max_segment_data_bytes",
    "max_ifd_depth",
    "max_ifd_entries",
    "max_total_ifd_entries",
    "max_tiff_value_bytes",
    "max_text_value_bytes",
)
_BLOCKER_MESSAGES = {
    "jpeg.exif.multiple_segments": "JPEG source has multiple Exif segments and is read-only.",
    "jpeg.metadata.xmp_read_only": "JPEG source has XMP metadata authority and is read-only.",
    "jpeg.metadata.iptc_read_only": "JPEG source has IPTC metadata authority and is read-only.",
    "jpeg.structure.trailing_bytes": "JPEG source has trailing bytes after EOI and is read-only.",
    "jpeg.exif.value_overlap": "JPEG Exif value allocations overlap and are read-only.",
    "jpeg.exif.duplicate_tag": "JPEG Exif target tag ownership is duplicate and read-only.",
    "jpeg.exif.unsupported_type": "JPEG Exif target type is unsupported for mutation.",
    "jpeg.exif.invalid_text_encoding": "JPEG Exif target text encoding is invalid for mutation.",
}
_BLOCKER_PRIORITY = tuple(_BLOCKER_MESSAGES)


@dataclass(frozen=True)
class _PreparedEdit:
    node: Node
    owner: JpegExifTextOwner
    key: OwnerKey
    old_value: str
    value: str
    replacement_slot: bytes

    @property
    def span(self) -> tuple[int, int]:
        return (
            self.owner.value_offset,
            self.owner.value_offset + self.owner.value_length,
        )


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("JPEG source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("JPEG source stream returned a non-bytes value")
    return bytes(data)


def _validate_source_authority(document: DocumentIR, source_bytes: bytes) -> None:
    source = document.source
    actual_digest = sha256(source_bytes).hexdigest()
    if source is None or source.format != "jpeg" or not source.sha256:
        raise SourcePackageMismatchError(
            "DocumentIR does not contain authoritative JPEG source metadata.",
            details={"reason": "missing_source_authority", "actual": actual_digest},
        )
    if source.sha256 != actual_digest:
        raise SourcePackageMismatchError(
            "Provided JPEG source does not match the DocumentIR source authority.",
            details={
                "reason": "source_digest_mismatch",
                "expected": source.sha256,
                "actual": actual_digest,
            },
        )
    if source.size_bytes is not None and source.size_bytes != len(source_bytes):
        raise SourcePackageMismatchError(
            "Provided JPEG source size does not match the DocumentIR source authority.",
            details={
                "reason": "source_size_mismatch",
                "expected": source.size_bytes,
                "actual": len(source_bytes),
            },
        )


def _read_time_limits(document: DocumentIR) -> JpegLimits:
    raw = document.metadata.custom.get(_JPEG_READ_LIMITS_KEY)
    if not isinstance(raw, Mapping) or set(raw) != set(_LIMIT_FIELD_NAMES):
        raise PatchPreconditionError(
            "JPEG DocumentIR is missing authoritative read-time limits.",
            details={"reason": "jpeg_read_limits_missing_or_invalid"},
        )
    try:
        values = {name: raw[name] for name in _LIMIT_FIELD_NAMES}
        return JpegLimits(**values)
    except (KeyError, TypeError, ValueError) as exc:
        raise PatchPreconditionError(
            "JPEG DocumentIR contains invalid authoritative read-time limits.",
            details={"reason": "jpeg_read_limits_missing_or_invalid"},
        ) from exc


def _intersect_limits(requested: JpegLimits, read_time: JpegLimits) -> JpegLimits:
    return JpegLimits(
        max_source_bytes=min(requested.max_source_bytes, read_time.max_source_bytes),
        max_markers=min(requested.max_markers, read_time.max_markers),
        max_segment_data_bytes=min(
            requested.max_segment_data_bytes, read_time.max_segment_data_bytes
        ),
        max_ifd_depth=min(requested.max_ifd_depth, read_time.max_ifd_depth),
        max_ifd_entries=min(requested.max_ifd_entries, read_time.max_ifd_entries),
        max_total_ifd_entries=min(
            requested.max_total_ifd_entries, read_time.max_total_ifd_entries
        ),
        max_tiff_value_bytes=min(
            requested.max_tiff_value_bytes, read_time.max_tiff_value_bytes
        ),
        max_text_value_bytes=min(
            requested.max_text_value_bytes, read_time.max_text_value_bytes
        ),
    )


def _fresh_parse(source_bytes: bytes, limits: JpegLimits) -> ParsedJpeg:
    try:
        return parse_jpeg(source_bytes, limits=limits)
    except JpegFormatError as exc:
        raise PatchPreconditionError(
            "Authoritative JPEG source no longer satisfies the H14 structural contract.",
            details={"reason": "jpeg.structure.invalid", "error": str(exc)},
        ) from exc


def _fresh_blocker(fresh: ParsedJpeg) -> str | None:
    blocker_set = set(fresh.blockers)
    for reason in _BLOCKER_PRIORITY:
        if reason in blocker_set:
            return reason
    return fresh.blockers[0] if fresh.blockers else None


def _reject_fresh_blocker(fresh: ParsedJpeg) -> None:
    reason = _fresh_blocker(fresh)
    if reason is None:
        return
    raise UnsupportedEditError(
        _BLOCKER_MESSAGES.get(reason, "JPEG source is read-only for H14 mutation."),
        details={"reason": reason},
    )


def _owner_key(owner: JpegExifTextOwner) -> OwnerKey:
    return (owner.marker_index, owner.entry_offset, owner.tag_id)


def _validate_native_binding(
    node: Node,
    fresh: ParsedJpeg,
) -> JpegExifTextOwner:
    locator = node.native_locator
    marker_index = node.metadata.get("jpeg.marker_index")
    ifd_path = node.metadata.get("jpeg.ifd_path")
    entry_offset = node.metadata.get("jpeg.ifd_entry_offset")
    tag_id = node.metadata.get("jpeg.exif_tag_id")
    tag_name = node.metadata.get("jpeg.exif_tag_name")
    value_offset = node.metadata.get("jpeg.value_offset")
    value_length = node.metadata.get("jpeg.value_length")

    if (
        not isinstance(marker_index, int)
        or isinstance(marker_index, bool)
        or not isinstance(entry_offset, int)
        or isinstance(entry_offset, bool)
        or not isinstance(tag_id, int)
        or isinstance(tag_id, bool)
        or not isinstance(tag_name, str)
        or not isinstance(ifd_path, str)
        or not isinstance(value_offset, int)
        or isinstance(value_offset, bool)
        or not isinstance(value_length, int)
        or isinstance(value_length, bool)
        or locator is None
        or locator.backend != "jpeg"
        or locator.part_uri != "/"
        or locator.object_id
        != f"app1:{marker_index}:ifd:{ifd_path}:entry:{entry_offset}:tag:{tag_id}"
        or locator.name != tag_name
        or locator.attributes.get("marker_index") != marker_index
        or locator.attributes.get("ifd_path") != ifd_path
        or locator.attributes.get("entry_offset") != entry_offset
        or locator.attributes.get("tag_id") != tag_id
        or locator.attributes.get("value_offset") != value_offset
        or locator.attributes.get("value_length") != value_length
    ):
        raise PatchPreconditionError(
            "JPEG Exif target native locator/binding is invalid or stale.",
            details={
                "reason": "jpeg.exif.stale_owner",
                "target_node_id": node.node_id,
            },
        )

    matches = tuple(
        owner
        for owner in fresh.text_owners
        if owner.marker_index == marker_index
        and owner.entry_offset == entry_offset
        and owner.tag_id == tag_id
    )
    if len(matches) != 1:
        raise PatchPreconditionError(
            "JPEG Exif native owner is missing or ambiguous in the authoritative source.",
            details={
                "reason": "jpeg.exif.stale_owner",
                "target_node_id": node.node_id,
                "matches": len(matches),
            },
        )
    owner = matches[0]
    marker = fresh.marker(owner.marker_index)
    expected_metadata = {
        "jpeg.exif_tag_id": owner.tag_id,
        "jpeg.exif_tag_name": owner.tag_name,
        "jpeg.marker_index": owner.marker_index,
        "jpeg.segment_start": marker.start,
        "jpeg.segment_end": marker.end,
        "jpeg.ifd_path": owner.ifd_path,
        "jpeg.ifd_entry_offset": owner.entry_offset,
        "jpeg.tiff_type": owner.tiff_type,
        "jpeg.count": owner.count,
        "jpeg.tiff_byte_order": owner.byte_order,
        "jpeg.value_offset": owner.value_offset,
        "jpeg.value_length": owner.value_length,
        "jpeg.inline_value": owner.inline_value,
        "jpeg.value_slot_sha256": owner.value_slot_sha256,
        "jpeg.app1_sha256": owner.app1_sha256,
        "jpeg.marker_raw_sha256": marker.raw_sha256,
    }
    for key, expected in expected_metadata.items():
        actual = node.metadata.get(key)
        if actual != expected:
            raise PatchPreconditionError(
                "JPEG Exif immutable native evidence is stale or forged.",
                details={
                    "reason": "jpeg.exif.stale_owner",
                    "metadata_key": key,
                    "expected": expected,
                    "actual": actual,
                    "target_node_id": node.node_id,
                },
            )
    if not isinstance(node.payload, TextPayload) or node.payload.text != owner.value:
        raise PatchPreconditionError(
            "JPEG Exif semantic owner is stale relative to the authoritative source.",
            details={
                "reason": "jpeg.exif.stale_owner",
                "target_node_id": node.node_id,
            },
        )
    return owner


def _encode_replacement_slot(
    owner: JpegExifTextOwner,
    value: str,
    *,
    limits: JpegLimits,
) -> bytes:
    if "\x00" in value:
        raise UnsupportedEditError(
            "JPEG Exif text replacement cannot contain NUL.",
            details={"reason": "jpeg.exif.invalid_text_encoding"},
        )
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise UnsupportedEditError(
            "JPEG H14 Exif text replacement must be strict ASCII.",
            details={"reason": "jpeg.exif.invalid_text_encoding"},
        ) from exc
    if len(encoded) > limits.max_text_value_bytes:
        raise UnsupportedEditError(
            "JPEG Exif replacement exceeds the effective text value limit.",
            details={"reason": "jpeg.resource_limit"},
        )
    if owner.tiff_type != 2 or owner.value_length != owner.count:
        raise PatchPreconditionError(
            "JPEG Exif target no longer has the fixed type-2 allocation required by H14.",
            details={"reason": "jpeg.exif.stale_owner"},
        )
    if len(encoded) + 1 > owner.value_length:
        raise UnsupportedEditError(
            "JPEG Exif replacement growth exceeds the existing fixed allocation.",
            details={"reason": "jpeg.exif.value_growth"},
        )
    return encoded + b"\x00" + b"\x00" * (owner.value_length - len(encoded) - 1)


def _prepare_edits(
    document: DocumentIR,
    fresh: ParsedJpeg,
    edits: tuple[EditOperation, ...],
    limits: JpegLimits,
) -> tuple[_PreparedEdit, ...]:
    prepared: list[_PreparedEdit] = []
    seen_keys: set[OwnerKey] = set()
    seen_spans: list[tuple[int, int]] = []

    for edit in edits:
        if edit.type != "update_jpeg_exif_text":
            raise UnsupportedEditError(
                "JPEG H14 supports only update_jpeg_exif_text.",
                details={"reason": "unsupported_edit_type", "edit_type": edit.type},
            )
        if edit.target_node_id is None or edit.target_node_id not in document.nodes:
            raise PatchPreconditionError(
                "JPEG Exif edit target node does not exist in the source IR.",
                details={
                    "reason": "missing_target",
                    "target_node_id": edit.target_node_id,
                },
            )
        node = document.nodes[edit.target_node_id]
        if node.semantic_role != "jpeg-exif-text" or not isinstance(
            node.payload, TextPayload
        ):
            raise UnsupportedEditError(
                "update_jpeg_exif_text requires a JPEG native Exif text node.",
                details={"reason": "wrong_node_kind", "target_node_id": node.node_id},
            )

        _reject_fresh_blocker(fresh)
        owner = _validate_native_binding(node, fresh)
        key = _owner_key(owner)
        if fresh.tag_counts.get(owner.tag_id, 0) != 1:
            raise UnsupportedEditError(
                "JPEG Exif target tag ownership is duplicate and read-only.",
                details={"reason": "jpeg.exif.duplicate_tag", "tag_id": owner.tag_id},
            )
        if owner.ambiguous:
            raise UnsupportedEditError(
                "JPEG Exif target allocation overlaps another native owner.",
                details={"reason": "jpeg.exif.value_overlap", "tag_id": owner.tag_id},
            )
        if key in seen_keys:
            raise UnsupportedEditError(
                "JPEG patch contains a duplicate transaction target.",
                details={"reason": "duplicate_jpeg_target", "key": key},
            )
        seen_keys.add(key)

        decision = capabilities_for_node(node).for_operation("update_jpeg_exif_text")
        if decision.state is not CapabilityState.WRITABLE:
            raise UnsupportedEditError(
                "JPEG Exif capability is read-only for this owner.",
                details={
                    "reason": decision.reason_code or "capability.read_only",
                    "target_node_id": node.node_id,
                },
            )

        if set(edit.payload) != {"tag_id", "old_value", "value"}:
            raise UnsupportedEditError(
                "JPEG Exif payload must contain tag_id, old_value and value only.",
                details={"reason": "invalid_jpeg_exif_payload"},
            )
        tag_id = edit.payload.get("tag_id")
        old_value = edit.payload.get("old_value")
        value = edit.payload.get("value")
        if (
            not isinstance(tag_id, int)
            or isinstance(tag_id, bool)
            or not isinstance(old_value, str)
            or not isinstance(value, str)
        ):
            raise UnsupportedEditError(
                "JPEG Exif payload fields have invalid types.",
                details={"reason": "invalid_jpeg_exif_payload"},
            )
        if tag_id != owner.tag_id or tag_id != node.metadata.get("jpeg.exif_tag_id"):
            raise PatchPreconditionError(
                "JPEG Exif tag identity is immutable in H14.",
                details={"reason": "jpeg.exif.tag_immutable", "tag_id": tag_id},
            )
        if old_value != owner.value or old_value != node.payload.text:
            raise PatchPreconditionError(
                "JPEG Exif old_value is stale.",
                details={
                    "reason": "jpeg.exif.stale_owner",
                    "expected": owner.value,
                    "actual": old_value,
                },
            )
        validate_edit_preconditions(document, node, edit, format_label="JPEG")

        replacement_slot = _encode_replacement_slot(owner, value, limits=limits)
        span = (owner.value_offset, owner.value_offset + owner.value_length)
        for other_start, other_end in seen_spans:
            if span[0] < other_end and other_start < span[1]:
                raise UnsupportedEditError(
                    "JPEG transaction target allocations overlap.",
                    details={"reason": "jpeg.exif.value_overlap"},
                )
        seen_spans.append(span)
        prepared.append(
            _PreparedEdit(
                node=node,
                owner=owner,
                key=key,
                old_value=old_value,
                value=value,
                replacement_slot=replacement_slot,
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
            "JPEG H14 candidate changed byte length before verification.",
            details={"reason": "jpeg.exif.candidate_length_drift"},
        )
    return bytes(candidate)


def patch_jpeg(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation] = (),
    limits: JpegLimits | None = None,
) -> WriterResult:
    validate_document(document)
    requested_limits = limits or JpegLimits()
    active_limits = _intersect_limits(requested_limits, _read_time_limits(document))
    source_bytes = _read_source_bytes(source_stream)
    _validate_source_authority(document, source_bytes)
    fresh = _fresh_parse(source_bytes, active_limits)
    edit_list = tuple(edits)
    prepared = _prepare_edits(document, fresh, edit_list, active_limits)
    candidate = _construct_candidate(source_bytes, prepared)

    if prepared:
        requested_values = {item.key: item.value for item in prepared}
        authorized_spans = {item.key: item.span for item in prepared}
        verify_jpeg_candidate(
            source_bytes,
            candidate,
            requested_values=requested_values,
            authorized_spans=authorized_spans,
            limits=active_limits,
        )

    exact = candidate == source_bytes
    if exact:
        fidelity = FidelityReport(
            claimed_tier="exact-preserve",
            evidence=(
                FidelityEvidence(
                    check_code="jpeg.byte_identity",
                    status=FidelityStatus.PASSED,
                    description="JPEG patch preserved source bytes exactly.",
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
                    check_code="jpeg.exif.semantic_readback",
                    status=FidelityStatus.PASSED,
                    description="Requested JPEG Exif text values passed strict semantic re-read.",
                    expected={item.owner.tag_name: item.value for item in prepared},
                    actual={item.owner.tag_name: item.value for item in prepared},
                    affected_node_ids=tuple(item.node.node_id for item in prepared),
                ),
                FidelityEvidence(
                    check_code="jpeg.exif.outside_slot_identity",
                    status=FidelityStatus.PASSED,
                    description="Every byte outside authorized Exif value slots remained exact.",
                    expected="exact",
                    actual="exact",
                    affected_node_ids=tuple(item.node.node_id for item in prepared),
                ),
            ),
        )

    written = output.write(candidate)
    return WriterResult(
        format="jpeg",
        mode="patch",
        bytes_written=len(candidate) if written is None else written,
        fidelity=fidelity,
        metadata={
            "touched_nodes": tuple(item.node.node_id for item in prepared),
            "touched_owner_keys": tuple(item.key for item in prepared),
            "touched_value_spans": tuple(item.span for item in prepared),
        },
    )


class JpegPatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        source_format = document.source.format if document.source is not None else None
        if source_format != "jpeg":
            return False
        extension = (target.extension or "").lower()
        return target.format.lower() in {"jpeg", "jpg"} or extension in {
            ".jpg",
            ".jpeg",
        }

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
            raise TypeError("JpegPatchWriter.write requires source_stream= and edits=")
        if kwargs:
            raise TypeError(f"unexpected JPEG writer options: {sorted(kwargs)}")
        return patch_jpeg(
            document,
            source_stream,
            output,
            edits=tuple(edits),
            limits=limits,
        )
