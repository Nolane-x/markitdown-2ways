from __future__ import annotations

from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.twoways.formats.mp3 import Mp3IRReader

from ._mp3_fixtures import make_mp3


def test_mp3_reader_adapter_accepts_extension_and_mimetype() -> None:
    reader = Mp3IRReader()
    source = BytesIO(make_mp3())

    assert reader.accepts(source, StreamInfo(extension=".mp3")) is True
    assert reader.accepts(source, StreamInfo(mimetype="audio/mpeg")) is True
    assert reader.accepts(source, StreamInfo(extension=".wav")) is False
    assert reader.accepts(source, StreamInfo(mimetype="audio/mp4")) is False


def test_mp3_reader_adapter_builds_same_ir_surface() -> None:
    source = make_mp3()
    reader = Mp3IRReader()
    stream_info = StreamInfo(filename="song.mp3", extension=".mp3", mimetype="audio/mpeg")

    document = reader.read(BytesIO(source), stream_info)

    assert document.source is not None
    assert document.source.format == "mp3"
    assert document.source.filename == "song.mp3"
    assert document.source.mimetype == "audio/mpeg"
    assert [node.semantic_role for node in document.nodes.values()] == [
        "mp3-id3v1-text",
        "mp3-id3v1-text",
        "mp3-id3v1-text",
    ]
