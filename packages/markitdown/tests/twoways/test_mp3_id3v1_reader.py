from __future__ import annotations

from io import BytesIO

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.mp3 import Mp3Limits, read_mp3_ir
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document

from ._mp3_fixtures import (
    apev2_tag,
    leading_id3v2,
    lyrics3v1_tag,
    make_mp3,
    mpeg_l3_frame,
)


def _nodes(document):
    return [
        node
        for node in document.nodes.values()
        if node.semantic_role == "mp3-id3v1-text"
    ]


def _node(document, field: str):
    return next(
        node
        for node in _nodes(document)
        if node.metadata["mp3.id3v1_field"] == field
    )


def test_reads_id3v1_into_deterministic_ir() -> None:
    source = make_mp3()
    first = read_mp3_ir(BytesIO(source), filename="song.mp3", mimetype="audio/mpeg")
    second = read_mp3_ir(BytesIO(source), filename="song.mp3", mimetype="audio/mpeg")

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    assert first.source is not None
    assert first.source.format == "mp3"
    assert first.source.filename == "song.mp3"
    assert first.source.mimetype == "audio/mpeg"
    assert first.source.size_bytes == len(source)
    assert first.source.sha256 is not None
    assert first.source.preserved_source_ref == f"mp3:sha256:{first.source.sha256}"
    assert len(first.canvases) == 1
    assert first.canvases[0].kind == "audio"

    nodes = _nodes(first)
    assert [node.metadata["mp3.id3v1_field"] for node in nodes] == [
        "Title",
        "Artist",
        "Album",
    ]
    assert [
        node.payload.text for node in nodes if isinstance(node.payload, TextPayload)
    ] == [
        "Alpha",
        "Nolane",
        "Lab",
    ]
    for node in nodes:
        assert node.native_locator is not None
        assert node.native_locator.backend == "mp3"
        assert node.native_locator.part_uri == "/"
        assert (
            node.native_locator.object_id
            == f"id3v1:{node.metadata['mp3.id3v1_field']}"
        )
        assert node.metadata["mp3.slot_length"] == 30
        assert isinstance(node.metadata["mp3.slot_start"], int)
        assert isinstance(node.metadata["mp3.slot_end"], int)
        assert isinstance(node.metadata["mp3.slot_sha256"], str)
        assert isinstance(node.metadata["mp3.id3v1_sha256"], str)
        assert node.metadata["mp3.native_source"] is True


def test_safe_owner_advertises_h15_mutation() -> None:
    document = read_mp3_ir(BytesIO(make_mp3()), filename="song.mp3")
    decision = capabilities_for_node(_node(document, "Title")).for_operation(
        "update_mp3_id3v1_text"
    )
    assert decision.state is CapabilityState.WRITABLE
    assert decision.reason_code is None
    assert decision.constraints == {
        "identity_markdown": False,
        "existing_owner_only": True,
        "fixed_allocation": True,
        "source_preservation": "mp3-exact-outside-target-slot",
        "field_identity_immutable": True,
    }


def test_competing_metadata_and_unproven_audio_are_read_only() -> None:
    cases = (
        (make_mp3(leading=leading_id3v2()), "mp3.metadata.id3v2_read_only"),
        (make_mp3(terminal_metadata=apev2_tag()), "mp3.metadata.ape_read_only"),
        (make_mp3(terminal_metadata=lyrics3v1_tag()), "mp3.metadata.lyrics3_read_only"),
        (make_mp3(frames=(mpeg_l3_frame(),)), "mp3.audio_structure_unproven"),
    )
    for source, reason in cases:
        document = read_mp3_ir(BytesIO(source), filename="blocked.mp3")
        for node in _nodes(document):
            decision = capabilities_for_node(node).for_operation(
                "update_mp3_id3v1_text"
            )
            assert decision.state is CapabilityState.READ_ONLY
            assert decision.reason_code == reason


def test_noncanonical_slot_padding_is_read_only() -> None:
    source = make_mp3(title_slot=b"A\x00B" + b"\x00" * 27)
    document = read_mp3_ir(BytesIO(source), filename="padding.mp3")
    decision = capabilities_for_node(_node(document, "Title")).for_operation(
        "update_mp3_id3v1_text"
    )
    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "mp3.id3v1.invalid_padding"


def test_read_time_limits_are_persisted_as_authority() -> None:
    limits = Mp3Limits(
        max_source_bytes=1024 * 1024,
        max_audio_frames=100,
        max_frame_bytes=4096,
        max_terminal_metadata_bytes=4096,
    )
    document = read_mp3_ir(BytesIO(make_mp3()), filename="song.mp3", limits=limits)
    assert document.metadata.custom["mp3.read_limits.v1"] == {
        "max_source_bytes": limits.max_source_bytes,
        "max_audio_frames": limits.max_audio_frames,
        "max_frame_bytes": limits.max_frame_bytes,
        "max_terminal_metadata_bytes": limits.max_terminal_metadata_bytes,
    }
