from __future__ import annotations

from collections.abc import Mapping

from ..._errors import RoundTripVerificationError
from .limits import Mp3Limits
from .parser import Mp3FormatError, parse_mp3


def _parse_for_verification(data: bytes, limits: Mp3Limits, *, label: str):
    try:
        return parse_mp3(data, limits=limits)
    except Mp3FormatError as exc:
        raise RoundTripVerificationError(
            f"MP3 {label} failed strict re-read verification.",
            details={"reason": "mp3_candidate_parse_failure", "error": str(exc)},
        ) from exc


def _validate_requested_ranges(
    source,
    requested_values: Mapping[str, str],
    requested_ranges: Mapping[str, tuple[int, int]],
) -> tuple[tuple[int, int], ...]:
    if set(requested_values) != set(requested_ranges):
        raise RoundTripVerificationError(
            "MP3 verification values and authorized ranges disagree.",
            details={"reason": "mp3_requested_range_mismatch"},
        )

    spans: list[tuple[int, int]] = []
    for field in requested_values:
        try:
            owner = source.owner(field)
        except KeyError as exc:
            raise RoundTripVerificationError(
                "MP3 verification references a missing ID3v1 field.",
                details={"reason": "mp3_requested_owner_missing", "field": field},
            ) from exc
        expected = (owner.slot_start, owner.slot_end)
        actual = requested_ranges[field]
        if actual != expected:
            raise RoundTripVerificationError(
                "MP3 authorized range does not match the native ID3v1 slot.",
                details={
                    "reason": "mp3_requested_range_mismatch",
                    "field": field,
                    "expected": expected,
                    "actual": actual,
                },
            )
        start, end = actual
        if start < 0 or end <= start or end > source.source_size:
            raise RoundTripVerificationError(
                "MP3 authorized slot range is out of bounds.",
                details={"reason": "mp3_requested_range_invalid", "field": field},
            )
        spans.append(actual)

    ordered = tuple(sorted(spans))
    for previous, current in zip(ordered, ordered[1:]):
        if current[0] < previous[1]:
            raise RoundTripVerificationError(
                "MP3 authorized slot ranges overlap unexpectedly.",
                details={"reason": "mp3_requested_range_overlap"},
            )
    return ordered


def _verify_exact_outside_ranges(
    source_bytes: bytes,
    candidate_bytes: bytes,
    spans: tuple[tuple[int, int], ...],
) -> None:
    cursor = 0
    for start, end in spans:
        if source_bytes[cursor:start] != candidate_bytes[cursor:start]:
            raise RoundTripVerificationError(
                "MP3 bytes changed outside authorized ID3v1 slots.",
                details={"reason": "mp3_unrequested_byte_drift"},
            )
        cursor = end
    if source_bytes[cursor:] != candidate_bytes[cursor:]:
        raise RoundTripVerificationError(
            "MP3 bytes changed outside authorized ID3v1 slots.",
            details={"reason": "mp3_unrequested_byte_drift"},
        )


def verify_mp3_candidate(
    source_bytes: bytes,
    candidate_bytes: bytes,
    *,
    requested_values: Mapping[str, str],
    requested_ranges: Mapping[str, tuple[int, int]],
    limits: Mp3Limits | None = None,
) -> None:
    if len(candidate_bytes) != len(source_bytes):
        raise RoundTripVerificationError(
            "MP3 candidate byte length changed unexpectedly.",
            details={
                "reason": "mp3_candidate_length_drift",
                "expected": len(source_bytes),
                "actual": len(candidate_bytes),
            },
        )

    active_limits = limits or Mp3Limits()
    source = _parse_for_verification(source_bytes, active_limits, label="source")
    candidate = _parse_for_verification(
        candidate_bytes, active_limits, label="candidate"
    )
    spans = _validate_requested_ranges(source, requested_values, requested_ranges)

    if (
        source.audio_start != candidate.audio_start
        or source.audio_end != candidate.audio_end
        or source.audio_frames != candidate.audio_frames
    ):
        raise RoundTripVerificationError(
            "MP3 MPEG audio topology or bytes changed unexpectedly.",
            details={"reason": "mp3_audio_topology_drift"},
        )
    if source.terminal_metadata != candidate.terminal_metadata:
        raise RoundTripVerificationError(
            "MP3 terminal metadata outside ID3v1 changed unexpectedly.",
            details={"reason": "mp3_terminal_metadata_drift"},
        )
    if (
        source.id3v1_start != candidate.id3v1_start
        or source.id3v1_end != candidate.id3v1_end
        or source.id3v1_version != candidate.id3v1_version
        or source.track != candidate.track
    ):
        raise RoundTripVerificationError(
            "MP3 ID3v1 immutable topology changed unexpectedly.",
            details={"reason": "mp3_id3v1_topology_drift"},
        )
    if (
        source.audio_authoritative != candidate.audio_authoritative
        or source.blockers != candidate.blockers
    ):
        raise RoundTripVerificationError(
            "MP3 candidate authority classification changed unexpectedly.",
            details={"reason": "mp3_authority_drift"},
        )

    requested_fields = set(requested_values)
    for source_owner in source.owners:
        try:
            candidate_owner = candidate.owner(source_owner.field)
        except KeyError as exc:
            raise RoundTripVerificationError(
                "MP3 ID3v1 owner disappeared during candidate re-read.",
                details={
                    "reason": "mp3_requested_owner_missing",
                    "field": source_owner.field,
                },
            ) from exc
        if (
            source_owner.field != candidate_owner.field
            or source_owner.slot_start != candidate_owner.slot_start
            or source_owner.slot_end != candidate_owner.slot_end
            or source_owner.slot_length != candidate_owner.slot_length
        ):
            raise RoundTripVerificationError(
                "MP3 ID3v1 slot identity changed unexpectedly.",
                details={
                    "reason": "mp3_id3v1_slot_drift",
                    "field": source_owner.field,
                },
            )
        if source_owner.field in requested_fields:
            expected_value = requested_values[source_owner.field]
            if candidate_owner.value != expected_value:
                raise RoundTripVerificationError(
                    "MP3 requested ID3v1 value failed semantic readback.",
                    details={
                        "reason": "mp3_requested_value_mismatch",
                        "field": source_owner.field,
                        "expected": expected_value,
                        "actual": candidate_owner.value,
                    },
                )
            if not candidate_owner.canonical_padding:
                raise RoundTripVerificationError(
                    "MP3 requested ID3v1 slot lost canonical padding.",
                    details={
                        "reason": "mp3_requested_padding_drift",
                        "field": source_owner.field,
                    },
                )
        elif candidate_owner != source_owner:
            raise RoundTripVerificationError(
                "MP3 unrequested ID3v1 owner changed unexpectedly.",
                details={
                    "reason": "mp3_unrequested_owner_drift",
                    "field": source_owner.field,
                },
            )

    _verify_exact_outside_ranges(source_bytes, candidate_bytes, spans)
