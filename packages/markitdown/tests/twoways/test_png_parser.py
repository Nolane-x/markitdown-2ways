from __future__ import annotations

import pytest

from markitdown.twoways.formats.png.limits import PngLimits
from markitdown.twoways.formats.png.parser import PngFormatError, parse_png

from ._png_fixtures import corrupt_first_text_crc, make_png, png_chunk


def test_parser_records_complete_valid_chunk_inventory() -> None:
    source = make_png(text=(("Title", "Alpha"), ("Author", "Ada")))

    parsed = parse_png(source)

    assert [chunk.chunk_type for chunk in parsed.chunks] == [
        "IHDR",
        "tEXt",
        "tEXt",
        "IDAT",
        "IEND",
    ]
    assert [(owner.keyword, owner.value) for owner in parsed.text_owners] == [
        ("Title", "Alpha"),
        ("Author", "Ada"),
    ]
    assert parsed.is_apng is False
    assert all(chunk.stored_crc == chunk.computed_crc for chunk in parsed.chunks)


def test_parser_rejects_bad_signature() -> None:
    source = b"not-png!" + make_png()[8:]

    with pytest.raises(PngFormatError, match="signature"):
        parse_png(source)


def test_parser_rejects_invalid_crc() -> None:
    with pytest.raises(PngFormatError, match="CRC"):
        parse_png(corrupt_first_text_crc(make_png()))


def test_parser_rejects_unknown_critical_chunk() -> None:
    source = make_png()
    idat = source.index(b"IDAT") - 4
    candidate = source[:idat] + png_chunk(b"ABCD", b"") + source[idat:]

    with pytest.raises(PngFormatError, match="critical"):
        parse_png(candidate)


def test_parser_enforces_source_limit() -> None:
    source = make_png()
    limits = PngLimits(max_source_bytes=len(source) - 1)

    with pytest.raises(PngFormatError, match="source"):
        parse_png(source, limits=limits)
