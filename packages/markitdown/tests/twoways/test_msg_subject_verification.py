from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.msg import patch_msg, read_msg_ir
from markitdown.twoways.formats.msg.verification import verify_msg_candidate
from markitdown.twoways.ir.edits import EditOperation

from ._msg_fixtures import make_msg_cfb


def _subject_node(document):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "msg-subject-text"
    )


def _authorized_ranges(node) -> tuple[tuple[int, int], ...]:
    return tuple(
        (item["start"], item["start"] + item["length"])
        for item in node.metadata["msg.subject_physical_ranges"]
    )


def _edited_candidate(source: bytes) -> tuple[bytes, tuple[tuple[int, int], ...]]:
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    node = _subject_node(document)
    output = BytesIO()
    edit = EditOperation(
        operation_id="subject",
        type="update_msg_subject_text",
        target_node_id=node.node_id,
        payload={
            "property_tag": 0x0037001F,
            "old_value": node.payload.text,
            "value": "Bravo",
        },
    )
    patch_msg(document, BytesIO(source), output, edits=(edit,))
    return output.getvalue(), _authorized_ranges(node)


def test_verifier_accepts_exact_authorized_subject_change() -> None:
    source = make_msg_cfb(subject="Alpha").data
    candidate, ranges = _edited_candidate(source)

    verify_msg_candidate(
        source,
        candidate,
        requested_subject="Bravo",
        authorized_ranges=ranges,
    )


def test_verifier_rejects_drift_outside_authorized_subject_ranges() -> None:
    source = make_msg_cfb(subject="Alpha").data
    candidate, ranges = _edited_candidate(source)
    drifted = bytearray(candidate)
    drifted[10] ^= 0x01

    with pytest.raises(RoundTripVerificationError, match="outside|header|drift"):
        verify_msg_candidate(
            source,
            bytes(drifted),
            requested_subject="Bravo",
            authorized_ranges=ranges,
        )


def test_verifier_rejects_property_stream_drift() -> None:
    fixture = make_msg_cfb(subject="Alpha")
    candidate, ranges = _edited_candidate(fixture.data)
    drifted = bytearray(candidate)
    drifted[fixture.properties_physical_start + 32] ^= 0x01

    with pytest.raises(
        RoundTripVerificationError, match="property|non-subject|outside|drift"
    ):
        verify_msg_candidate(
            fixture.data,
            bytes(drifted),
            requested_subject="Bravo",
            authorized_ranges=ranges,
        )


def test_verifier_rejects_candidate_length_drift() -> None:
    source = make_msg_cfb(subject="Alpha").data
    candidate, ranges = _edited_candidate(source)

    with pytest.raises(RoundTripVerificationError, match="length|size"):
        verify_msg_candidate(
            source,
            candidate + b"\x00",
            requested_subject="Bravo",
            authorized_ranges=ranges,
        )


def test_verifier_rejects_wrong_requested_semantic_value() -> None:
    source = make_msg_cfb(subject="Alpha").data
    candidate, ranges = _edited_candidate(source)

    with pytest.raises(RoundTripVerificationError, match="semantic|subject|value"):
        verify_msg_candidate(
            source,
            candidate,
            requested_subject="Delta",
            authorized_ranges=ranges,
        )


def test_verifier_rejects_wrong_authorized_range() -> None:
    source = make_msg_cfb(subject="Alpha").data
    candidate, ranges = _edited_candidate(source)
    shifted = tuple((start + 1, end + 1) for start, end in ranges)

    with pytest.raises(RoundTripVerificationError, match="range|authorized|subject"):
        verify_msg_candidate(
            source,
            candidate,
            requested_subject="Bravo",
            authorized_ranges=shifted,
        )
