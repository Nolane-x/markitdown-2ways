from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.jpeg import patch_jpeg, read_jpeg_ir
from markitdown.twoways.formats.jpeg.parser import parse_jpeg
from markitdown.twoways.formats.jpeg.verification import verify_jpeg_candidate
from markitdown.twoways.ir.edits import EditOperation

from ._jpeg_fixtures import IMAGE_DESCRIPTION, make_jpeg


def _node(document):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "jpeg-exif-text"
        and node.metadata.get("jpeg.exif_tag_id") == IMAGE_DESCRIPTION
    )


def _edited_candidate(
    source: bytes,
) -> tuple[bytes, tuple[int, int, int], tuple[int, int]]:
    document = read_jpeg_ir(BytesIO(source), filename="card.jpg")
    node = _node(document)
    output = BytesIO()
    edit = EditOperation(
        operation_id="description",
        type="update_jpeg_exif_text",
        target_node_id=node.node_id,
        payload={
            "tag_id": IMAGE_DESCRIPTION,
            "old_value": node.payload.text,
            "value": "Beta",
        },
    )
    patch_jpeg(document, BytesIO(source), output, edits=(edit,))

    owner = next(
        owner
        for owner in parse_jpeg(source).text_owners
        if owner.tag_id == IMAGE_DESCRIPTION
    )
    key = (owner.marker_index, owner.entry_offset, owner.tag_id)
    span = (owner.value_offset, owner.value_offset + owner.value_length)
    return output.getvalue(), key, span


def test_verifier_accepts_exact_authorized_slot_change() -> None:
    source = make_jpeg()
    candidate, key, span = _edited_candidate(source)

    verify_jpeg_candidate(
        source,
        candidate,
        requested_values={key: "Beta"},
        authorized_spans={key: span},
    )


def test_verifier_rejects_unrequested_byte_drift_outside_target_slot() -> None:
    source = make_jpeg()
    candidate, key, span = _edited_candidate(source)
    parsed_candidate = parse_jpeg(candidate)
    app0 = next(marker for marker in parsed_candidate.markers if marker.code == 0xE0)
    drifted = bytearray(candidate)
    drifted[app0.payload_start] ^= 0x01

    with pytest.raises(RoundTripVerificationError, match="outside authorized"):
        verify_jpeg_candidate(
            source,
            bytes(drifted),
            requested_values={key: "Beta"},
            authorized_spans={key: span},
        )


def test_verifier_rejects_candidate_length_drift() -> None:
    source = make_jpeg()
    candidate, key, span = _edited_candidate(source)

    with pytest.raises(RoundTripVerificationError, match="byte length"):
        verify_jpeg_candidate(
            source,
            candidate + b"\x00",
            requested_values={key: "Beta"},
            authorized_spans={key: span},
        )


def test_verifier_rejects_wrong_requested_semantic_value() -> None:
    source = make_jpeg()
    candidate, key, span = _edited_candidate(source)

    with pytest.raises(RoundTripVerificationError, match="semantic readback"):
        verify_jpeg_candidate(
            source,
            candidate,
            requested_values={key: "Gamma"},
            authorized_spans={key: span},
        )
