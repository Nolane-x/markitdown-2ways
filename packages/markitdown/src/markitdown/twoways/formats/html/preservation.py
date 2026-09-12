from __future__ import annotations

import codecs

from ..._errors import RoundTripVerificationError
from ..text.model import TextRepresentation


def _encoded_payload_and_boundaries(
    text: str, encoding: str
) -> tuple[bytes, tuple[int, ...]]:
    encoder_type = codecs.getincrementalencoder(encoding)
    encoder = encoder_type(errors="strict")
    payload = bytearray()
    boundaries = [0]
    for character in text:
        payload.extend(encoder.encode(character, final=False))
        boundaries.append(len(payload))
    payload.extend(encoder.encode("", final=True))
    boundaries[-1] = len(payload)
    encoded = bytes(payload)
    expected = text.encode(encoding, errors="strict")
    if encoded != expected:
        raise RoundTripVerificationError(
            "Incremental HTML encoding disagrees with strict whole-text encoding.",
            details={
                "reason": "html.incremental_encoding_mismatch",
                "encoding": encoding,
            },
        )
    return encoded, tuple(boundaries)


def verify_untouched_bytes(
    source_bytes: bytes,
    candidate_bytes: bytes,
    source_text: str,
    candidate_text: str,
    representation: TextRepresentation,
    untouched: tuple[tuple[int, int, int, int], ...],
) -> None:
    original_expected, original_bounds = _encoded_payload_and_boundaries(
        source_text, representation.encoding
    )
    candidate_expected, candidate_bounds = _encoded_payload_and_boundaries(
        candidate_text, representation.encoding
    )
    original_bom_length = len(source_bytes) - len(original_expected)
    candidate_bom_length = len(candidate_bytes) - len(candidate_expected)
    if original_bom_length < 0 or candidate_bom_length < 0:
        raise RoundTripVerificationError(
            "HTML encoded payload exceeds its byte stream.",
            details={"reason": "html.invalid_encoded_payload_boundary"},
        )
    if (
        original_bom_length != candidate_bom_length
        or source_bytes[:original_bom_length]
        != candidate_bytes[:candidate_bom_length]
    ):
        raise RoundTripVerificationError(
            "HTML BOM or encoded payload boundary changed unexpectedly.",
            details={"reason": "html.encoding_boundary_mismatch"},
        )

    original_payload = source_bytes[original_bom_length:]
    candidate_payload = candidate_bytes[candidate_bom_length:]
    if original_payload != original_expected:
        raise RoundTripVerificationError(
            "HTML source bytes disagree with the recorded strict encoding.",
            details={"reason": "html.source_encoded_payload_mismatch"},
        )

    for old_start, old_end, new_start, new_end in untouched:
        if not (
            0 <= old_start <= old_end < len(original_bounds)
            and 0 <= new_start <= new_end < len(candidate_bounds)
        ):
            raise RoundTripVerificationError(
                "HTML untouched span boundary evidence is invalid.",
                details={"reason": "html.untouched_span_boundary"},
            )
        old_bytes = original_payload[
            original_bounds[old_start] : original_bounds[old_end]
        ]
        new_bytes = candidate_payload[
            candidate_bounds[new_start] : candidate_bounds[new_end]
        ]
        if old_bytes != new_bytes:
            raise RoundTripVerificationError(
                "HTML bytes outside authorized target spans changed.",
                details={
                    "reason": "html.untouched_bytes_changed",
                    "source_span": (old_start, old_end),
                    "candidate_span": (new_start, new_end),
                },
            )

    if candidate_payload != candidate_expected:
        raise RoundTripVerificationError(
            "HTML candidate bytes disagree with strict candidate encoding.",
            details={"reason": "html.candidate_encoded_payload_mismatch"},
        )
