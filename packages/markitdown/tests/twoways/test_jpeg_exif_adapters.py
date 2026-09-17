from __future__ import annotations

from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.twoways.formats.jpeg import JpegIRReader

from ._jpeg_fixtures import make_jpeg


def test_jpeg_reader_adapter_accepts_extensions_and_mimetypes() -> None:
    reader = JpegIRReader()
    source = BytesIO(make_jpeg())

    assert reader.accepts(source, StreamInfo(extension=".jpg")) is True
    assert reader.accepts(source, StreamInfo(extension=".jpeg")) is True
    assert reader.accepts(source, StreamInfo(mimetype="image/jpeg")) is True
    assert reader.accepts(source, StreamInfo(mimetype="image/jpg")) is True
    assert reader.accepts(source, StreamInfo(extension=".png")) is False


def test_jpeg_reader_adapter_builds_same_ir_surface() -> None:
    source = make_jpeg()
    reader = JpegIRReader()
    stream_info = StreamInfo(
        filename="card.jpeg",
        extension=".jpeg",
        mimetype="image/jpeg",
    )

    document = reader.read(BytesIO(source), stream_info)

    assert document.source is not None
    assert document.source.format == "jpeg"
    assert document.source.filename == "card.jpeg"
    assert document.source.mimetype == "image/jpeg"
    assert [node.semantic_role for node in document.nodes.values()] == [
        "jpeg-exif-text",
        "jpeg-exif-text",
    ]
