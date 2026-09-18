from __future__ import annotations

from collections.abc import Sequence

from ..._errors import RoundTripVerificationError
from .limits import MsgLimits
from .model import CfbPhysicalRange, CfbStream, MsgFormatError, ParsedMsg
from .parser import parse_msg


def _parse_for_verification(data: bytes, limits: MsgLimits, *, label: str) -> ParsedMsg:
    try:
        return parse_msg(data, limits=limits)
    except MsgFormatError as exc:
        raise RoundTripVerificationError(
            f"MSG {label} failed strict re-read verification.",
            details={"reason": "msg_candidate_parse_failure", "error": str(exc)},
        ) from exc


def _owner_ranges(parsed: ParsedMsg) -> tuple[tuple[int, int], ...]:
    owner = parsed.subject_owner
    if owner is None:
        raise RoundTripVerificationError(
            "MSG source no longer has a readable Unicode Subject owner.",
            details={"reason": "msg.subject.missing"},
        )
    return tuple(
        (physical.start, physical.end) for physical in owner.stream.physical_ranges
    )


def _normalize_ranges(
    ranges: Sequence[tuple[int, int]],
    *,
    source_size: int,
) -> tuple[tuple[int, int], ...]:
    normalized: list[tuple[int, int]] = []
    for item in ranges:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or isinstance(item[0], bool)
            or isinstance(item[1], bool)
            or not isinstance(item[0], int)
            or not isinstance(item[1], int)
        ):
            raise RoundTripVerificationError(
                "MSG authorized subject range is malformed.",
                details={"reason": "msg_subject_range_invalid"},
            )
        start, end = item
        if start < 0 or end <= start or end > source_size:
            raise RoundTripVerificationError(
                "MSG authorized subject range is outside source bounds.",
                details={"reason": "msg_subject_range_invalid"},
            )
        normalized.append((start, end))

    ordered = tuple(sorted(normalized))
    for previous, current in zip(ordered, ordered[1:]):
        if current[0] < previous[1]:
            raise RoundTripVerificationError(
                "MSG authorized subject ranges overlap.",
                details={"reason": "msg_subject_range_overlap"},
            )
    return ordered


def _stream_identity(stream: CfbStream) -> tuple[object, ...]:
    return (
        stream.directory_id,
        stream.parent_id,
        stream.name,
        stream.chain_kind,
        stream.chain,
        stream.stream_size,
        tuple((item.start, item.length) for item in stream.physical_ranges),
        stream.directory_entry_sha256,
    )


def _physical_range_identity(
    ranges: tuple[CfbPhysicalRange, ...],
) -> tuple[tuple[int, int], ...]:
    return tuple((item.start, item.length) for item in ranges)


def _verify_cfb_topology(source: ParsedMsg, candidate: ParsedMsg) -> None:
    source_cfb = source.cfb
    candidate_cfb = candidate.cfb
    if source_cfb.header != candidate_cfb.header:
        raise RoundTripVerificationError(
            "MSG CFB header changed unexpectedly.",
            details={"reason": "msg_cfb_header_drift"},
        )
    if (
        source_cfb.fat_sector_ids != candidate_cfb.fat_sector_ids
        or source_cfb.difat_sector_ids != candidate_cfb.difat_sector_ids
        or source_cfb.directory_chain != candidate_cfb.directory_chain
        or source_cfb.minifat_chain != candidate_cfb.minifat_chain
        or source_cfb.root_chain != candidate_cfb.root_chain
    ):
        raise RoundTripVerificationError(
            "MSG CFB FAT/DIFAT/MiniFAT topology changed unexpectedly.",
            details={"reason": "msg_cfb_topology_drift"},
        )
    if source_cfb.directory_entries != candidate_cfb.directory_entries:
        raise RoundTripVerificationError(
            "MSG CFB directory topology changed unexpectedly.",
            details={"reason": "msg_cfb_directory_drift"},
        )

    source_streams = {
        (stream.parent_id, stream.name, stream.directory_id): stream
        for stream in source_cfb.streams
    }
    candidate_streams = {
        (stream.parent_id, stream.name, stream.directory_id): stream
        for stream in candidate_cfb.streams
    }
    if set(source_streams) != set(candidate_streams):
        raise RoundTripVerificationError(
            "MSG stream inventory changed unexpectedly.",
            details={"reason": "msg_stream_inventory_drift"},
        )

    subject_key = None
    if source.subject_owner is not None:
        subject = source.subject_owner.stream
        subject_key = (subject.parent_id, subject.name, subject.directory_id)

    for key, source_stream in source_streams.items():
        candidate_stream = candidate_streams[key]
        if _stream_identity(source_stream) != _stream_identity(candidate_stream):
            raise RoundTripVerificationError(
                "MSG stream allocation/topology changed unexpectedly.",
                details={"reason": "msg_stream_topology_drift", "stream": key[1]},
            )
        if (
            key != subject_key
            and source_stream.logical_bytes != candidate_stream.logical_bytes
        ):
            raise RoundTripVerificationError(
                "MSG non-subject stream bytes changed unexpectedly.",
                details={"reason": "msg_non_subject_stream_drift", "stream": key[1]},
            )


def _verify_msg_property_authority(source: ParsedMsg, candidate: ParsedMsg) -> None:
    if (
        source.properties_stream.logical_bytes
        != candidate.properties_stream.logical_bytes
    ):
        raise RoundTripVerificationError(
            "MSG top-level property stream changed unexpectedly.",
            details={"reason": "msg_property_stream_drift"},
        )
    if source.property_entries != candidate.property_entries:
        raise RoundTripVerificationError(
            "MSG property entry topology changed unexpectedly.",
            details={"reason": "msg_property_entry_drift"},
        )
    if source.store_support_mask != candidate.store_support_mask:
        raise RoundTripVerificationError(
            "MSG Unicode store-support authority changed unexpectedly.",
            details={"reason": "msg_store_support_drift"},
        )
    if source.blockers != candidate.blockers:
        raise RoundTripVerificationError(
            "MSG candidate authority classification changed unexpectedly.",
            details={"reason": "msg_authority_drift"},
        )

    source_owner = source.subject_owner
    candidate_owner = candidate.subject_owner
    if source_owner is None or candidate_owner is None:
        raise RoundTripVerificationError(
            "MSG Unicode Subject owner disappeared during verification.",
            details={"reason": "msg.subject.missing"},
        )
    if (
        source_owner.property_id != candidate_owner.property_id
        or source_owner.property_type != candidate_owner.property_type
        or source_owner.property_tag != candidate_owner.property_tag
        or source_owner.declared_size != candidate_owner.declared_size
        or source_owner.property_entry != candidate_owner.property_entry
        or _stream_identity(source_owner.stream)
        != _stream_identity(candidate_owner.stream)
        or _physical_range_identity(source_owner.stream.physical_ranges)
        != _physical_range_identity(candidate_owner.stream.physical_ranges)
    ):
        raise RoundTripVerificationError(
            "MSG Subject native owner identity changed unexpectedly.",
            details={"reason": "msg_subject_owner_drift"},
        )


def _verify_exact_outside_ranges(
    source_bytes: bytes,
    candidate_bytes: bytes,
    ranges: tuple[tuple[int, int], ...],
) -> None:
    cursor = 0
    for start, end in ranges:
        if source_bytes[cursor:start] != candidate_bytes[cursor:start]:
            raise RoundTripVerificationError(
                "MSG bytes changed outside authorized Subject ranges.",
                details={"reason": "msg_unrequested_byte_drift"},
            )
        cursor = end
    if source_bytes[cursor:] != candidate_bytes[cursor:]:
        raise RoundTripVerificationError(
            "MSG bytes changed outside authorized Subject ranges.",
            details={"reason": "msg_unrequested_byte_drift"},
        )


def verify_msg_candidate(
    source_bytes: bytes,
    candidate_bytes: bytes,
    *,
    requested_subject: str,
    authorized_ranges: Sequence[tuple[int, int]],
    limits: MsgLimits | None = None,
) -> None:
    if len(candidate_bytes) != len(source_bytes):
        raise RoundTripVerificationError(
            "MSG candidate byte length changed unexpectedly.",
            details={
                "reason": "msg_candidate_length_drift",
                "expected": len(source_bytes),
                "actual": len(candidate_bytes),
            },
        )
    if not isinstance(requested_subject, str):
        raise RoundTripVerificationError(
            "MSG requested Subject value is invalid.",
            details={"reason": "msg_requested_subject_invalid"},
        )

    active_limits = limits or MsgLimits()
    source = _parse_for_verification(source_bytes, active_limits, label="source")
    candidate = _parse_for_verification(
        candidate_bytes, active_limits, label="candidate"
    )
    expected_ranges = _owner_ranges(source)
    ranges = _normalize_ranges(authorized_ranges, source_size=len(source_bytes))
    if ranges != expected_ranges:
        raise RoundTripVerificationError(
            "MSG authorized ranges do not match the native Subject stream.",
            details={
                "reason": "msg_subject_range_mismatch",
                "expected": expected_ranges,
                "actual": ranges,
            },
        )

    _verify_cfb_topology(source, candidate)
    _verify_msg_property_authority(source, candidate)

    assert candidate.subject_owner is not None
    if candidate.subject_owner.value != requested_subject:
        raise RoundTripVerificationError(
            "MSG requested Subject failed semantic readback.",
            details={
                "reason": "msg_requested_subject_mismatch",
                "expected": requested_subject,
                "actual": candidate.subject_owner.value,
            },
        )

    _verify_exact_outside_ranges(source_bytes, candidate_bytes, ranges)
