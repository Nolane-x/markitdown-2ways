from __future__ import annotations

from io import BytesIO

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.converters._image_converter import ImageConverter

from ._jpeg_fixtures import make_jpeg


@pytest.mark.parametrize(
    ("extension", "mimetype"),
    (
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        ("", "image/jpeg"),
    ),
)
def test_h14_does_not_change_one_way_jpeg_acceptance(
    extension: str,
    mimetype: str,
) -> None:
    converter = ImageConverter()
    source = BytesIO(make_jpeg())
    stream_info = StreamInfo(
        filename="card.jpg",
        extension=extension,
        mimetype=mimetype,
    )

    assert converter.accepts(source, stream_info) is True
