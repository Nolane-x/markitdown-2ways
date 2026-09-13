from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import pytest

from markitdown.twoways.formats.epub.lowering import (
    EpubXmlTextReplacement,
    lower_epub_member_edits,
)
from markitdown.twoways.formats.epub.reader import read_epub_ir
from markitdown.twoways.ir.edits import INITIAL_EDIT_TYPES

from ._epub_fixtures import make_epub, read_member


def _owner(document, *, value: str):
    matches = [
        node
        for node in document.nodes.values()
        if getattr(node.payload, "text", None) == value
        and node.metadata.get("epub.owner_kind") in {"metadata-text", "xhtml-text"}
    ]
    assert len(matches) == 1
    return matches[0]


def _request(node, *, operation_id: str, value: str) -> EpubXmlTextReplacement:
    return EpubXmlTextReplacement(
        operation_id=operation_id,
        xml_path=node.metadata["epub.xml_path"],
        member_sha256=node.metadata["epub.member_sha256"],
        value=value,
    )


def _shadow_path(shadow, edit) -> str:
    assert edit.target_node_id is not None
    path = shadow.nodes[edit.target_node_id].metadata.get("xml.path")
    assert isinstance(path, str)
    return path


def test_h7_registers_exactly_two_epub_edit_types() -> None:
    epub_types = {
        item for item in INITIAL_EDIT_TYPES if item.startswith("replace_epub_")
    }
    assert epub_types == {
        "replace_epub_metadata_text",
        "replace_epub_xhtml_text",
    }


def test_xhtml_owner_lowers_to_fresh_h4_xml_text_edit() -> None:
    source = make_epub()
    document = read_epub_ir(BytesIO(source), filename="book.epub")
    owner = _owner(document, value="world")
    member_path = owner.metadata["epub.member_path"]
    member = read_member(source, member_path)

    shadow, edits = lower_epub_member_edits(
        member,
        member_path,
        (_request(owner, operation_id="xhtml-1", value="WORLD"),),
    )

    assert len(edits) == 1
    assert edits[0].operation_id == "xhtml-1"
    assert edits[0].type == "replace_xml_text"
    assert edits[0].payload == {"value": "WORLD"}
    assert edits[0].precondition is None
    assert _shadow_path(shadow, edits[0]) == owner.metadata["epub.xml_path"]


def test_metadata_owner_uses_same_h4_lowering_boundary() -> None:
    source = make_epub()
    document = read_epub_ir(BytesIO(source), filename="book.epub")
    owner = _owner(document, value="Demo Book")
    member_path = owner.metadata["epub.member_path"]
    member = read_member(source, member_path)

    shadow, edits = lower_epub_member_edits(
        member,
        member_path,
        (_request(owner, operation_id="metadata-1", value="Renamed Book"),),
    )

    assert len(edits) == 1
    assert edits[0].type == "replace_xml_text"
    assert edits[0].payload == {"value": "Renamed Book"}
    assert _shadow_path(shadow, edits[0]) == owner.metadata["epub.xml_path"]


def test_lowering_rejects_stale_member_digest_before_resolving_xml_owner() -> None:
    source = make_epub()
    document = read_epub_ir(BytesIO(source), filename="book.epub")
    owner = _owner(document, value="world")
    member_path = owner.metadata["epub.member_path"]
    member = read_member(source, member_path)
    request = EpubXmlTextReplacement(
        operation_id="stale",
        xml_path=owner.metadata["epub.xml_path"],
        member_sha256=sha256(b"different-member").hexdigest(),
        value="WORLD",
    )

    with pytest.raises(ValueError, match="member digest"):
        lower_epub_member_edits(member, member_path, (request,))


def test_lowering_rejects_duplicate_logical_xml_owner() -> None:
    source = make_epub()
    document = read_epub_ir(BytesIO(source), filename="book.epub")
    owner = _owner(document, value="world")
    member_path = owner.metadata["epub.member_path"]
    member = read_member(source, member_path)
    first = _request(owner, operation_id="first", value="WORLD")
    second = _request(owner, operation_id="second", value="World 2")

    with pytest.raises(ValueError, match="duplicate EPUB XML owner"):
        lower_epub_member_edits(member, member_path, (first, second))


def test_lowering_rejects_unknown_or_non_text_xml_owner() -> None:
    source = make_epub()
    member_path = "OEBPS/chapter.xhtml"
    member = read_member(source, member_path)
    request = EpubXmlTextReplacement(
        operation_id="unknown",
        xml_path="/not/a/real/xml/path",
        member_sha256=sha256(member).hexdigest(),
        value="replacement",
    )

    with pytest.raises(ValueError, match="writable XML text owner"):
        lower_epub_member_edits(member, member_path, (request,))
