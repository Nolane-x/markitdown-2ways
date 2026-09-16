from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.xml.reader import XmlIRReader, read_xml_ir
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document


def _by_path(document):
    return {node.metadata["xml.path"]: node for node in document.nodes.values()}


def test_xml_reader_builds_deterministic_namespace_aware_ir() -> None:
    source = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<r xmlns:m="urn:m" a="1"><m:c>text</m:c><![CDATA[x]]><!--c--></r>'
    )

    first = read_xml_ir(
        BytesIO(source), filename="data.xml", mimetype="application/xml"
    )
    second = read_xml_ir(
        BytesIO(source), filename="data.xml", mimetype="application/xml"
    )

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    assert first.source is not None
    assert first.source.format == "xml"
    assert first.source.filename == "data.xml"
    assert first.source.mimetype == "application/xml"
    assert first.source.size_bytes == len(source)
    assert first.source.sha256 is not None
    assert first.source.preserved_source_ref == f"xml:sha256:{first.source.sha256}"
    assert len(first.canvases) == 1
    assert first.canvases[0].kind == "xml"

    nodes = _by_path(first)
    root = nodes["/r[1]"]
    assert root.kind == "unknown_native"
    assert root.semantic_role == "xml-element"
    assert root.parent_id is None
    assert root.payload["xml_type"] == "element"
    assert root.payload["qname"] == "r"
    assert first.root_node_ids == (root.node_id,)
    assert first.canvases[0].root_node_ids == (root.node_id,)

    attribute = nodes["/r[1]/@a"]
    assert attribute.parent_id == root.node_id
    assert attribute.semantic_role == "xml-attribute"
    assert attribute.payload == {
        "xml_type": "attribute",
        "qname": "a",
        "expanded_name": "a",
        "value": "1",
    }
    assert attribute.native_locator is not None
    assert attribute.native_locator.backend == "xml"
    assert attribute.native_locator.part_uri == "/"
    assert attribute.native_locator.object_id == "attribute"
    assert attribute.native_locator.path == "/r[1]/@a"
    assert attribute.provenance[0].char_span == (
        attribute.metadata["xml.char_start"],
        attribute.metadata["xml.char_end"],
    )

    child = nodes["/r[1]/%7Burn%3Am%7Dc[1]"]
    text = nodes[child.metadata["xml.path"] + "/#text[1]"]
    assert child.parent_id == root.node_id
    assert child.payload["expanded_name"] == "{urn:m}c"
    assert text.parent_id == child.node_id
    assert text.payload == {"xml_type": "text", "value": "text"}

    namespace = next(
        node for node in first.nodes.values() if node.semantic_role == "xml-namespace"
    )
    assert namespace.payload == {
        "xml_type": "namespace",
        "prefix": "m",
        "uri": "urn:m",
    }

    assert root.metadata["xml.encoding"] == "utf-8"
    assert root.metadata["xml.bom"] == "none"
    assert root.metadata["xml.version"] == "1.0"
    assert root.metadata["xml.declared_encoding"] == "UTF-8"
    assert len(root.metadata["xml.declaration_raw_digest"]) == 64


def test_xml_capabilities_are_narrow_and_kind_specific() -> None:
    document = read_xml_ir(
        BytesIO(b'<r xmlns:m="u" a="1">text<![CDATA[cdata]]></r>'),
        filename="data.xml",
    )
    nodes = _by_path(document)
    root = nodes["/r[1]"]
    attribute = nodes["/r[1]/@a"]
    text = nodes["/r[1]/#text[1]"]
    cdata = nodes["/r[1]/#cdata[1]"]
    namespace = next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "xml-namespace"
    )

    text_decision = capabilities_for_node(text).for_operation("replace_xml_text")
    attr_decision = capabilities_for_node(attribute).for_operation(
        "replace_xml_attribute"
    )
    element_decision = capabilities_for_node(root).for_operation("replace_xml_text")
    namespace_decision = capabilities_for_node(namespace).for_operation(
        "replace_xml_attribute"
    )
    cdata_decision = capabilities_for_node(cdata).for_operation("replace_xml_text")

    assert text_decision.state is CapabilityState.WRITABLE
    assert text_decision.constraints == {
        "identity_markdown": False,
        "source_preservation": "lexical-source-span",
        "structural_edits": False,
        "target_only": True,
    }
    assert attr_decision.state is CapabilityState.WRITABLE
    assert attr_decision.constraints == text_decision.constraints
    assert element_decision.state is CapabilityState.READ_ONLY
    assert element_decision.reason_code == "xml.element.structural_edit_unsupported"
    assert namespace_decision.state is CapabilityState.READ_ONLY
    assert namespace_decision.reason_code == "xml.namespace.structural_edit_unsupported"
    assert cdata_decision.state is CapabilityState.READ_ONLY
    assert cdata_decision.reason_code == "xml.cdata.lexical_edit_unsupported"


def test_non_roundtrippable_xml_representation_is_read_only() -> None:
    document = read_xml_ir(
        BytesIO(b"<r>text</r>"),
        filename="data.xml",
        encoding="utf-8-sig",
    )
    nodes = _by_path(document)
    text = nodes["/r[1]/#text[1]"]
    attribute_free_root = nodes["/r[1]"]

    assert text.metadata["xml.encoding"] == "utf-8-sig"
    assert text.metadata["xml.byte_roundtrip"] is False
    decision = capabilities_for_node(text).for_operation("replace_xml_text")
    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "xml.encoding.not_roundtrippable"
    assert attribute_free_root.metadata["xml.byte_roundtrip"] is False


def test_top_level_misc_is_preserved_without_becoming_document_root() -> None:
    document = read_xml_ir(
        BytesIO(b"<?pre x?><r/><!--after-->"),
        filename="data.xml",
    )
    nodes = _by_path(document)

    root = nodes["/r[1]"]
    assert document.root_node_ids == (root.node_id,)
    assert nodes["/#pi[1]"].parent_id is None
    assert nodes["/#comment[1]"].parent_id is None
    assert nodes["/#pi[1]"].semantic_role == "xml-processing-instruction"
    assert nodes["/#comment[1]"].semantic_role == "xml-comment"


def test_xml_ir_reader_accepts_only_exact_xml_extension_or_mimetype() -> None:
    reader = XmlIRReader()

    assert reader.accepts(
        BytesIO(b""), SimpleNamespace(extension=".xml", mimetype=None)
    )
    assert reader.accepts(
        BytesIO(b""), SimpleNamespace(extension=".txt", mimetype="application/xml")
    )
    assert reader.accepts(
        BytesIO(b""),
        SimpleNamespace(extension=None, mimetype="text/xml; charset=utf-8"),
    )
    assert not reader.accepts(
        BytesIO(b""),
        SimpleNamespace(extension=".svg", mimetype="image/svg+xml"),
    )
    assert not reader.accepts(
        BytesIO(b""),
        SimpleNamespace(extension=".xhtml", mimetype="application/xhtml+xml"),
    )
    assert not reader.accepts(
        BytesIO(b""),
        SimpleNamespace(extension=".rss", mimetype="application/rss+xml"),
    )
