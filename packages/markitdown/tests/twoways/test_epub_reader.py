from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.epub.reader import EpubIRReader, read_epub_ir

from ._epub_fixtures import make_epub


def _nodes_for_operation(document, operation: str):
    return tuple(
        node
        for node in document.nodes.values()
        if capabilities_for_node(node).for_operation(operation).state
        is CapabilityState.WRITABLE
    )


def test_reader_builds_deterministic_epub3_ir_and_source_authority() -> None:
    source = make_epub()
    first = read_epub_ir(
        BytesIO(source),
        filename="book.epub",
        mimetype="application/epub+zip",
    )
    second = read_epub_ir(
        BytesIO(source),
        filename="book.epub",
        mimetype="application/epub+zip",
    )

    assert first == second
    assert first.source is not None
    assert first.source.format == "epub"
    assert first.source.sha256 == sha256(source).hexdigest()
    assert first.source.size_bytes == len(source)
    assert len(first.canvases) == 1
    assert first.canvases[0].kind == "publication"
    root = first.nodes[first.root_node_ids[0]]
    assert root.semantic_role == "epub-publication"


def test_reader_advertises_only_selected_epub_text_mutations() -> None:
    document = read_epub_ir(BytesIO(make_epub()), filename="book.epub")

    metadata_nodes = _nodes_for_operation(document, "replace_epub_metadata_text")
    xhtml_nodes = _nodes_for_operation(document, "replace_epub_xhtml_text")

    metadata_values = {node.payload.text for node in metadata_nodes}
    xhtml_values = {node.payload.text for node in xhtml_nodes}

    assert {"Demo Book", "Author One", "en"} <= metadata_values
    assert {"Hello ", "world"} <= xhtml_values
    assert "urn:uuid:book-1" not in metadata_values
    assert "Chapter One" not in xhtml_values
    assert "blocked()" not in xhtml_values
    assert "vector" not in xhtml_values
    assert "x" not in xhtml_values
    assert all(node.metadata.get("epub.identity_markdown") is False for node in metadata_nodes)
    assert all(node.metadata.get("epub.identity_markdown") is False for node in xhtml_nodes)


def test_epub2_and_multiple_rootfiles_have_no_writable_epub_text_nodes() -> None:
    for source in (make_epub(version="2.0"), make_epub(multiple_rootfiles=True)):
        document = read_epub_ir(BytesIO(source), filename="book.epub")
        assert _nodes_for_operation(document, "replace_epub_metadata_text") == ()
        assert _nodes_for_operation(document, "replace_epub_xhtml_text") == ()


def test_epub_reader_accepts_extension_and_canonical_mimetype() -> None:
    reader = EpubIRReader()
    stream = BytesIO(make_epub())

    assert reader.accepts(stream, SimpleNamespace(extension=".EPUB", mimetype=None))
    assert reader.accepts(
        stream,
        SimpleNamespace(extension=None, mimetype="application/epub+zip"),
    )


def test_noncanonical_epub_mimetype_is_probed_without_moving_stream() -> None:
    reader = EpubIRReader()
    stream = BytesIO(make_epub())
    stream.seek(7)
    before = stream.tell()

    assert reader.accepts(
        stream,
        SimpleNamespace(extension=None, mimetype="application/x-epub+zip"),
    )
    assert stream.tell() == before


def test_generic_zip_is_not_claimed_by_compatibility_mimetype_probe() -> None:
    reader = EpubIRReader()
    stream = BytesIO(b"not-an-epub")

    assert not reader.accepts(
        stream,
        SimpleNamespace(extension=None, mimetype="application/x-epub+zip"),
    )
