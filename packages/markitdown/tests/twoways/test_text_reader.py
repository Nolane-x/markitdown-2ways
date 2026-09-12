from __future__ import annotations

from io import BytesIO

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.text.reader import read_text_ir
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document


def test_reads_text_source_into_deterministic_ir() -> None:
    source = b"alpha\r\nbeta\r\n"

    first = read_text_ir(BytesIO(source), filename="notes.txt", mimetype="text/plain")
    second = read_text_ir(BytesIO(source), filename="notes.txt", mimetype="text/plain")

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    assert first.source is not None
    assert first.source.format == "text"
    assert first.source.filename == "notes.txt"
    assert first.source.mimetype == "text/plain"
    assert first.source.size_bytes == len(source)
    assert first.source.sha256 is not None
    assert first.source.preserved_source_ref == f"text:sha256:{first.source.sha256}"
    assert len(first.canvases) == 1
    assert first.canvases[0].kind == "text"
    assert len(first.nodes) == 1

    node = first.nodes[first.canvases[0].root_node_ids[0]]
    assert node.kind == "text"
    assert node.semantic_role == "document-body"
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == "alpha\r\nbeta\r\n"
    assert node.native_locator is not None
    assert node.native_locator.backend == "text"
    assert node.native_locator.part_uri == "/"
    assert node.native_locator.object_id == "document-body"
    assert node.metadata["text.encoding"] == "utf-8"
    assert node.metadata["text.bom"] == "none"
    assert node.metadata["text.newline"] == "crlf"
    assert node.metadata["text.byte_roundtrip"] is True
    assert node.metadata["text.format"] == "text"


def test_markdown_filename_is_classified_as_native_markdown_source() -> None:
    document = read_text_ir(
        BytesIO(b"# Title\n\nBody\n"),
        filename="README.md",
        mimetype="text/markdown",
    )
    assert document.source is not None
    assert document.source.format == "markdown"
    node = document.nodes[document.canvases[0].root_node_ids[0]]
    assert node.metadata["text.format"] == "markdown"
    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == "# Title\n\nBody\n"


def test_roundtrippable_source_advertises_replace_text() -> None:
    document = read_text_ir(BytesIO(b"alpha\nbeta\n"), filename="notes.txt")
    node = document.nodes[document.canvases[0].root_node_ids[0]]
    decision = capabilities_for_node(node).for_operation("replace_text")

    assert decision.state is CapabilityState.WRITABLE
    assert decision.reason_code is None
    assert decision.constraints == {
        "identity_markdown": True,
        "source_preservation": "encoding-bom-newline",
        "whole_document": True,
    }


def test_mixed_newline_source_is_readable_but_replace_text_is_read_only() -> None:
    document = read_text_ir(BytesIO(b"alpha\r\nbeta\ngamma\r"), filename="mixed.txt")
    node = document.nodes[document.canvases[0].root_node_ids[0]]
    decision = capabilities_for_node(node).for_operation("replace_text")

    assert isinstance(node.payload, TextPayload)
    assert node.payload.text == "alpha\r\nbeta\ngamma\r"
    assert node.metadata["text.newline"] == "mixed"
    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "text.newline.mixed"


def test_non_roundtrippable_explicit_codec_is_read_only() -> None:
    document = read_text_ir(
        BytesIO(b"alpha"),
        filename="notes.txt",
        encoding="utf-8-sig",
    )
    node = document.nodes[document.canvases[0].root_node_ids[0]]
    decision = capabilities_for_node(node).for_operation("replace_text")

    assert node.metadata["text.encoding"] == "utf-8-sig"
    assert node.metadata["text.byte_roundtrip"] is False
    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "text.encoding.not_roundtrippable"
