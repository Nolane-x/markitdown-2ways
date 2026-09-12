from __future__ import annotations

import codecs

import pytest

from markitdown.twoways.formats.html.codec import decode_html_source
from markitdown.twoways.formats.html.lexical import parse_html_source, scan_html_text
from markitdown.twoways.formats.html.model import HtmlLexicalError


def _nodes_by_path(text: str):
    document = scan_html_text(text)
    return document, {node.path: node for node in document.nodes}


def test_scans_stable_html_with_exact_paths_and_source_spelling() -> None:
    text = '<HTML><body><p CLASS="hero">A&amp;B<br>tail</p></body></HTML>'
    document, nodes = _nodes_by_path(text)

    assert document.root_path == "/html[1]"
    assert "/html[1]/body[1]/p[1]" in nodes
    assert "/html[1]/body[1]/p[1]/br[1]" in nodes

    paragraph = nodes["/html[1]/body[1]/p[1]"]
    assert paragraph.qname == "p"
    assert paragraph.normalized_name == "p"
    assert paragraph.raw.startswith('<p CLASS="hero">')

    attribute = nodes["/html[1]/body[1]/p[1]/@class"]
    assert attribute.qname == "CLASS"
    assert attribute.normalized_name == "class"
    assert attribute.quote == '"'
    assert attribute.value == "hero"
    assert attribute.value_start is not None
    assert attribute.value_end is not None
    assert text[attribute.value_start : attribute.value_end] == "hero"

    first_text = nodes["/html[1]/body[1]/p[1]/#text[1]"]
    assert first_text.raw == "A&amp;B"
    assert first_text.value == "A&B"

    tail = nodes["/html[1]/body[1]/p[1]/#text[2]"]
    assert tail.raw == "tail"
    assert tail.value == "tail"


def test_preserves_doctype_comment_void_and_attribute_shapes() -> None:
    text = "<!DOCTYPE html><!--lead--><html><body><input disabled data-x=abc><img alt='x'></body></html>"
    document = scan_html_text(text)
    nodes = tuple(document.nodes)

    assert any(
        node.kind == "doctype" and node.raw == "<!DOCTYPE html>" for node in nodes
    )
    assert any(node.kind == "comment" and node.raw == "<!--lead-->" for node in nodes)

    by_path = {node.path: node for node in nodes}
    disabled = by_path["/html[1]/body[1]/input[1]/@disabled"]
    assert disabled.value is None
    assert disabled.value_start is None
    assert disabled.quote is None

    unquoted = by_path["/html[1]/body[1]/input[1]/@data-x"]
    assert unquoted.value == "abc"
    assert unquoted.quote is None
    assert text[unquoted.value_start : unquoted.value_end] == "abc"

    quoted = by_path["/html[1]/body[1]/img[1]/@alt"]
    assert quoted.value == "x"
    assert quoted.quote == "'"


def test_rawtext_and_rcdata_are_distinct_owners() -> None:
    text = "<html><head><title>A&amp;B</title><style>a<b{c:d}</style></head><body><textarea>x&amp;y</textarea><script>if(a<b){x&y}</script></body></html>"
    _, nodes = _nodes_by_path(text)

    title = next(
        node
        for node in nodes.values()
        if node.kind == "rcdata"
        and node.parent_path
        and "/title[1]" in node.parent_path
    )
    textarea = next(
        node
        for node in nodes.values()
        if node.kind == "rcdata"
        and node.parent_path
        and "/textarea[1]" in node.parent_path
    )
    style = next(
        node
        for node in nodes.values()
        if node.kind == "rawtext"
        and node.parent_path
        and "/style[1]" in node.parent_path
    )
    script = next(
        node
        for node in nodes.values()
        if node.kind == "rawtext"
        and node.parent_path
        and "/script[1]" in node.parent_path
    )

    assert title.value == "A&B"
    assert textarea.value == "x&y"
    assert style.raw == "a<b{c:d}"
    assert script.raw == "if(a<b){x&y}"


def test_duplicate_normalized_attributes_are_recorded_as_ambiguous() -> None:
    parsed = parse_html_source(b'<html><body><p A="1" a="2">x</p></body></html>')

    assert parsed.recovery_stable is False
    assert parsed.recovery_reason == "html.attribute.duplicate_name"


def test_utf8_bom_and_meta_charset_are_authoritative() -> None:
    source = (
        codecs.BOM_UTF8
        + b'<html><head><meta charset="utf-8"></head><body>x</body></html>'
    )
    text, representation, declarations = decode_html_source(source)

    assert text.startswith("<html>")
    assert representation.encoding == "utf-8"
    assert representation.bom == "utf-8"
    assert representation.byte_roundtrip is True
    assert len(declarations) == 1
    assert declarations[0].encoding == "utf-8"


def test_explicit_legacy_encoding_with_matching_meta_roundtrips() -> None:
    text = '<html><head><meta charset="windows-1252"></head><body>caf\xe9</body></html>'
    source = text.encode("windows-1252")

    decoded, representation, declarations = decode_html_source(
        source, encoding="windows-1252"
    )

    assert "caf\xe9" in decoded
    assert representation.byte_roundtrip is True
    assert declarations[0].encoding in {"cp1252", "windows-1252"}


def test_conflicting_explicit_and_meta_encoding_fails_closed() -> None:
    source = b'<html><head><meta charset="windows-1252"></head><body>x</body></html>'

    with pytest.raises(HtmlLexicalError, match="encoding"):
        decode_html_source(source, encoding="utf-8")


def test_multiple_conflicting_meta_encodings_fail_closed() -> None:
    source = b'<html><head><meta charset="utf-8"><meta charset="windows-1252"></head><body>x</body></html>'

    with pytest.raises(HtmlLexicalError, match="encoding"):
        decode_html_source(source)


def test_malformed_token_boundary_fails_closed() -> None:
    with pytest.raises(HtmlLexicalError):
        scan_html_text('<html><body><p class="unterminated>x</p></body></html>')
