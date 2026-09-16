from __future__ import annotations

import pytest

from markitdown.twoways._errors import RoundTripVerificationError
from markitdown.twoways.formats.epub.parser import parse_epub_source
from markitdown.twoways.formats.epub.verification import verify_epub_candidate

from ._epub_fixtures import make_epub, read_member, replace_member


def _owner_key(original, value: str) -> tuple[str, str]:
    owners = (*original.metadata_owners, *original.xhtml_text_owners)
    matches = [owner for owner in owners if owner.value == value]
    assert len(matches) == 1
    return matches[0].member_path, matches[0].xml_path


def test_candidate_accepts_one_requested_xhtml_text_change() -> None:
    source = make_epub()
    original = parse_epub_source(source)
    member_path, xml_path = _owner_key(original, "world")
    member = read_member(source, member_path)
    candidate = replace_member(source, member_path, member.replace(b"world", b"WORLD"))

    reread = verify_epub_candidate(
        original,
        candidate,
        requested={(member_path, xml_path): "WORLD"},
        touched_members=frozenset({member_path}),
    )

    assert reread.package_path == original.package_path
    assert reread.manifest == original.manifest
    assert reread.spine == original.spine


def test_candidate_rejects_untouched_member_content_drift() -> None:
    source = make_epub()
    original = parse_epub_source(source)
    style = read_member(source, "OEBPS/style.css")
    candidate = replace_member(
        source,
        "OEBPS/style.css",
        style.replace(b"1em", b"2em"),
    )

    with pytest.raises(RoundTripVerificationError):
        verify_epub_candidate(
            original,
            candidate,
            requested={},
            touched_members=frozenset(),
        )


def test_candidate_rejects_package_graph_drift() -> None:
    source = make_epub()
    original = parse_epub_source(source)
    package_path = original.package_path
    opf = read_member(source, package_path)
    candidate = replace_member(
        source,
        package_path,
        opf.replace(b'idref="chapter"', b'idref="nav"'),
    )

    with pytest.raises(RoundTripVerificationError):
        verify_epub_candidate(
            original,
            candidate,
            requested={},
            touched_members=frozenset({package_path}),
        )


def test_candidate_rejects_wrong_requested_value() -> None:
    source = make_epub()
    original = parse_epub_source(source)
    member_path, xml_path = _owner_key(original, "world")
    member = read_member(source, member_path)
    candidate = replace_member(source, member_path, member.replace(b"world", b"WORLD"))

    with pytest.raises(RoundTripVerificationError):
        verify_epub_candidate(
            original,
            candidate,
            requested={(member_path, xml_path): "WRONG"},
            touched_members=frozenset({member_path}),
        )


def test_candidate_rejects_unrequested_owner_drift_inside_touched_member() -> None:
    source = make_epub()
    original = parse_epub_source(source)
    member_path, xml_path = _owner_key(original, "world")
    member = read_member(source, member_path)
    replacement = member.replace(b"Hello ", b"HELLO ").replace(b"world", b"WORLD")
    candidate = replace_member(source, member_path, replacement)

    with pytest.raises(RoundTripVerificationError):
        verify_epub_candidate(
            original,
            candidate,
            requested={(member_path, xml_path): "WORLD"},
            touched_members=frozenset({member_path}),
        )
