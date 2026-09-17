from __future__ import annotations

from collections.abc import Mapping

from ..._errors import RoundTripVerificationError
from .limits import PngLimits
from .parser import PngFormatError, parse_png


def verify_png_candidate(
    source_bytes: bytes,
    candidate_bytes: bytes,
    *,
    requested_values: Mapping[int, tuple[str, str]],
    limits: PngLimits | None = None,
) -> None:
    active_limits = limits or PngLimits()
    try:
        source = parse_png(source_bytes, limits=active_limits)
        candidate = parse_png(candidate_bytes, limits=active_limits)
    except PngFormatError as exc:
        raise RoundTripVerificationError(
            "PNG candidate failed strict re-read verification.",
            details={"reason": "png_candidate_parse_failure", "error": str(exc)},
        ) from exc

    source_types = tuple(chunk.chunk_type for chunk in source.chunks)
    candidate_types = tuple(chunk.chunk_type for chunk in candidate.chunks)
    if source_types != candidate_types or len(source.chunks) != len(candidate.chunks):
        raise RoundTripVerificationError(
            "PNG candidate chunk topology changed unexpectedly.",
            details={
                "reason": "png_chunk_topology_drift",
                "expected": source_types,
                "actual": candidate_types,
            },
        )

    requested_indexes = set(requested_values)
    if any(index < 0 or index >= len(source.chunks) for index in requested_indexes):
        raise RoundTripVerificationError(
            "PNG verification request references a missing native chunk.",
            details={"reason": "png_requested_chunk_missing"},
        )

    for source_chunk, candidate_chunk in zip(source.chunks, candidate.chunks):
        index = source_chunk.index
        if index not in requested_indexes:
            if source_chunk.raw != candidate_chunk.raw:
                raise RoundTripVerificationError(
                    "PNG unrequested chunk bytes changed unexpectedly.",
                    details={
                        "reason": "png_unrequested_chunk_drift",
                        "chunk_index": index,
                        "chunk_type": source_chunk.chunk_type,
                    },
                )
            continue

        expected_keyword, expected_value = requested_values[index]
        if source_chunk.chunk_type != "tEXt" or candidate_chunk.chunk_type != "tEXt":
            raise RoundTripVerificationError(
                "PNG requested owner is no longer a tEXt chunk.",
                details={
                    "reason": "png_requested_owner_type_drift",
                    "chunk_index": index,
                },
            )
        source_owner = source.text_owner(index)
        candidate_owner = candidate.text_owner(index)
        if source_owner is None or candidate_owner is None:
            raise RoundTripVerificationError(
                "PNG requested text owner disappeared during re-read.",
                details={
                    "reason": "png_requested_owner_missing",
                    "chunk_index": index,
                },
            )
        if (
            source_owner.keyword != expected_keyword
            or candidate_owner.keyword != expected_keyword
        ):
            raise RoundTripVerificationError(
                "PNG requested metadata keyword changed unexpectedly.",
                details={
                    "reason": "png_requested_keyword_drift",
                    "chunk_index": index,
                    "expected": expected_keyword,
                    "source": source_owner.keyword,
                    "actual": candidate_owner.keyword,
                },
            )
        if candidate_owner.value != expected_value:
            raise RoundTripVerificationError(
                "PNG requested metadata value failed semantic readback.",
                details={
                    "reason": "png_requested_value_mismatch",
                    "chunk_index": index,
                    "expected": expected_value,
                    "actual": candidate_owner.value,
                },
            )
