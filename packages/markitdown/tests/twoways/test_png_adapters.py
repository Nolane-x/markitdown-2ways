from __future__ import annotations

from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.twoways.formats.png import PngIRReader, PngPatchWriter
from markitdown.twoways.writers.base import TargetInfo

from ._png_fixtures import make_png


def test_png_reader_adapter_accepts_extension_and_mimetype() -> None:
    reader = PngIRReader()
    source = BytesIO(make_png())

    assert reader.accepts(source, StreamInfo(extension=".png")) is True
    assert reader.accepts(source, StreamInfo(mimetype="image/png")) is True
    assert reader.accepts(source, StreamInfo(extension=".jpg")) is False


def test_png_reader_and_writer_adapters_round_trip_noop() -> None:
    source = make_png()
    stream_info = StreamInfo(
        filename="card.png",
        extension=".png",
        mimetype="image/png",
    )
    reader = PngIRReader()
    document = reader.read(BytesIO(source), stream_info)
    writer = PngPatchWriter()
    target = TargetInfo(format="png", mimetype="image/png", extension=".png")
    output = BytesIO()

    assert writer.accepts(document, target) is True
    result = writer.write(
        document,
        output,
        target,
        source_stream=BytesIO(source),
        edits=(),
    )

    assert output.getvalue() == source
    assert result.fidelity.claimed_tier == "exact-preserve"
