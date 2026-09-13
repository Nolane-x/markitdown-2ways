from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.ipynb.reader import IpynbIRReader, read_ipynb_ir
from markitdown.twoways.ir.nodes import TextPayload
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document


def _source_nodes(document):
    return sorted(
        (
            node
            for node in document.nodes.values()
            if node.metadata.get("ipynb.source_pointer") is not None
        ),
        key=lambda node: node.metadata["ipynb.cell_index"],
    )


def test_ipynb_reader_builds_deterministic_nbformat4_ir() -> None:
    source = (
        b'{"cells":['
        b'{"cell_type":"markdown","id":"m1","metadata":{"tags":["keep"]},'
        b'"source":["# Title\\n","Body"]},'
        b'{"cell_type":"code","execution_count":2,"metadata":{},"outputs":[],'
        b'"source":"print(1)"},'
        b'{"cell_type":"raw","metadata":{},"source":["raw\\n"]}'
        b'],"metadata":{"title":"Notebook"},"nbformat":4,"nbformat_minor":5}'
    )

    first = read_ipynb_ir(BytesIO(source), filename="book.ipynb")
    second = read_ipynb_ir(BytesIO(source), filename="book.ipynb")

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    assert first.source is not None
    assert first.source.format == "ipynb"
    assert first.source.filename == "book.ipynb"
    assert first.source.size_bytes == len(source)
    assert first.source.preserved_source_ref == f"ipynb:sha256:{first.source.sha256}"
    assert len(first.canvases) == 1
    assert first.canvases[0].kind == "notebook"

    root = first.nodes[first.root_node_ids[0]]
    assert root.kind == "group"
    assert root.semantic_role == "ipynb-notebook"
    assert root.parent_id is None
    assert root.metadata["ipynb.nbformat"] == 4
    assert root.metadata["ipynb.nbformat_minor"] == 5
    assert root.metadata["ipynb.top_level_non_cells_digest"]
    assert len(root.children) == 3

    sources = _source_nodes(first)
    assert len(sources) == 3
    markdown, code, raw = sources

    assert isinstance(markdown.payload, TextPayload)
    assert markdown.payload.text == "# Title\nBody"
    assert markdown.semantic_role == "ipynb-markdown-source"
    assert markdown.metadata["text.native_source"] is True
    assert markdown.metadata["ipynb.source_representation"] == "string-array"
    assert markdown.metadata["ipynb.source_segment_pointers"] == (
        "/cells/0/source/0",
        "/cells/0/source/1",
    )
    assert markdown.native_locator is not None
    assert markdown.native_locator.backend == "ipynb"
    assert markdown.native_locator.object_id == "cell-source"
    assert markdown.native_locator.path == "/cells/0/source"
    assert markdown.provenance[0].char_span == (
        markdown.metadata["ipynb.source_start"],
        markdown.metadata["ipynb.source_end"],
    )

    assert isinstance(code.payload, TextPayload)
    assert code.payload.text == "print(1)"
    assert code.semantic_role == "code"
    assert code.metadata["ipynb.source_representation"] == "string"
    assert isinstance(raw.payload, TextPayload)
    assert raw.payload.text == "raw\n"
    assert raw.semantic_role == "ipynb-raw-source"

    for index, cell_id in enumerate(root.children):
        cell = first.nodes[cell_id]
        assert cell.kind == "group"
        assert cell.metadata["ipynb.cell_index"] == index
        assert cell.metadata["ipynb.non_source_digest"]
        assert len(cell.children) == 1
        assert first.nodes[cell.children[0]].parent_id == cell.node_id


def test_ipynb_capabilities_are_narrow_and_source_specific() -> None:
    source = (
        b'{"cells":['
        b'{"cell_type":"markdown","metadata":{},"source":"editable"},'
        b'{"cell_type":"code","metadata":{},"outputs":[],"execution_count":null,'
        b'"source":["print(1)\\n"]},'
        b'{"cell_type":"raw","metadata":{},"source":["raw"]},'
        b'{"cell_type":"mystery","metadata":{},"source":"keep"},'
        b'{"cell_type":"markdown","metadata":{},"source":[]}'
        b'],"metadata":{},"nbformat":4,"nbformat_minor":5}'
    )
    document = read_ipynb_ir(BytesIO(source), filename="book.ipynb")
    sources = _source_nodes(document)

    for node in sources[:3]:
        decision = capabilities_for_node(node).for_operation(
            "replace_ipynb_cell_source"
        )
        assert decision.state is CapabilityState.WRITABLE
        assert decision.constraints == {
            "identity_markdown": False,
            "source_preservation": "json-scalar-source-segments",
            "structural_edits": False,
            "target_only": True,
            "outputs_preserved": True,
        }

    unknown = sources[3]
    assert (
        capabilities_for_node(unknown)
        .for_operation("replace_ipynb_cell_source")
        .reason_code
        == "ipynb.cell.unsupported_type"
    )
    empty_array = sources[4]
    assert (
        capabilities_for_node(empty_array)
        .for_operation("replace_ipynb_cell_source")
        .reason_code
        == "ipynb.cell.source.empty_array_requires_structure"
    )

    root = document.nodes[document.root_node_ids[0]]
    assert (
        capabilities_for_node(root)
        .for_operation("replace_ipynb_cell_source")
        .state
        is CapabilityState.READ_ONLY
    )
    for cell_id in root.children:
        cell = document.nodes[cell_id]
        assert (
            capabilities_for_node(cell)
            .for_operation("replace_ipynb_cell_source")
            .reason_code
            == "ipynb.cell.structure_read_only"
        )


def test_non_roundtrippable_ipynb_source_is_read_only() -> None:
    source = b'{"cells":[{"cell_type":"markdown","metadata":{},"source":"x"}],"metadata":{},"nbformat":4,"nbformat_minor":5}'
    document = read_ipynb_ir(
        BytesIO(source), filename="book.ipynb", encoding="utf-8-sig"
    )
    node = _source_nodes(document)[0]

    assert node.metadata["ipynb.byte_roundtrip"] is False
    decision = capabilities_for_node(node).for_operation("replace_ipynb_cell_source")
    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "ipynb.encoding.not_roundtrippable"


def test_unsupported_nbformat_collapses_to_one_read_only_root() -> None:
    document = read_ipynb_ir(
        BytesIO(b'{"cells":[],"metadata":{},"nbformat":3,"nbformat_minor":0}'),
        filename="old.ipynb",
    )

    validate_document(document)
    assert len(document.nodes) == 1
    root = document.nodes[document.root_node_ids[0]]
    assert root.kind == "unknown_native"
    assert root.semantic_role == "ipynb-notebook"
    assert root.metadata["ipynb.writable_version"] is False
    assert root.metadata["ipynb.read_only_reason"] == "ipynb.nbformat.unsupported_version"
    assert root.native_locator is not None
    assert root.native_locator.object_id == "notebook"
    assert (
        capabilities_for_node(root)
        .for_operation("replace_ipynb_cell_source")
        .reason_code
        == "ipynb.nbformat.unsupported_version"
    )


def test_ipynb_reader_accepts_native_and_probed_json_without_consuming_stream() -> None:
    reader = IpynbIRReader()
    notebook = b'{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":5}'

    assert reader.accepts(
        BytesIO(b"ignored"), SimpleNamespace(extension=".IPYNB", mimetype=None)
    )
    assert reader.accepts(
        BytesIO(b"ignored"),
        SimpleNamespace(extension=".bin", mimetype="application/x-ipynb+json"),
    )

    stream = BytesIO(notebook)
    before = stream.tell()
    assert reader.accepts(
        stream,
        SimpleNamespace(extension=".json", mimetype="application/json"),
    )
    assert stream.tell() == before

    ordinary = BytesIO(b'{"hello":"world"}')
    before = ordinary.tell()
    assert not reader.accepts(
        ordinary,
        SimpleNamespace(extension=".json", mimetype="application/json"),
    )
    assert ordinary.tell() == before

    assert not reader.accepts(
        BytesIO(notebook),
        SimpleNamespace(extension=".json", mimetype="text/plain"),
    )
