from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..._errors import RoundTripVerificationError
from .biff import parse_xls
from .limits import XlsLimits
from .model import (
    CfbPhysicalRange,
    CfbStream,
    ParsedXls,
    XlsFormatError,
    XlsNumberOwner,
)

_NUMBER = 0x0203


def _parse_for_verification(
    data: bytes,
    limits: XlsLimits,
    *,
    label: str,
) -> ParsedXls:
    try:
        return parse_xls(data, limits=limits)
    except XlsFormatError as exc:
        raise RoundTripVerificationError(
            f"XLS {label} failed strict H17 re-read.",
            details={"reason": f"xls_{label}_reread_failed", "error": str(exc)},
        ) from exc


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


def _range_identity(
    ranges: tuple[CfbPhysicalRange, ...],
) -> tuple[tuple[int, int], ...]:
    return tuple((item.start, item.length) for item in ranges)


def _normalize_ranges(
    ranges: Sequence[tuple[int, int]],
    *,
    source_size: int,
) -> tuple[tuple[int, int], ...]:
    normalized = tuple(sorted((int(start), int(end)) for start, end in ranges))
    previous_end = -1
    for start, end in normalized:
        if start < 0 or end <= start or end > source_size:
            raise RoundTripVerificationError(
                "XLS authorized range is outside candidate bounds.",
                details={"reason": "xls_authorized_range_invalid"},
            )
        if start < previous_end:
            raise RoundTripVerificationError(
                "XLS authorized ranges overlap.",
                details={"reason": "xls_authorized_range_overlap"},
            )
        previous_end = end
    return normalized


def _owner_map(parsed: ParsedXls) -> dict[tuple[str, int, int], XlsNumberOwner]:
    result: dict[tuple[str, int, int], XlsNumberOwner] = {}
    for sheet in parsed.sheets:
        for owner in sheet.number_owners:
            key = (sheet.name, owner.row, owner.column)
            if key in result:
                raise RoundTripVerificationError(
                    "XLS NUMBER owner topology is ambiguous.",
                    details={"reason": "xls_number_owner_ambiguous"},
                )
            result[key] = owner
    return result


def _verify_cfb(source: ParsedXls, candidate: ParsedXls) -> None:
    if source.cfb.header != candidate.cfb.header:
        raise RoundTripVerificationError(
            "XLS CFB header changed unexpectedly.",
            details={"reason": "xls_cfb_header_drift"},
        )
    if (
        source.cfb.fat_sector_ids != candidate.cfb.fat_sector_ids
        or source.cfb.difat_sector_ids != candidate.cfb.difat_sector_ids
        or source.cfb.directory_chain != candidate.cfb.directory_chain
        or source.cfb.minifat_chain != candidate.cfb.minifat_chain
        or source.cfb.root_chain != candidate.cfb.root_chain
    ):
        raise RoundTripVerificationError(
            "XLS CFB allocation topology changed unexpectedly.",
            details={"reason": "xls_cfb_topology_drift"},
        )
    if source.cfb.directory_entries != candidate.cfb.directory_entries:
        raise RoundTripVerificationError(
            "XLS CFB directory topology changed unexpectedly.",
            details={"reason": "xls_cfb_directory_drift"},
        )

    source_streams = {
        (stream.parent_id, stream.name, stream.directory_id): stream
        for stream in source.cfb.streams
    }
    candidate_streams = {
        (stream.parent_id, stream.name, stream.directory_id): stream
        for stream in candidate.cfb.streams
    }
    if set(source_streams) != set(candidate_streams):
        raise RoundTripVerificationError(
            "XLS CFB stream inventory changed unexpectedly.",
            details={"reason": "xls_stream_inventory_drift"},
        )

    workbook_key = (
        source.workbook_stream.parent_id,
        source.workbook_stream.name,
        source.workbook_stream.directory_id,
    )
    for key, source_stream in source_streams.items():
        candidate_stream = candidate_streams[key]
        if _stream_identity(source_stream) != _stream_identity(candidate_stream):
            raise RoundTripVerificationError(
                "XLS CFB stream allocation changed unexpectedly.",
                details={"reason": "xls_stream_topology_drift", "stream": key[1]},
            )
        if (
            key != workbook_key
            and source_stream.logical_bytes != candidate_stream.logical_bytes
        ):
            raise RoundTripVerificationError(
                "XLS non-Workbook stream bytes changed unexpectedly.",
                details={"reason": "xls_non_workbook_stream_drift", "stream": key[1]},
            )


def _verify_biff_topology(source: ParsedXls, candidate: ParsedXls) -> None:
    if source.biff_topology_sha256 != candidate.biff_topology_sha256:
        raise RoundTripVerificationError(
            "XLS BIFF record topology changed unexpectedly.",
            details={"reason": "xls_biff_topology_drift"},
        )
    if source.blockers != candidate.blockers:
        raise RoundTripVerificationError(
            "XLS candidate authority classification changed unexpectedly.",
            details={"reason": "xls_authority_drift"},
        )
    if len(source.records) != len(candidate.records):
        raise RoundTripVerificationError(
            "XLS BIFF record count changed unexpectedly.",
            details={"reason": "xls_biff_record_count_drift"},
        )
    for left, right in zip(source.records, candidate.records):
        identity_left = (
            left.index,
            left.record_type,
            left.header_offset,
            left.payload_offset,
            left.payload_size,
            left.end_offset,
        )
        identity_right = (
            right.index,
            right.record_type,
            right.header_offset,
            right.payload_offset,
            right.payload_size,
            right.end_offset,
        )
        if identity_left != identity_right:
            raise RoundTripVerificationError(
                "XLS BIFF record identity changed unexpectedly.",
                details={"reason": "xls_biff_record_identity_drift"},
            )
        if left.record_type != _NUMBER and left.raw != right.raw:
            raise RoundTripVerificationError(
                "XLS non-NUMBER BIFF record changed unexpectedly.",
                details={
                    "reason": "xls_non_number_record_drift",
                    "record_index": left.index,
                },
            )

    source_sheets = tuple(
        (
            sheet.name,
            sheet.hidden_state,
            sheet.sheet_type,
            sheet.bof_offset,
            sheet.eof_offset,
            sheet.is_dialog,
        )
        for sheet in source.sheets
    )
    candidate_sheets = tuple(
        (
            sheet.name,
            sheet.hidden_state,
            sheet.sheet_type,
            sheet.bof_offset,
            sheet.eof_offset,
            sheet.is_dialog,
        )
        for sheet in candidate.sheets
    )
    if source_sheets != candidate_sheets:
        raise RoundTripVerificationError(
            "XLS sheet identity/topology changed unexpectedly.",
            details={"reason": "xls_sheet_topology_drift"},
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
                "XLS bytes changed outside authorized NUMBER value ranges.",
                details={"reason": "xls_unrequested_byte_drift"},
            )
        cursor = end
    if source_bytes[cursor:] != candidate_bytes[cursor:]:
        raise RoundTripVerificationError(
            "XLS bytes changed outside authorized NUMBER value ranges.",
            details={"reason": "xls_unrequested_byte_drift"},
        )


def verify_xls_candidate(
    source_bytes: bytes,
    candidate_bytes: bytes,
    *,
    requested_values: Mapping[tuple[str, int, int], float],
    authorized_ranges: Sequence[tuple[int, int]],
    limits: XlsLimits | None = None,
) -> None:
    if len(candidate_bytes) != len(source_bytes):
        raise RoundTripVerificationError(
            "XLS candidate byte length changed unexpectedly.",
            details={
                "reason": "xls_candidate_length_drift",
                "expected": len(source_bytes),
                "actual": len(candidate_bytes),
            },
        )

    active_limits = limits or XlsLimits()
    source = _parse_for_verification(source_bytes, active_limits, label="source")
    candidate = _parse_for_verification(
        candidate_bytes,
        active_limits,
        label="candidate",
    )
    _verify_cfb(source, candidate)
    _verify_biff_topology(source, candidate)

    source_owners = _owner_map(source)
    candidate_owners = _owner_map(candidate)
    if set(source_owners) != set(candidate_owners):
        raise RoundTripVerificationError(
            "XLS NUMBER coordinate ownership changed unexpectedly.",
            details={"reason": "xls_number_owner_topology_drift"},
        )

    requested_keys = set(requested_values)
    if not requested_keys or not requested_keys <= set(source_owners):
        raise RoundTripVerificationError(
            "XLS requested NUMBER targets do not match source authority.",
            details={"reason": "xls_requested_target_invalid"},
        )

    expected_ranges: list[tuple[int, int]] = []
    for key in sorted(requested_keys):
        owner = source_owners[key]
        expected_ranges.extend(
            (item.start, item.end) for item in owner.value_physical_ranges
        )
    normalized = _normalize_ranges(authorized_ranges, source_size=len(source_bytes))
    expected = _normalize_ranges(expected_ranges, source_size=len(source_bytes))
    if normalized != expected:
        raise RoundTripVerificationError(
            "XLS authorized ranges do not match requested native NUMBER slots.",
            details={
                "reason": "xls_number_range_mismatch",
                "expected": expected,
                "actual": normalized,
            },
        )

    for key, source_owner in source_owners.items():
        candidate_owner = candidate_owners[key]
        source_identity = (
            source_owner.row,
            source_owner.column,
            source_owner.xf_index,
            source_owner.record.index,
            source_owner.record.header_offset,
            source_owner.record.payload_size,
            source_owner.value_logical_offset,
            _range_identity(source_owner.value_physical_ranges),
        )
        candidate_identity = (
            candidate_owner.row,
            candidate_owner.column,
            candidate_owner.xf_index,
            candidate_owner.record.index,
            candidate_owner.record.header_offset,
            candidate_owner.record.payload_size,
            candidate_owner.value_logical_offset,
            _range_identity(candidate_owner.value_physical_ranges),
        )
        if source_identity != candidate_identity:
            raise RoundTripVerificationError(
                "XLS NUMBER native owner identity changed unexpectedly.",
                details={"reason": "xls_number_owner_drift", "target": key},
            )
        if key in requested_keys:
            expected_value = float(requested_values[key])
            if candidate_owner.value != expected_value:
                raise RoundTripVerificationError(
                    "XLS requested NUMBER value failed semantic readback.",
                    details={
                        "reason": "xls_requested_value_mismatch",
                        "target": key,
                        "expected": expected_value,
                        "actual": candidate_owner.value,
                    },
                )
        elif source_owner.record.raw != candidate_owner.record.raw:
            raise RoundTripVerificationError(
                "XLS unrequested NUMBER record changed unexpectedly.",
                details={"reason": "xls_unrequested_number_drift", "target": key},
            )

    _verify_exact_outside_ranges(
        source_bytes,
        candidate_bytes,
        normalized,
    )
