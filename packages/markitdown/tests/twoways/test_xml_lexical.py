from __future__ import annotations

from decimal import Decimal

import pytest

from markitdown.twoways.formats.xml.lexical import (
    XmlLexicalError,
    scan_xml_text,
)


def _by_path(document):
    return {node.path: node for node in document.nodes}


def test_scans_namespaced_xml_with_exact_native_paths_and_spans() -> None:
    text = '<r xmlns="urn:r" xmlns:m="urn:m"><item m:id="A">x&amp;y</item><item/></r>'
    document = scan_xml_text(text)
    nodes = _by_path(document)

    root_path = "/%7Burn%3Ar%7Dr[1]"
    item1_path = root_path + "/%7Burn%3Ar%7Ditem[1]"
    item2_path = root_path + "/%7Burn%3Ar%7Ditem[2]"
    attribute_path = item1_path + "/@%7Burn%3Am%7Did"
    text_path = item1_path + "/#text[1]"

    assert document.root_path == root_path
    assert item1_path in nodes
    assert item2_path in nodes

    attribute = nodes[attribute_path]
    assert attribute.kind == "attribute"
    assert attribute.qname == "m:id"
    assert attribute.expanded_name == "{urn:m}id"
    assert attribute.value == "A"
    assert attribute.quote == '"'
    assert text[attribute.value_start : attribute.value_end] == "A"

    text_node = nodes[text_path]
    assert text_node.kind == "text"
    assert text_node.value == "x&y"
    assert text[text_node.start : text_node.end] == "x&amp;y"


def test_default_namespace_does_not_apply_to_unprefixed_attributes() -> None:
    document = scan_xml_text('<r xmlns="urn:r" id="x"><c/></r>')
    nodes = _by_path(document)
    root_path = "/%7Burn%3Ar%7Dr[1]"

    attribute = nodes[root_path + "/@id"]
    assert attribute.qname == "id"
    assert attribute.expanded_name == "id"


def test_preserves_comment_pi_cdata_and_self_closing_lexemes() -> None:
    text = '<?pi test?><r><!--c--><![CDATA[x<y]]><a /></r>'
    document = scan_xml_text(text)
    nodes = tuple(document.nodes)

    assert any(node.kind == "processing_instruction" and node.raw == "<?pi test?>" for node in nodes)
    assert any(node.kind == "comment" and node.raw == "<!--c-->" for node in nodes)
    cdata = next(node for node in nodes if node.kind == "cdata")
    assert cdata.value == "x<y"
    child = next(node for node in nodes if node.kind == "element" and node.qname == "a")
    assert child.raw.endswith("<a />") or child.raw == "<a />"


def test_decodes_predefined_and_numeric_references_strictly() -> None:
    document = scan_xml_text('<r a="&amp;&#9;&#xA;">&lt;&#62;&#x26;</r>')
    nodes = tuple(document.nodes)
    attribute = next(node for node in nodes if node.kind == "attribute" and node.qname == "a")
    text_node = next(node for node in nodes if node.kind == "text")

    assert attribute.value == "&\t\n"
    assert text_node.value == "<>&"


def test_physical_line_breaks_normalize_in_text_semantics() -> None:
    document = scan_xml_text("<r>a\r\nb\rc</r>")
    text_node = next(node for node in document.nodes if node.kind == "text")

    assert text_node.value == "a\nb\nc"


def test_namespace_declarations_are_owned_read_only_lexemes() -> None:
    text = '<r xmlns="urn:r" xmlns:m="urn:m" m:x="1"/>'
    document = scan_xml_text(text)
    namespaces = [node for node in document.nodes if node.kind == "namespace"]

    assert {node.namespace_prefix for node in namespaces} == {"", "m"}
    assert {node.value for node in namespaces} == {"urn:r", "urn:m"}


def test_same_expanded_name_indexing_is_namespace_aware() -> None:
    document = scan_xml_text(
        '<r xmlns:a="u" xmlns:b="u" xmlns:c="v"><a:x/><b:x/><c:x/></r>'
    )
    paths = {node.path for node in document.nodes if node.kind == "element"}

    assert "/r[1]/%7Bu%7Dx[1]" in paths
    assert "/r[1]/%7Bu%7Dx[2]" in paths
    assert "/r[1]/%7Bv%7Dx[1]" in paths


def test_unknown_named_reference_fails_closed() -> None:
    with pytest.raises(XmlLexicalError):
        scan_xml_text("<r>&unknown;</r>")


def test_multiple_roots_fail_closed() -> None:
    with pytest.raises(XmlLexicalError):
        scan_xml_text("<a/><b/>")
