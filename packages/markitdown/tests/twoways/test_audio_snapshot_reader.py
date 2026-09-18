from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    AudioConverterSnapshot,
    CapabilityState,
    build_capability_report,
    canonical_json_bytes,
    canonical_json_digest,
    capabilities_for_node,
    decode_document,
    read_audio_snapshot_ir,
)
from markitdown.twoways.formats.mp3 import read_mp3_ir
from markitdown.twoways.ir.nodes import TextPayload

from ._mp3_fixtures import make_mp3


SOURCE = b"RIFF-derived-audio-fixture"
OUTPUT = "Title: Demo\n\n### Audio Transcript:\nHello world"


def _snapshot(**updates: object) -> AudioConverterSnapshot:
    values = {
        "content": OUTPUT,
        "provider": "offline-fixture",
        "materialization_id": "audio-001",
        "metadata_provider": "fake-exiftool",
        "transcript_provider": "fake-transcriber",
    }
    values.update(updates)
    return AudioConverterSnapshot(**values)


def _root(document):
    assert len(document.root_node_ids) == 1
    return document.nodes[document.root_node_ids[0]]


def test_reader_binds_exact_source_and_materialized_output() -> None:
    info = StreamInfo(
        extension=".wav",
        mimetype="audio/x-wav",
        filename="demo.wav",
    )
    document = read_audio_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=info,
        snapshot=_snapshot(),
    )

    assert document.source is not None
    assert document.source.format == "audio-converter-derived-source"
    assert document.source.filename == "demo.wav"
    assert document.source.mimetype == "audio/x-wav"
    assert document.source.sha256 == sha256(SOURCE).hexdigest()
    assert document.source.size_bytes == len(SOURCE)

    node = _root(document)
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == OUTPUT
    assert node.semantic_role == "derived_audio"
    assert node.native_locator is None
    assert document.canvases[0].kind == "derived-audio"
    assert document.canvases[0].native_locator is None

    evidence = document.metadata.custom["twoways.audio_converter_snapshot.v1"]
    output_bytes = OUTPUT.encode("utf-8")
    assert evidence["source_sha256"] == sha256(SOURCE).hexdigest()
    assert evidence["source_size_bytes"] == len(SOURCE)
    assert evidence["accepted_by"] == "extension"
    assert evidence["transcription_format"] == "wav"
    assert evidence["markdown_sha256"] == sha256(output_bytes).hexdigest()
    assert evidence["markdown_utf8_size_bytes"] == len(output_bytes)
    assert evidence["provider"] == "offline-fixture"
    assert evidence["materialization_id"] == "audio-001"
    assert evidence["metadata_provider"] == "fake-exiftool"
    assert evidence["transcript_provider"] == "fake-transcriber"
    assert evidence["exiftool_executed_by_twoways"] is False
    assert evidence["transcription_executed_by_twoways"] is False
    assert evidence["network_performed_by_twoways"] is False
    assert evidence["subprocess_performed_by_twoways"] is False


def test_root_is_derived_and_never_native_writable() -> None:
    document = read_audio_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=StreamInfo(extension=".wav"),
        snapshot=_snapshot(),
    )
    node = _root(document)
    decision = capabilities_for_node(node).for_operation("replace_text")

    assert decision.state is CapabilityState.DERIVED
    assert decision.reason_code == "audio.output.not_native_writable"
    assert decision.constraints == {
        "identity_markdown": False,
        "native_owner": False,
        "remote_writeback": False,
        "materialization": "explicit-local-only",
    }

    report = build_capability_report(document)
    assert report.total_nodes == 1
    assert report.derived_nodes == 1
    assert report.writable_nodes == 0
    assert dict(report.writable_by_operation) == {}


def test_repeated_reads_and_canonical_round_trip_are_deterministic() -> None:
    kwargs = {
        "stream_info": StreamInfo(extension=".m4a"),
        "snapshot": _snapshot(),
    }
    first = read_audio_snapshot_ir(BytesIO(SOURCE), **kwargs)
    second = read_audio_snapshot_ir(BytesIO(SOURCE), **kwargs)

    assert canonical_json_digest(first) == canonical_json_digest(second)
    encoded = canonical_json_bytes(first)
    decoded = decode_document(encoded)
    assert canonical_json_bytes(decoded) == encoded


def test_source_and_output_are_independent_identity_authorities() -> None:
    info = StreamInfo(extension=".mp4")
    baseline = read_audio_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=info,
        snapshot=_snapshot(),
    )
    changed_source = read_audio_snapshot_ir(
        BytesIO(SOURCE + b"-changed"),
        stream_info=info,
        snapshot=_snapshot(),
    )
    changed_output = read_audio_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=info,
        snapshot=_snapshot(content=OUTPUT + "\nchanged"),
    )

    assert baseline.source is not None
    assert changed_source.source is not None
    assert changed_output.source is not None
    assert baseline.document_id != changed_source.document_id
    assert baseline.document_id != changed_output.document_id
    assert baseline.source.sha256 != changed_source.source.sha256
    assert baseline.source.sha256 == changed_output.source.sha256


@pytest.mark.parametrize(
    ("extension", "expected_format"),
    (
        (".wav", "wav"),
        (".mp3", "mp3"),
        (".m4a", "mp4"),
        (".mp4", "mp4"),
    ),
)
def test_complete_extension_surface_is_accepted(
    extension: str,
    expected_format: str,
) -> None:
    document = read_audio_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=StreamInfo(extension=extension),
        snapshot=_snapshot(),
    )
    evidence = document.metadata.custom["twoways.audio_converter_snapshot.v1"]
    assert evidence["accepted_by"] == "extension"
    assert evidence["transcription_format"] == expected_format


@pytest.mark.parametrize(
    ("mimetype", "expected_format"),
    (
        ("audio/x-wav", "wav"),
        ("audio/mpeg", "mp3"),
        ("video/mp4", "mp4"),
    ),
)
def test_exact_mime_surface_is_accepted_and_routes_transcription(
    mimetype: str,
    expected_format: str,
) -> None:
    document = read_audio_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=StreamInfo(mimetype=mimetype),
        snapshot=_snapshot(),
    )
    evidence = document.metadata.custom["twoways.audio_converter_snapshot.v1"]
    assert evidence["accepted_by"] == "mimetype"
    assert evidence["transcription_format"] == expected_format


def test_prefix_acceptance_does_not_invent_transcription_route() -> None:
    document = read_audio_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=StreamInfo(mimetype="audio/x-wav; charset=binary"),
        snapshot=_snapshot(),
    )
    evidence = document.metadata.custom["twoways.audio_converter_snapshot.v1"]
    assert evidence["accepted_by"] == "mimetype"
    assert evidence["transcription_format"] is None


def test_one_way_branch_order_is_preserved_for_conflicting_stream_info() -> None:
    document = read_audio_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=StreamInfo(extension=".m4a", mimetype="audio/mpeg"),
        snapshot=_snapshot(),
    )
    evidence = document.metadata.custom["twoways.audio_converter_snapshot.v1"]
    assert evidence["accepted_by"] == "extension"
    assert evidence["transcription_format"] == "mp3"


def test_empty_materialized_output_is_valid() -> None:
    document = read_audio_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=StreamInfo(extension=".wav"),
        snapshot=_snapshot(content=""),
    )
    node = _root(document)
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == ""


def test_mp3_derived_view_does_not_acquire_h15_native_authority() -> None:
    source = make_mp3()
    native = read_mp3_ir(BytesIO(source))
    derived = read_audio_snapshot_ir(
        BytesIO(source),
        stream_info=StreamInfo(extension=".mp3", mimetype="audio/mpeg"),
        snapshot=_snapshot(),
    )

    assert native.source is not None
    assert derived.source is not None
    assert native.source.sha256 == derived.source.sha256

    node = _root(derived)
    assert node.native_locator is None
    assert capabilities_for_node(node).for_operation("replace_text").state is (
        CapabilityState.DERIVED
    )
