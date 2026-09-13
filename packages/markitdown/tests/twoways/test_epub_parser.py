from __future__ import annotations

import pytest

from markitdown.twoways.formats.epub.model import EpubParseError
from markitdown.twoways.formats.epub.parser import parse_epub_source

from ._epub_fixtures import make_epub


def test_parser_builds_epub3_package_graph_and_text_owner_evidence() -> None:
    parsed = parse_epub_source(make_epub())

    assert parsed.package_version == "3.0"
    assert parsed.writable_version is True
    assert parsed.read_only_reason is None
    assert parsed.package_path == "OEBPS/content.opf"
    assert tuple(item.item_id for item in parsed.manifest) == (
        "chapter",
        "nav",
        "style",
        "cover",
    )
    assert parsed.manifest[0].resolved_path == "OEBPS/chapter.xhtml"
    assert parsed.manifest[1].is_navigation is True
    assert tuple(item.idref for item in parsed.spine) == ("chapter",)

    metadata = {(owner.name, owner.value) for owner in parsed.metadata_owners}
    assert ("title", "Demo Book") in metadata
    assert ("creator", "Author One") in metadata
    assert ("language", "en") in metadata

    xhtml_values = {owner.value for owner in parsed.xhtml_text_owners}
    assert "Hello " in xhtml_values
    assert "world" in xhtml_values
    assert "blocked()" not in xhtml_values
    assert "vector" not in xhtml_values
    assert "x" not in xhtml_values
    assert "Chapter One" not in xhtml_values


def test_epub2_is_parseable_but_deterministically_read_only() -> None:
    parsed = parse_epub_source(make_epub(version="2.0"))

    assert parsed.package_version == "2.0"
    assert parsed.writable_version is False
    assert parsed.read_only_reason == "epub.package.unsupported_version"
    assert parsed.metadata_owners == ()
    assert parsed.xhtml_text_owners == ()


def test_multiple_rootfiles_are_parseable_but_read_only() -> None:
    parsed = parse_epub_source(make_epub(multiple_rootfiles=True))

    assert len(parsed.rootfiles) == 2
    assert parsed.writable_version is False
    assert parsed.read_only_reason == "epub.container.multiple_rootfiles"
    assert parsed.metadata_owners == ()
    assert parsed.xhtml_text_owners == ()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"duplicate_manifest_id": True},
        {"broken_spine": True},
    ],
)
def test_ambiguous_or_broken_package_graph_fails_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(EpubParseError):
        parse_epub_source(make_epub(**kwargs))
