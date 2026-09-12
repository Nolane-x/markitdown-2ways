from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.json.reader import JsonIRReader, read_json_ir
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document


def _by_pointer(document):
    return {node.metadata["json.pointer"]: node for node in document.nodes.values()}


def test_json_reader_builds_deterministic_hierarchical_ir() -> None:
    source = b'{"name":"Ada","n":1,"ok":true,"none":null,"arr":[2]}'

    first = read_json_ir(BytesIO(source), filename="data.json", mimetype="application/json")
    second = read_json_ir(BytesIO(source), filename="data.json", mimetype="application/json")

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    assert first.source is not None
    assert first.source.format == "json"
    assert first.source.filename == "data.json"
    assert first.source.mimetype == "application/json"
    assert first.source.size_bytes == len(source)
    assert first.source.sha256 is not None
    assert first.source.preserved_source_ref == f"json:sha256:{first.source.sha256}"
    assert len(first.canvases) == 1
    assert first.canvases[0].kind == "json"

    nodes = _by_pointer(first)
    assert set(nodes) == {"", "/name", "/n", "/ok", "/none", "/arr", "/arr/0"}
    root = nodes[""]
    assert root.kind == "unknown_native"
    assert root.semantic_role == "json-object"
    assert root.parent_id is None
    assert root.payload == {"json_type": "object", "size": 5}
    assert tuple(first.nodes[node_id].metadata["json.pointer"] for node_id in root.children) == (
        "/name",
        "/n",
        "/ok",
        "/none",
        "/arr",
    )
    assert first.root_node_ids == (root.node_id,)
    assert first.canvases[0].root_node_ids == (root.node_id,)

    string = nodes["/name"]
    assert string.semantic_role == "json-string"
    assert string.payload == {"json_type": "string", "value": "Ada"}
    assert string.metadata["json.kind"] == "string"
    assert string.metadata["json.raw"] == '"Ada"'
    assert string.metadata["json.char_start"] < string.metadata["json.char_end"]
    assert len(string.metadata["json.raw_digest"]) == 64
    assert string.native_locator is not None
    assert string.native_locator.backend == "json"
    assert string.native_locator.part_uri == "/"
    assert string.native_locator.object_id == "value"
    assert string.native_locator.path == "/name"
    assert string.provenance[0].char_span == (
        string.metadata["json.char_start"],
        string.metadata["json.char_end"],
    )

    number = nodes["/n"]
    assert number.payload == {"json_type": "number", "raw": "1"}
    assert nodes["/ok"].payload == {"json_type": "boolean", "value": True}
    assert nodes["/none"].payload == {"json_type": "null", "value": None}
    assert nodes["/arr"].payload == {"json_type": "array", "size": 1}
    assert nodes["/arr/0"].parent_id == nodes["/arr"].node_id


def test_scalar_nodes_are_writable_but_containers_are_structural_read_only() -> None:
    document = read_json_ir(BytesIO(b'{"value":1,"nested":{}}'), filename="data.json")
    nodes = _by_pointer(document)

    scalar = capabilities_for_node(nodes["/value"]).for_operation("replace_json_scalar")
    container = capabilities_for_node(nodes["/nested"]).for_operation("replace_json_scalar")

    assert scalar.state is CapabilityState.WRITABLE
    assert scalar.reason_code is None
    assert scalar.constraints == {
        "identity_markdown": False,
        "source_preservation": "lexical-value-span",
        "structural_edits": False,
        "target_only": True,
    }
    assert container.state is CapabilityState.READ_ONLY
    assert container.reason_code == "json.container.structural_edit_unsupported"


def test_non_roundtrippable_encoding_makes_scalar_read_only() -> None:
    document = read_json_ir(
        BytesIO(b'{"value":"x"}'),
        filename="data.json",
        encoding="utf-8-sig",
    )
    node = _by_pointer(document)["/value"]
    decision = capabilities_for_node(node).for_operation("replace_json_scalar")

    assert node.metadata["json.encoding"] == "utf-8-sig"
    assert node.metadata["json.byte_roundtrip"] is False
    assert decision.state is CapabilityState.READ_ONLY
    assert decision.reason_code == "json.encoding.not_roundtrippable"


def test_root_scalar_is_a_single_writable_root_node() -> None:
    document = read_json_ir(BytesIO(b" true \n"), filename="flag.json")
    nodes = _by_pointer(document)

    assert set(nodes) == {""}
    root = nodes[""]
    assert root.semantic_role == "json-boolean"
    assert root.payload == {"json_type": "boolean", "value": True}
    assert capabilities_for_node(root).for_operation("replace_json_scalar").state is CapabilityState.WRITABLE


def test_json_ir_reader_accepts_only_json_extension_or_exact_mimetype() -> None:
    reader = JsonIRReader()

    assert reader.accepts(BytesIO(b""), SimpleNamespace(extension=".json", mimetype=None))
    assert reader.accepts(
        BytesIO(b""), SimpleNamespace(extension=".txt", mimetype="application/json")
    )
    assert reader.accepts(
        BytesIO(b""), SimpleNamespace(extension=None, mimetype="text/json; charset=utf-8")
    )
    assert not reader.accepts(
        BytesIO(b""), SimpleNamespace(extension=".jsonl", mimetype="application/x-ndjson")
    )
    assert not reader.accepts(
        BytesIO(b""), SimpleNamespace(extension=".txt", mimetype="application/problem+json")
    )
