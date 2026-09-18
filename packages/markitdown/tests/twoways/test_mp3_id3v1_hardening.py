from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import PatchPreconditionError, UnsupportedEditError
from markitdown.twoways.capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from markitdown.twoways.formats.mp3 import (
    Mp3FormatError,
    Mp3Limits,
    parse_mp3,
    patch_mp3,
    read_mp3_ir,
)
from markitdown.twoways.ir.edits import EditOperation

from ._mp3_fixtures import (
    apev2_tag,
    leading_id3v2,
    lyrics3v1_tag,
    make_mp3,
)


def _node(document, field: str = "Title"):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "mp3-id3v1-text"
        and node.metadata.get("mp3.id3v1_field") == field
    )


def _edit(
    document,
    value: str = "Beta",
    *,
    field: str = "Title",
    node_id: str | None = None,
) -> EditOperation:
    node = document.nodes[node_id] if node_id is not None else _node(document, field)
    return EditOperation(
        operation_id=f"edit-{field.lower()}",
        type="update_mp3_id3v1_text",
        target_node_id=node.node_id,
        payload={
            "field": field,
            "old_value": node.payload.text,
            "value": value,
        },
    )


def _force_writable(document, field: str = "Title"):
    node = _node(document, field)
    writable = encode_capabilities(
        (
            CapabilityDecision(
                operation="update_mp3_id3v1_text",
                state=CapabilityState.WRITABLE,
            ),
        )
    )
    forged_node = replace(
        node,
        metadata={**node.metadata, CAPABILITY_METADATA_KEY: writable},
    )
    return replace(
        document,
        nodes={**document.nodes, node.node_id: forged_node},
    )


@pytest.mark.parametrize(
    ("source", "message"),
    (
        (make_mp3(leading=leading_id3v2()), "ID3v2"),
        (make_mp3(terminal_metadata=apev2_tag()), "APEv2"),
        (make_mp3(terminal_metadata=lyrics3v1_tag()), "Lyrics3"),
    ),
)
def test_forged_writable_cannot_bypass_fresh_competing_metadata(
    source: bytes,
    message: str,
) -> None:
    document = _force_writable(read_mp3_ir(BytesIO(source), filename="song.mp3"))
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match=message):
        patch_mp3(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document),),
        )

    assert output.getvalue() == b""


def test_forged_writable_cannot_bypass_noncanonical_padding() -> None:
    title_slot = b"A\x00B" + b"\x00" * 27
    source = make_mp3(title_slot=title_slot)
    document = _force_writable(read_mp3_ir(BytesIO(source), filename="song.mp3"))
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="padding"):
        patch_mp3(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document),),
        )

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    ("metadata_key", "forged_value"),
    (
        ("mp3.slot_start", 0),
        ("mp3.slot_end", 30),
        ("mp3.slot_sha256", "0" * 64),
        ("mp3.id3v1_sha256", "1" * 64),
        ("mp3.id3v1_field", "Artist"),
    ),
)
def test_forged_native_evidence_fails_without_output(
    metadata_key: str,
    forged_value: object,
) -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source), filename="song.mp3")
    node = _node(document)
    forged_node = replace(
        node,
        metadata={**node.metadata, metadata_key: forged_value},
    )
    forged = replace(
        document,
        nodes={**document.nodes, node.node_id: forged_node},
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="stale|forged|locator|binding"):
        patch_mp3(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged, node_id=node.node_id),),
        )

    assert output.getvalue() == b""


def test_forged_payload_value_fails_without_output() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source), filename="song.mp3")
    node = _node(document)
    forged_node = replace(node, payload=replace(node.payload, text="Forged"))
    forged = replace(
        document,
        nodes={**document.nodes, node.node_id: forged_node},
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="stale|semantic"):
        patch_mp3(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged),),
        )

    assert output.getvalue() == b""


def test_forged_locator_object_id_fails_without_output() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source), filename="song.mp3")
    node = _node(document)
    assert node.native_locator is not None
    forged_node = replace(
        node,
        native_locator=replace(node.native_locator, object_id="id3v1:Artist"),
    )
    forged = replace(
        document,
        nodes={**document.nodes, node.node_id: forged_node},
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="locator|binding|stale"):
        patch_mp3(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged),),
        )

    assert output.getvalue() == b""


def test_forged_persisted_read_limits_fail_without_output() -> None:
    source = make_mp3()
    limits = Mp3Limits(
        max_source_bytes=len(source),
        max_audio_frames=2,
        max_frame_bytes=1024,
        max_terminal_metadata_bytes=128,
    )
    document = read_mp3_ir(BytesIO(source), filename="song.mp3", limits=limits)
    custom = dict(document.metadata.custom)
    forged_limits = dict(custom["mp3.read_limits.v1"])
    forged_limits["max_audio_frames"] = 999
    custom["mp3.read_limits.v1"] = forged_limits
    forged = replace(
        document,
        metadata=replace(document.metadata, custom=custom),
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="read.*limit|stale|forged"):
        patch_mp3(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged),),
        )

    assert output.getvalue() == b""


def test_ape_size_underflow_is_a_read_only_structure_blocker() -> None:
    malformed = bytearray(apev2_tag())
    malformed[12:16] = (31).to_bytes(4, "little")

    parsed = parse_mp3(make_mp3(terminal_metadata=bytes(malformed)))

    assert "mp3.metadata.ape_read_only" in parsed.blockers
    assert "mp3.structure.invalid" in parsed.blockers
    assert not parsed.audio_authoritative


def test_lyrics3v2_nonnumeric_size_is_a_read_only_structure_blocker() -> None:
    terminal = b"LYRICSBEGINpayload" + b"ABCDEF" + b"LYRICS200"

    parsed = parse_mp3(make_mp3(terminal_metadata=terminal))

    assert "mp3.metadata.lyrics3_read_only" in parsed.blockers
    assert "mp3.structure.invalid" in parsed.blockers
    assert not parsed.audio_authoritative


def test_lyrics3v2_mismatched_begin_is_a_read_only_structure_blocker() -> None:
    body = b"XXXXXXXXXXXpayload"
    terminal = body + f"{len(body):06d}".encode("ascii") + b"LYRICS200"

    parsed = parse_mp3(make_mp3(terminal_metadata=terminal))

    assert "mp3.metadata.lyrics3_read_only" in parsed.blockers
    assert "mp3.structure.invalid" in parsed.blockers
    assert not parsed.audio_authoritative


def test_resource_limits_fail_closed() -> None:
    source = make_mp3()

    with pytest.raises(Mp3FormatError, match="source.*limit"):
        parse_mp3(
            source,
            limits=Mp3Limits(max_source_bytes=len(source) - 1),
        )

    with pytest.raises(Mp3FormatError, match="frame.*limit"):
        parse_mp3(
            source,
            limits=Mp3Limits(max_frame_bytes=16),
        )

    with pytest.raises(Mp3FormatError, match="frame.*limit"):
        parse_mp3(
            source,
            limits=Mp3Limits(max_audio_frames=1),
        )

    with pytest.raises(Mp3FormatError, match="terminal metadata.*limit"):
        parse_mp3(
            make_mp3(terminal_metadata=apev2_tag()),
            limits=Mp3Limits(max_terminal_metadata_bytes=16),
        )
