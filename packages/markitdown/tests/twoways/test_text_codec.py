from __future__ import annotations

import codecs

import pytest

from markitdown.twoways.formats.text.codec import (
    decode_text_source,
    encode_text_source,
    normalize_newlines,
)


@pytest.mark.parametrize(
    ("source", "expected_text", "encoding", "bom", "newline"),
    [
        (b"alpha\nbeta\n", "alpha\nbeta\n", "utf-8", "none", "lf"),
        (
            codecs.BOM_UTF8 + "alpha\r\nbeta\r\n".encode("utf-8"),
            "alpha\r\nbeta\r\n",
            "utf-8",
            "utf-8",
            "crlf",
        ),
        (
            codecs.BOM_UTF16_LE + "alpha\rbeta\r".encode("utf-16-le"),
            "alpha\rbeta\r",
            "utf-16-le",
            "utf-16-le",
            "cr",
        ),
        (
            codecs.BOM_UTF16_BE + "alpha".encode("utf-16-be"),
            "alpha",
            "utf-16-be",
            "utf-16-be",
            "none",
        ),
    ],
)
def test_decodes_unicode_sources_without_exposing_bom(
    source: bytes,
    expected_text: str,
    encoding: str,
    bom: str,
    newline: str,
) -> None:
    text, representation = decode_text_source(source)

    assert text == expected_text
    assert representation.encoding == encoding
    assert representation.bom == bom
    assert representation.newline == newline
    assert representation.byte_roundtrip is True
    assert encode_text_source(text, representation) == source


def test_explicit_legacy_encoding_is_preserved_when_exactly_reversible() -> None:
    source = "café\r\n".encode("cp1252")

    text, representation = decode_text_source(source, encoding="cp1252")

    assert text == "café\r\n"
    assert representation.encoding == "cp1252"
    assert representation.bom == "none"
    assert representation.newline == "crlf"
    assert representation.byte_roundtrip is True
    assert encode_text_source(text, representation) == source


def test_mixed_newlines_are_classified_without_normalizing_source_text() -> None:
    source = b"alpha\r\nbeta\ngamma\rdelta"

    text, representation = decode_text_source(source)

    assert text == "alpha\r\nbeta\ngamma\rdelta"
    assert representation.newline == "mixed"
    assert encode_text_source(text, representation) == source


@pytest.mark.parametrize(
    ("source_text", "newline", "expected"),
    [
        ("a\nb\r\nc\rd", "lf", "a\nb\nc\nd"),
        ("a\nb\r\nc\rd", "crlf", "a\r\nb\r\nc\r\nd"),
        ("a\nb\r\nc\rd", "cr", "a\rb\rc\rd"),
    ],
)
def test_normalize_newlines_uses_the_authoritative_source_convention(
    source_text: str,
    newline: str,
    expected: str,
) -> None:
    assert normalize_newlines(source_text, newline) == expected


def test_newline_none_rejects_introducing_a_line_break() -> None:
    assert normalize_newlines("single line", "none") == "single line"
    with pytest.raises(ValueError, match="no newline convention"):
        normalize_newlines("first\nsecond", "none")


def test_mixed_newline_representation_cannot_be_used_for_replacement() -> None:
    with pytest.raises(ValueError, match="mixed newline"):
        normalize_newlines("replacement", "mixed")


def test_unencodable_replacement_fails_instead_of_transcoding() -> None:
    _, representation = decode_text_source(b"plain\r\n", encoding="ascii")

    with pytest.raises(UnicodeEncodeError):
        encode_text_source("caf\u00e9\r\n", representation)


def test_explicit_encoding_must_match_detected_unicode_bom() -> None:
    source = codecs.BOM_UTF8 + b"alpha"

    with pytest.raises(ValueError, match="BOM"):
        decode_text_source(source, encoding="utf-16-le")
