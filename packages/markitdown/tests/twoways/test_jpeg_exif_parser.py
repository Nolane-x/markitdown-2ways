from __future__ import annotations

import pytest

from markitdown.twoways.formats.jpeg import JpegLimits
from markitdown.twoways.formats.jpeg.parser import JpegFormatError, parse_jpeg

from ._jpeg_fixtures import (
    ARTIST,
    IMAGE_DESCRIPTION,
    ExifTextEntry,
    iptc_app13,
    make_jpeg,
    malformed_marker_length_jpeg,
    malformed_tiff_offset_jpeg,
    xmp_app1,
)


def _owner(parsed, tag_id: int):
    return next(owner for owner in parsed.text_owners if owner.tag_id == tag_id)


def test_parse_little_endian_exif_text_owners() -> None:
    source = make_jpeg()

    parsed = parse_jpeg(source)

    description = _owner(parsed, IMAGE_DESCRIPTION)
    artist = _owner(parsed, ARTIST)
    assert parsed.exif_segment_count == 1
    assert parsed.xmp_present is False
    assert parsed.iptc_present is False
    assert parsed.trailing_bytes == b""
    assert description.tag_name == "ImageDescription"
    assert description.value == "Alpha"
    assert description.byte_order == "little"
    assert description.value_length == 16
    assert description.inline_value is False
    assert artist.value == "Nolane"


def test_parse_big_endian_exif_text_owner() -> None:
    source = make_jpeg(
        entries=(ExifTextEntry(ARTIST, "Ada", capacity=12),),
        endian="big",
    )

    parsed = parse_jpeg(source)
    artist = _owner(parsed, ARTIST)

    assert artist.value == "Ada"
    assert artist.byte_order == "big"
    assert artist.value_length == 12


def test_parse_inline_ascii_owner() -> None:
    source = make_jpeg(
        entries=(ExifTextEntry(IMAGE_DESCRIPTION, "A", capacity=4, force_inline=True),)
    )

    parsed = parse_jpeg(source)
    description = _owner(parsed, IMAGE_DESCRIPTION)

    assert description.value == "A"
    assert description.inline_value is True
    assert description.value_length == 4


def test_parser_reports_cross_metadata_authority() -> None:
    source = make_jpeg(extra_segments=(xmp_app1(), iptc_app13()), second_exif=True)

    parsed = parse_jpeg(source)

    assert parsed.exif_segment_count == 2
    assert parsed.xmp_present is True
    assert parsed.iptc_present is True


def test_duplicate_target_tag_is_recorded_as_ambiguous() -> None:
    source = make_jpeg(
        entries=(
            ExifTextEntry(ARTIST, "Ada", capacity=12),
            ExifTextEntry(ARTIST, "Grace", capacity=12),
        )
    )

    parsed = parse_jpeg(source)

    assert parsed.tag_counts[ARTIST] == 2
    assert all(owner.ambiguous for owner in parsed.text_owners)


def test_overlapping_external_value_slots_are_ambiguous() -> None:
    source = make_jpeg(overlap_external=True)

    parsed = parse_jpeg(source)

    assert all(owner.ambiguous for owner in parsed.text_owners)
    assert any("overlap" in blocker for blocker in parsed.blockers)


def test_invalid_marker_length_fails_closed() -> None:
    with pytest.raises(JpegFormatError, match="segment length"):
        parse_jpeg(malformed_marker_length_jpeg())


def test_invalid_tiff_ifd_offset_fails_closed() -> None:
    with pytest.raises(JpegFormatError, match="IFD0"):
        parse_jpeg(malformed_tiff_offset_jpeg())


def test_source_limit_fails_closed() -> None:
    with pytest.raises(JpegFormatError, match="source.*limit"):
        parse_jpeg(make_jpeg(), limits=JpegLimits(max_source_bytes=32))
