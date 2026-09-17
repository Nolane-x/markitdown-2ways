from __future__ import annotations

from collections.abc import Mapping

from ..._errors import RoundTripVerificationError
from .limits import JpegLimits
from .model import JpegExifTextOwner, ParsedJpeg
from .parser import JpegFormatError, parse_jpeg

OwnerKey = tuple[int, int, int]


def _owner_map(parsed: ParsedJpeg) -> dict[OwnerKey, JpegExifTextOwner]:
    result: dict[OwnerKey, JpegExifTextOwner] = {}
    for owner in parsed.text_owners:
        key = (owner.marker_index, owner.entry_offset, owner.tag_id)
        if key in result:
            raise RoundTripVerificationError(
                "JPEG candidate owner identity is ambiguous during verification.",
                details={"reason": "jpeg.exif.owner_identity_ambiguous", "key": key},
            )
        result[key] = owner
    return result


def _validate_spans(
    source_length: int,
    spans: Mapping[OwnerKey, tuple[int, int]],
) -> tuple[tuple[int, int], ...]:
    ordered = sorted(spans.values())
    previous_end = 0
    for start, end in ordered:
        if start < 0 or end <= start or end > source_length:
            raise RoundTripVerificationError(
                "JPEG verification received an invalid authorized byte span.",
                details={
                    "reason": "jpeg.exif.invalid_authorized_span",
                    "start": start,
                    "end": end,
                },
            )
        if start < previous_end:
            raise RoundTripVerificationError(
                "JPEG verification received overlapping authorized byte spans.",
                details={"reason": "jpeg.exif.authorized_span_overlap"},
            )
        previous_end = end
    return tuple(ordered)


def _verify_outside_spans_exact(
    source_bytes: bytes,
    candidate_bytes: bytes,
    spans: tuple[tuple[int, int], ...],
) -> None:
    cursor = 0
    for start, end in spans:
        if source_bytes[cursor:start] != candidate_bytes[cursor:start]:
            raise RoundTripVerificationError(
                "JPEG bytes outside authorized Exif value slots changed unexpectedly.",
                details={
                    "reason": "jpeg.exif.unauthorized_byte_drift",
                    "range_start": cursor,
                    "range_end": start,
                },
            )
        cursor = end
    if source_bytes[cursor:] != candidate_bytes[cursor:]:
        raise RoundTripVerificationError(
            "JPEG bytes outside authorized Exif value slots changed unexpectedly.",
            details={
                "reason": "jpeg.exif.unauthorized_byte_drift",
                "range_start": cursor,
                "range_end": len(source_bytes),
            },
        )


def verify_jpeg_candidate(
    source_bytes: bytes,
    candidate_bytes: bytes,
    *,
    requested_values: Mapping[OwnerKey, str],
    authorized_spans: Mapping[OwnerKey, tuple[int, int]],
    limits: JpegLimits | None = None,
) -> None:
    active_limits = limits or JpegLimits()
    if len(source_bytes) != len(candidate_bytes):
        raise RoundTripVerificationError(
            "JPEG candidate byte length changed unexpectedly.",
            details={
                "reason": "jpeg.exif.candidate_length_drift",
                "expected": len(source_bytes),
                "actual": len(candidate_bytes),
            },
        )
    if set(requested_values) != set(authorized_spans):
        raise RoundTripVerificationError(
            "JPEG verification request/value span identities disagree.",
            details={"reason": "jpeg.exif.verification_identity_mismatch"},
        )

    try:
        source = parse_jpeg(source_bytes, limits=active_limits)
        candidate = parse_jpeg(candidate_bytes, limits=active_limits)
    except JpegFormatError as exc:
        raise RoundTripVerificationError(
            "JPEG candidate failed strict re-read verification.",
            details={"reason": "jpeg.structure.invalid", "error": str(exc)},
        ) from exc

    source_topology = tuple(
        (
            marker.index,
            marker.code,
            marker.start,
            marker.end,
            marker.payload_start,
            marker.payload_end,
        )
        for marker in source.markers
    )
    candidate_topology = tuple(
        (
            marker.index,
            marker.code,
            marker.start,
            marker.end,
            marker.payload_start,
            marker.payload_end,
        )
        for marker in candidate.markers
    )
    if candidate_topology != source_topology:
        raise RoundTripVerificationError(
            "JPEG marker/segment topology changed unexpectedly.",
            details={
                "reason": "jpeg.structure.topology_drift",
                "expected": source_topology,
                "actual": candidate_topology,
            },
        )
    if candidate.blockers != source.blockers:
        raise RoundTripVerificationError(
            "JPEG candidate metadata-authority state changed unexpectedly.",
            details={
                "reason": "jpeg.exif.authority_drift",
                "expected": source.blockers,
                "actual": candidate.blockers,
            },
        )

    spans = _validate_spans(len(source_bytes), authorized_spans)
    _verify_outside_spans_exact(source_bytes, candidate_bytes, spans)

    source_owners = _owner_map(source)
    candidate_owners = _owner_map(candidate)
    immutable_fields = (
        "tag_id",
        "tag_name",
        "marker_index",
        "byte_order",
        "ifd_path",
        "entry_offset",
        "tiff_type",
        "count",
        "value_offset",
        "value_length",
        "inline_value",
    )

    for key, expected_value in requested_values.items():
        source_owner = source_owners.get(key)
        candidate_owner = candidate_owners.get(key)
        if source_owner is None or candidate_owner is None:
            raise RoundTripVerificationError(
                "JPEG requested Exif owner disappeared during strict re-read.",
                details={"reason": "jpeg.exif.requested_owner_missing", "key": key},
            )
        expected_span = (
            source_owner.value_offset,
            source_owner.value_offset + source_owner.value_length,
        )
        if authorized_spans[key] != expected_span:
            raise RoundTripVerificationError(
                "JPEG authorized value slot no longer matches the source owner.",
                details={
                    "reason": "jpeg.exif.authorized_span_mismatch",
                    "key": key,
                    "expected": expected_span,
                    "actual": authorized_spans[key],
                },
            )
        for field_name in immutable_fields:
            source_value = getattr(source_owner, field_name)
            candidate_value = getattr(candidate_owner, field_name)
            if candidate_value != source_value:
                raise RoundTripVerificationError(
                    "JPEG requested Exif owner immutable topology changed unexpectedly.",
                    details={
                        "reason": "jpeg.exif.requested_owner_topology_drift",
                        "key": key,
                        "field": field_name,
                        "expected": source_value,
                        "actual": candidate_value,
                    },
                )
        if candidate_owner.value != expected_value:
            raise RoundTripVerificationError(
                "JPEG requested Exif text failed semantic readback.",
                details={
                    "reason": "jpeg.exif.requested_value_mismatch",
                    "key": key,
                    "expected": expected_value,
                    "actual": candidate_owner.value,
                },
            )
