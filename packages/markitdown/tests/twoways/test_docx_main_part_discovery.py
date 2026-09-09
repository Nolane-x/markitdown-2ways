from __future__ import annotations

import pytest

from markitdown.twoways.formats.docx._reader_parts import _main_part_uri

_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)


def _content_types(*part_names: str) -> bytes:
    overrides = "".join(
        f'<Override PartName="{part_name}" ContentType="{_MAIN_CONTENT_TYPE}"/>'
        for part_name in part_names
    )
    return (
        f'<Types xmlns="{_CONTENT_TYPES_NS}">{overrides}</Types>'
    ).encode("utf-8")


def test_main_part_discovery_rejects_distinct_main_document_parts():
    members = {
        "[Content_Types].xml": _content_types(
            "/word/document.xml",
            "/word/other.xml",
        ),
        "word/document.xml": b"",
        "word/other.xml": b"",
    }

    with pytest.raises(ValueError, match="multiple main document parts"):
        _main_part_uri(members)


def test_main_part_discovery_allows_duplicate_identical_override():
    members = {
        "[Content_Types].xml": _content_types(
            "/word/document.xml",
            "/word/document.xml",
        ),
        "word/document.xml": b"",
    }

    assert _main_part_uri(members) == "/word/document.xml"


def test_main_part_discovery_preserves_single_override_and_fallback():
    override_members = {
        "[Content_Types].xml": _content_types("/word/custom.xml"),
        "word/custom.xml": b"",
    }
    fallback_members = {
        "[Content_Types].xml": _content_types(),
        "word/document.xml": b"",
    }

    assert _main_part_uri(override_members) == "/word/custom.xml"
    assert _main_part_uri(fallback_members) == "/word/document.xml"


def test_main_part_discovery_rejects_wrong_content_types_root_namespace():
    xml = (
        '<Types xmlns="urn:not-opc">'
        f'<Override PartName="/word/evil.xml" ContentType="{_MAIN_CONTENT_TYPE}"/>'
        "</Types>"
    ).encode("utf-8")
    members = {
        "[Content_Types].xml": xml,
        "word/evil.xml": b"",
    }

    with pytest.raises(ValueError, match="Content Types namespace"):
        _main_part_uri(members)


def test_main_part_discovery_rejects_foreign_override_namespace():
    xml = (
        f'<Types xmlns="{_CONTENT_TYPES_NS}" xmlns:x="urn:not-opc">'
        f'<x:Override PartName="/word/evil.xml" ContentType="{_MAIN_CONTENT_TYPE}"/>'
        "</Types>"
    ).encode("utf-8")
    members = {
        "[Content_Types].xml": xml,
        "word/evil.xml": b"",
    }

    with pytest.raises(ValueError, match="Override namespace"):
        _main_part_uri(members)


def test_main_part_discovery_rejects_suffix_spoofed_content_type():
    spoofed_content_type = "application/x-wordprocessingml.document.main+xml"
    xml = (
        f'<Types xmlns="{_CONTENT_TYPES_NS}">'
        f'<Override PartName="/word/evil.xml" '
        f'ContentType="{spoofed_content_type}"/>'
        "</Types>"
    ).encode("utf-8")
    members = {
        "[Content_Types].xml": xml,
        "word/evil.xml": b"",
    }

    with pytest.raises(ValueError, match="does not expose a main document part"):
        _main_part_uri(members)
