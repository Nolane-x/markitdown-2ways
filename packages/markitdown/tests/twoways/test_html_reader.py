from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.html.reader import HtmlIRReader, read_html_ir
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document


def _by_path(document):
    return {
        node.metadata["html.path"]: node
        for node in document.nodes.values()
        if "html.path" in node.metadata
    }


def test_html_reader_builds_deterministic_recovery_stable_ir() -> None:
    source = (
        b'<!DOCTYPE html><!--lead--><html><body><p class="hero">'
        b"A&amp;B<br>tail</p></body></html>"
    )

    first = read_html_ir(BytesIO(source), filename="page.html", mimetype="text/html")
    second = read_html_ir(BytesIO(source), filename="page.html", mimetype="text/html")

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    assert first.source is not None
    assert first.source.format == "html"
    assert first.source.filename == "page.html"
    assert first.source.mimetype == "text/html"
    assert first.source.size_bytes == len(source)
    assert first.source.preserved_source_ref == f"html:sha256:{first.source.sha256}"
    assert len(first.canvases) == 1
    assert first.canvases[0].kind == "html"

    nodes = _by_path(first)
    document_root = nodes["/"]
    assert document_root.kind == "unknown_native"
    assert document_root.semantic_role == "html-document"
    assert document_root.parent_id is None
    assert document_root.payload == {"html_type": "document"}
    assert first.root_node_ids == (document_root.node_id,)
    assert first.canvases[0].root_node_ids == (document_root.node_id,)
    assert document_root.metadata["html.recovery_stable"] is True

    html = nodes["/html[1]"]
    paragraph = nodes["/html[1]/body[1]/p[1]"]
    attribute = nodes["/html[1]/body[1]/p[1]/@class"]
    text = nodes["/html[1]/body[1]/p[1]/#text[1]"]

    assert html.parent_id == document_root.node_id
    assert paragraph.payload["normalized_name"] == "p"
    assert attribute.parent_id == paragraph.node_id
    assert attribute.payload == {
        "html_type": "attribute",
        "qname": "class",
        "normalized_name": "class",
        "value": "hero",
    }
    assert text.payload == {"html_type": "text", "value": "A&B"}
    assert attribute.native_locator is not None
    assert attribute.native_locator.backend == "html"
    assert attribute.native_locator.part_uri == "/"
    assert attribute.native_locator.object_id == "attribute"
    assert attribute.native_locator.path == "/html[1]/body[1]/p[1]/@class"
    assert attribute.provenance[0].char_span == (
        attribute.metadata["html.char_start"],
        attribute.metadata["html.char_end"],
    )

    assert nodes["/#doctype[1]"].parent_id == document_root.node_id
    assert nodes["/#comment[1]"].parent_id == document_root.node_id


def test_html_capabilities_are_narrow_and_kind_specific() -> None:
    document = read_html_ir(
        BytesIO(
            b'<html><head><meta charset="utf-8"><title>x</title><style>a{b:c}</style></head>'
            b'<body><p class="hero" data-x=bare disabled>text</p></body></html>'
        ),
        filename="page.html",
    )
    nodes = _by_path(document)

    text = nodes["/html[1]/body[1]/p[1]/#text[1]"]
    quoted = nodes["/html[1]/body[1]/p[1]/@class"]
    unquoted = nodes["/html[1]/body[1]/p[1]/@data-x"]
    boolean = nodes["/html[1]/body[1]/p[1]/@disabled"]
    element = nodes["/html[1]/body[1]/p[1]"]
    rcdata = next(
        node for node in document.nodes.values() if node.semantic_role == "html-rcdata"
    )
    rawtext = next(
        node for node in document.nodes.values() if node.semantic_role == "html-rawtext"
    )
    charset = nodes["/html[1]/head[1]/meta[1]/@charset"]

    text_decision = capabilities_for_node(text).for_operation("replace_html_text")
    attr_decision = capabilities_for_node(quoted).for_operation(
        "replace_html_attribute"
    )
    assert text_decision.state is CapabilityState.WRITABLE
    assert text_decision.constraints == {
        "identity_markdown": False,
        "source_preservation": "lexical-source-span",
        "structural_edits": False,
        "target_only": True,
        "recovery_stable": True,
    }
    assert attr_decision.state is CapabilityState.WRITABLE
    assert attr_decision.constraints == text_decision.constraints

    assert (
        capabilities_for_node(unquoted)
        .for_operation("replace_html_attribute")
        .reason_code
        == "html.attribute.requires_quote_transition"
    )
    assert (
        capabilities_for_node(boolean)
        .for_operation("replace_html_attribute")
        .reason_code
        == "html.attribute.boolean_read_only"
    )
    assert (
        capabilities_for_node(element).for_operation("replace_html_text").reason_code
        == "html.element.structural_edit_unsupported"
    )
    assert (
        capabilities_for_node(rawtext).for_operation("replace_html_text").reason_code
        == "html.raw_text.read_only"
    )
    assert (
        capabilities_for_node(rcdata).for_operation("replace_html_text").reason_code
        == "html.rcdata.read_only"
    )
    assert (
        capabilities_for_node(charset)
        .for_operation("replace_html_attribute")
        .reason_code
        == "html.encoding.declaration_read_only"
    )


def test_non_roundtrippable_html_representation_is_read_only() -> None:
    document = read_html_ir(
        BytesIO(b"<html><body><p>text</p></body></html>"),
        filename="page.html",
        encoding="utf-8-sig",
    )
    nodes = _by_path(document)
    text = nodes["/html[1]/body[1]/p[1]/#text[1]"]

    assert text.metadata["html.encoding"] == "utf-8-sig"
    assert text.metadata["html.byte_roundtrip"] is False
    decision = capabilities_for_node(text).for_operation("replace_html_text")
    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "html.encoding.not_roundtrippable"


def test_recovery_unstable_html_collapses_to_document_level_read_only_ir() -> None:
    document = read_html_ir(
        BytesIO(b"<html><body><p>one<p>two</body></html>"),
        filename="page.html",
    )

    validate_document(document)
    assert len(document.nodes) == 1
    root = document.nodes[document.root_node_ids[0]]
    assert root.semantic_role == "html-document"
    assert root.metadata["html.path"] == "/"
    assert root.metadata["html.recovery_stable"] is False
    assert root.metadata["html.recovery_reason"] == "html.recovery.optional_end_tag"
    assert (
        capabilities_for_node(root).for_operation("replace_html_text").state
        is CapabilityState.READ_ONLY
    )
    assert (
        capabilities_for_node(root).for_operation("replace_html_text").reason_code
        == "html.recovery.optional_end_tag"
    )
    assert (
        capabilities_for_node(root).for_operation("replace_html_attribute").state
        is CapabilityState.READ_ONLY
    )


def test_duplicate_attributes_collapse_to_read_only_fallback() -> None:
    document = read_html_ir(
        BytesIO(b'<html><body><p A="1" a="2">x</p></body></html>'),
        filename="page.html",
    )
    root = document.nodes[document.root_node_ids[0]]

    assert len(document.nodes) == 1
    assert root.metadata["html.recovery_reason"] == "html.attribute.duplicate_name"


def test_html_ir_reader_accepts_only_exact_html_surfaces() -> None:
    reader = HtmlIRReader()

    assert reader.accepts(
        BytesIO(b""), SimpleNamespace(extension=".html", mimetype=None)
    )
    assert reader.accepts(
        BytesIO(b""), SimpleNamespace(extension=".HTM", mimetype=None)
    )
    assert reader.accepts(
        BytesIO(b""),
        SimpleNamespace(extension=".txt", mimetype="text/html; charset=utf-8"),
    )
    assert not reader.accepts(
        BytesIO(b""),
        SimpleNamespace(extension=".xhtml", mimetype="application/xhtml+xml"),
    )
    assert not reader.accepts(
        BytesIO(b""), SimpleNamespace(extension=".svg", mimetype="image/svg+xml")
    )
    assert not reader.accepts(
        BytesIO(b""), SimpleNamespace(extension=".xml", mimetype="application/xml")
    )
