from __future__ import annotations

from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.converters._image_converter import ImageConverter

from ._png_fixtures import make_png


def test_h12_does_not_change_one_way_png_acceptance() -> None:
    converter = ImageConverter()
    source = BytesIO(make_png())
    stream_info = StreamInfo(
        filename="card.png",
        extension=".png",
        mimetype="image/png",
    )

    assert converter.accepts(source, stream_info) is True
