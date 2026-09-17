from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.mp3 import patch_mp3, read_mp3_ir
from markitdown.twoways.formats.mp3.verification import verify_mp3_candidate
from markitdown.twoways.ir.edits import EditOperation

from ._mp3_fixtures import make_mp3


def _node(document, field: str = "Title"):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "mp3-id3v1-text"
        and node.metadata.get("mp3.id3v1_field") == field
    )


def _edited_candidate(source: bytes) -> tuple[bytes, tuple[int, int]]:
    document = read_mp3_ir(BytesIO(source), filename="song.mp3")
    node = _node(document)
    output = BytesIO()
    edit = EditOperation(
        operation_id="title",
        type="update_mp3_id3v1_text",
        target_node_id=node.node_id,
        payload={"field": "Title", "old_value": node.payload.text, "value": "Beta"},
    )
    patch_mp3(document, BytesIO(source), output, edits=(edit,))
    return output.getvalue(), (
        node.metadata["mp3.slot_start"],
        node.metadata["mp3.slot_end"],
    )


def test_verifier_accepts_exact_authorized_slot_change() -> None:
    source = make_mp3()
    candidate, span = _edited_candidate(source)

    verify_mp3_candidate(
        source,
        candidate,
        requested_values={"Title": "Beta"},
        requested_ranges={"Title": span},
    )


def test_verifier_rejects_drift_outside_authorized_slot() -> None:
    source = make_mp3()
    candidate, span = _edited_candidate(source)
    drifted = bytearray(candidate)
    drifted[10] ^= 0x01

    with pytest.raises(RoundTripVerificationError, match="outside|audio|drift"):
        verify_mp3_candidate(
            source,
            bytes(drifted),
            requested_values={"Title": "Beta"},
            requested_ranges={"Title": span},
        )


def test_verifier_rejects_candidate_length_drift() -> None:
    source = make_mp3()
    candidate, span = _edited_candidate(source)

    with pytest.raises(RoundTripVerificationError, match="length|size"):
        verify_mp3_candidate(
            source,
            candidate + b"\x00",
            requested_values={"Title": "Beta"},
            requested_ranges={"Title": span},
        )


def test_verifier_rejects_wrong_requested_semantic_value() -> None:
    source = make_mp3()
    candidate, span = _edited_candidate(source)

    with pytest.raises(RoundTripVerificationError, match="semantic|value"):
        verify_mp3_candidate(
            source,
            candidate,
            requested_values={"Title": "Gamma"},
            requested_ranges={"Title": span},
        )


def test_verifier_rejects_wrong_authorized_range() -> None:
    source = make_mp3()
    candidate, span = _edited_candidate(source)
    shifted = (span[0] + 1, span[1] + 1)

    with pytest.raises(RoundTripVerificationError, match="range|slot|authorized"):
        verify_mp3_candidate(
            source,
            candidate,
            requested_values={"Title": "Beta"},
            requested_ranges={"Title": shifted},
        )
