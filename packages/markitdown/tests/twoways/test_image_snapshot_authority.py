from __future__ import annotations

from io import BytesIO

import pytest

from markitdown._stream_info import StreamInfo
from markitdown.twoways import (
    ImageDerivedLimits,
    ImageDescriptionSnapshot,
    ImageMetadataSnapshot,
    read_image_snapshot_ir,
)

from .test_image_snapshot_reader import DESCRIPTION, JPEG_INFO, METADATA, SOURCE


class _BoundedReadProbe(BytesIO):
    def __init__(self, data: bytes, *, maximum_request: int) -> None:
        super().__init__(data)
        self.maximum_request = maximum_request
        self.requests: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.requests.append(size)
        if size < 0 or size > self.maximum_request:
            raise AssertionError(f"unbounded read request: {size}")
        return super().read(size)


@pytest.mark.parametrize(
    "field",
    ("Unknown", "FileName", "MIMEType"),
)
def test_metadata_unknown_keys_fail_closed(field: str) -> None:
    with pytest.raises(ValueError, match="metadata field"):
        ImageMetadataSnapshot(fields={field: "value"}, provider="fixture")


def test_metadata_values_must_be_strings() -> None:
    with pytest.raises(TypeError, match="metadata value"):
        ImageMetadataSnapshot(fields={"Title": 123}, provider="fixture")


@pytest.mark.parametrize(
    ("factory", "message"),
    (
        (
            lambda: ImageMetadataSnapshot(fields={}, provider=" "),
            "provider",
        ),
        (
            lambda: ImageDescriptionSnapshot(
                content="caption",
                provider=" ",
                model="vision",
                content_type="image/jpeg",
            ),
            "provider",
        ),
        (
            lambda: ImageDescriptionSnapshot(
                content="caption",
                provider="fixture",
                model=" ",
                content_type="image/jpeg",
            ),
            "model",
        ),
        (
            lambda: ImageDescriptionSnapshot(
                content="caption",
                provider="fixture",
                model="vision",
                content_type=" ",
            ),
            "content_type",
        ),
    ),
)
def test_snapshot_authority_fields_must_be_non_empty(factory, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


def test_description_content_type_uses_stream_mimetype_verbatim() -> None:
    info = StreamInfo(extension=".png", mimetype="IMAGE/JPEG")
    document = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=info,
        description=ImageDescriptionSnapshot(
            content="caption",
            provider="fixture",
            model="vision",
            content_type="IMAGE/JPEG",
        ),
    )
    evidence = document.metadata.custom["twoways.image_converter_snapshot.v1"]
    assert evidence["accepted_by"] == "extension"
    assert evidence["description_content_type"] == "IMAGE/JPEG"


@pytest.mark.parametrize(
    ("extension", "expected"),
    (
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        (".png", "image/png"),
    ),
)
def test_description_content_type_falls_back_to_mimetypes(
    extension: str,
    expected: str,
) -> None:
    document = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=StreamInfo(extension=extension),
        description=ImageDescriptionSnapshot(
            content="caption",
            provider="fixture",
            model="vision",
            content_type=expected,
        ),
    )
    evidence = document.metadata.custom["twoways.image_converter_snapshot.v1"]
    assert evidence["description_content_type"] == expected


def test_description_content_type_mismatch_fails_closed() -> None:
    with pytest.raises(ValueError, match="content_type"):
        read_image_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=JPEG_INFO,
            description=ImageDescriptionSnapshot(
                content="caption",
                provider="fixture",
                model="vision",
                content_type="image/png",
            ),
        )


@pytest.mark.parametrize(
    ("prompt", "effective"),
    (
        (None, "Write a detailed caption for this image."),
        ("", "Write a detailed caption for this image."),
        ("   ", "Write a detailed caption for this image."),
        ("Describe only visible text.", "Describe only visible text."),
    ),
)
def test_effective_prompt_matches_one_way_semantics(
    prompt: str | None,
    effective: str,
) -> None:
    document = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=JPEG_INFO,
        description=ImageDescriptionSnapshot(
            content="caption",
            provider="fixture",
            model="vision",
            prompt=prompt,
            content_type="image/jpeg",
        ),
    )
    evidence = document.metadata.custom["twoways.image_converter_snapshot.v1"]
    assert evidence["description_effective_prompt"] == effective


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_source_bytes", 0),
        ("max_metadata_utf8_bytes", 0),
        ("max_description_utf8_bytes", 0),
        ("max_markdown_utf8_bytes", 0),
        ("max_source_bytes", True),
        ("max_metadata_utf8_bytes", False),
        ("max_description_utf8_bytes", 1.5),
    ),
)
def test_limits_fail_closed(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        ImageDerivedLimits(**{field: value})


def test_source_boundary_and_bounded_reads() -> None:
    probe = _BoundedReadProbe(SOURCE, maximum_request=64 * 1024)
    exact = read_image_snapshot_ir(
        probe,
        stream_info=JPEG_INFO,
        limits=ImageDerivedLimits(max_source_bytes=len(SOURCE)),
    )
    assert exact.source is not None
    assert exact.source.size_bytes == len(SOURCE)
    assert probe.requests
    assert all(0 <= size <= 64 * 1024 for size in probe.requests)

    with pytest.raises(ValueError, match="max_source_bytes"):
        read_image_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=JPEG_INFO,
            limits=ImageDerivedLimits(max_source_bytes=len(SOURCE) - 1),
        )


def test_metadata_description_and_markdown_exact_boundaries() -> None:
    metadata_size = len(
        "Title".encode("utf-8")
        + b"\0"
        + "Demo".encode("utf-8")
        + b"\0"
        + "Artist".encode("utf-8")
        + b"\0"
        + "Nolane".encode("utf-8")
        + b"\0"
        + "GPSPosition".encode("utf-8")
        + b"\0"
        + "20.0 106.0".encode("utf-8")
    )
    description_size = len(DESCRIPTION.content.encode("utf-8"))
    markdown = (
        "Title: Demo\n"
        "Artist: Nolane\n"
        "GPSPosition: 20.0 106.0\n"
        "\n# Description:\n"
        "A small demo image.\n"
    )
    markdown_size = len(markdown.encode("utf-8"))

    exact = read_image_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=JPEG_INFO,
        metadata=METADATA,
        description=DESCRIPTION,
        limits=ImageDerivedLimits(
            max_metadata_utf8_bytes=metadata_size,
            max_description_utf8_bytes=description_size,
            max_markdown_utf8_bytes=markdown_size,
        ),
    )
    assert exact.root_node_ids

    with pytest.raises(ValueError, match="max_metadata_utf8_bytes"):
        read_image_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=JPEG_INFO,
            metadata=METADATA,
            limits=ImageDerivedLimits(max_metadata_utf8_bytes=metadata_size - 1),
        )

    with pytest.raises(ValueError, match="max_description_utf8_bytes"):
        read_image_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=JPEG_INFO,
            description=DESCRIPTION,
            limits=ImageDerivedLimits(max_description_utf8_bytes=description_size - 1),
        )

    with pytest.raises(ValueError, match="max_markdown_utf8_bytes"):
        read_image_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=JPEG_INFO,
            metadata=METADATA,
            description=DESCRIPTION,
            limits=ImageDerivedLimits(max_markdown_utf8_bytes=markdown_size - 1),
        )
