from __future__ import annotations

from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.converters._audio_converter import AudioConverter
from markitdown.twoways.formats.mp3 import Mp3PatchWriter, read_mp3_ir
from markitdown.twoways.writers.base import TargetInfo

from ._mp3_fixtures import make_mp3


def test_h15_does_not_change_one_way_mp3_acceptance() -> None:
    converter = AudioConverter()
    source = BytesIO(make_mp3())
    stream_info = StreamInfo(
        filename="song.mp3",
        extension=".mp3",
        mimetype="audio/mpeg",
    )

    assert converter.accepts(source, stream_info) is True


def test_native_mp3_writer_routes_without_one_way_audio_dependencies() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source), filename="song.mp3")
    writer = Mp3PatchWriter()

    assert writer.accepts(
        document,
        TargetInfo(format="mp3", extension=".mp3"),
    )
