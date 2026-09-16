from __future__ import annotations

from io import BytesIO

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.png import read_png_ir
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document

from ._png_fixtures import make_png


def _text_nodes(document):
    return [
        node
        for node in document.nodes.values()
        if node.semantic_role == "png-text-metadata"
    ]


def test_reads_png_text_chunks_into_deterministic_ir() -> None:
    source = make_png(text=(("Title", "Alpha"), ("Author", "Nolane")))

    first = read_png_ir(BytesIO(source), filename="card.png", mimetype="image/png")
    second = read_png_ir(BytesIO(source), filename="card.png", mimetype="image/png")

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    assert first.source is not None
    assert first.source.format == "png"
    assert first.source.filename == "card.png"
    assert first.source.mimetype == "image/png"
    assert first.source.size_bytes == len(source)
    assert first.source.sha256 is not None
    assert first.source.preserved_source_ref == f"png:sha256:{first.source.sha256}"
    assert len(first.canvases) == 1
    assert first.canvases[0].kind == "image"

    nodes = _text_nodes(first)
    assert [node.metadata["png.keyword"] for node in nodes] == ["Title", "Author"]
    assert [
        node.payload.text
        for node in nodes
        if isinstance(node.payload, TextPayload)
    ] == [
        "Alpha",
        "Nolane",
    ]
    for node in nodes:
        assert isinstance(node.payload, TextPayload)
        assert node.native_locator is not None
        assert node.native_locator.backend == "png"
        assert node.native_locator.part_uri == "/"
        assert isinstance(node.metadata["png.chunk_index"], int)
        assert isinstance(node.metadata["png.raw_sha256"], str)


def test_unique_text_keyword_advertises_h12_mutation() -> None:
    document = read_png_ir(BytesIO(make_png()), filename="card.png")
    node = _text_nodes(document)[0]

    decision = capabilities_for_node(node).for_operation("update_png_text_metadata")

    assert decision.state is CapabilityState.WRITABLE
    assert decision.reason_code is None
    assert decision.constraints == {
        "identity_markdown": False,
        "source_preservation": "png-chunk-exact-unrequested",
        "existing_owner_only": True,
        "keyword_immutable": True,
    }


def test_duplicate_text_keyword_is_readable_but_read_only() -> None:
    source = make_png(text=(("Title", "Alpha"), ("Title", "Beta")))
    document = read_png_ir(BytesIO(source), filename="duplicate.png")

    nodes = _text_nodes(document)
    assert len(nodes) == 2
    for node in nodes:
        decision = capabilities_for_node(node).for_operation("update_png_text_metadata")
        assert decision.state is CapabilityState.READ_ONLY
        assert decision.reason_code == "png.text.duplicate_keyword"


def test_apng_is_readable_but_text_mutation_is_read_only() -> None:
    document = read_png_ir(BytesIO(make_png(apng=True)), filename="animated.png")
    node = _text_nodes(document)[0]

    decision = capabilities_for_node(node).for_operation("update_png_text_metadata")

    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "png.apng.read_only"
