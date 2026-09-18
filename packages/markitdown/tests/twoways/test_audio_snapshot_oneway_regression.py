from __future__ import annotations

from hashlib import sha1
from io import BytesIO
import inspect
from pathlib import Path

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.converters import _audio_converter as converter_module
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.readers import audio as reader_module
from markitdown.twoways.readers.audio import (
    AudioConverterSnapshot,
    read_audio_snapshot_ir,
)


EXPECTED_CONVERTER_BLOB = "3d96b53c85490021269f198df94e50096f738b19"
SOURCE = b"offline-audio-differential-fixture"


def test_existing_audio_converter_blob_is_unchanged() -> None:
    path = Path(inspect.getsourcefile(converter_module.AudioConverter) or "")
    assert path.is_file()
    data = path.read_bytes()
    git_blob = sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()
    assert git_blob == EXPECTED_CONVERTER_BLOB


@pytest.mark.parametrize(
    ("info", "expected_format"),
    (
        (StreamInfo(extension=".wav"), "wav"),
        (StreamInfo(extension=".mp3"), "mp3"),
        (StreamInfo(extension=".m4a"), "mp4"),
        (StreamInfo(extension=".mp4"), "mp4"),
        (StreamInfo(mimetype="audio/x-wav"), "wav"),
        (StreamInfo(mimetype="audio/mpeg"), "mp3"),
        (StreamInfo(mimetype="video/mp4"), "mp4"),
        (StreamInfo(extension=".m4a", mimetype="audio/mpeg"), "mp3"),
        (StreamInfo(mimetype="audio/x-wav; charset=binary"), None),
    ),
)
def test_h24_matches_one_way_output_and_transcription_route(
    monkeypatch,
    info: StreamInfo,
    expected_format: str | None,
) -> None:
    transcript_calls: list[str] = []

    def _fake_metadata(file_stream, *, exiftool_path=None):
        return {
            "Title": "Demo",
            "Artist": "Nolane",
            "NumChannels": 2,
        }

    def _fake_transcribe(file_stream, *, audio_format: str):
        transcript_calls.append(audio_format)
        return "Hello world"

    monkeypatch.setattr(converter_module, "exiftool_metadata", _fake_metadata)
    monkeypatch.setattr(converter_module, "transcribe_audio", _fake_transcribe)

    converter = converter_module.AudioConverter()
    one_way = converter.convert(BytesIO(SOURCE), info)

    if expected_format is None:
        assert transcript_calls == []
    else:
        assert transcript_calls == [expected_format]

    document = read_audio_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=info,
        snapshot=AudioConverterSnapshot(
            content=one_way.markdown,
            provider="offline-one-way",
            metadata_provider="fake-exiftool",
            transcript_provider="fake-transcriber",
        ),
    )

    node = document.nodes[document.root_node_ids[0]]
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == one_way.markdown

    evidence = document.metadata.custom["twoways.audio_converter_snapshot.v1"]
    assert evidence["transcription_format"] == expected_format


def test_empty_one_way_output_remains_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        converter_module,
        "exiftool_metadata",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        converter_module,
        "transcribe_audio",
        lambda *args, **kwargs: None,
    )
    converter = converter_module.AudioConverter()
    info = StreamInfo(extension=".wav")
    one_way = converter.convert(BytesIO(SOURCE), info)
    assert one_way.markdown == ""

    document = read_audio_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=info,
        snapshot=AudioConverterSnapshot(
            content=one_way.markdown,
            provider="offline-one-way",
        ),
    )
    node = document.nodes[document.root_node_ids[0]]
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == ""


def test_production_reader_has_no_optional_dependency_network_or_process_paths() -> None:
    source = inspect.getsource(reader_module)
    forbidden = (
        "_exiftool",
        "_transcribe_audio",
        "speech_recognition",
        "ffmpeg",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
        "urllib.request",
        "import socket",
        "from socket",
        "import subprocess",
        "from subprocess",
        "time.sleep",
    )
    assert not any(token in source for token in forbidden)
