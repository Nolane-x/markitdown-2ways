from __future__ import annotations

from io import BytesIO

from markitdown.twoways.capabilities import CapabilityState, capabilities_for_node
from markitdown.twoways.formats.zip.reader import read_zip_ir
from markitdown.twoways.ir.serialization import canonical_json_digest, validate_document

from ._xlsx_fixtures import make_xlsx
from ._zip_fixtures import make_zip


def test_zip_reader_builds_deterministic_archive_tree() -> None:
    source = make_zip()
    first = read_zip_ir(BytesIO(source), filename="bundle.zip")
    second = read_zip_ir(BytesIO(source), filename="bundle.zip")

    validate_document(first)
    assert canonical_json_digest(first) == canonical_json_digest(second)
    assert first.source is not None
    assert first.source.format == "zip"
    assert first.canvases[0].kind == "archive"
    root = first.nodes[first.root_node_ids[0]]
    assert root.semantic_role == "zip-archive"
    assert root.metadata["zip.identity_markdown"] is False


def test_nested_xlsx_preserves_each_inner_worksheet_canvas() -> None:
    source = make_zip(
        members={"book.xlsx": make_xlsx(), "keep.txt": b"keep\n"},
    )
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")

    worksheets = [canvas for canvas in document.canvases if canvas.kind == "worksheet"]
    assert len(worksheets) == 2
    assert [canvas.name for canvas in worksheets] == ["Data", "Other"]
    assert all(
        canvas.metadata["zip.member_chain"] == ("book.xlsx",) for canvas in worksheets
    )
    assert all(canvas.metadata["zip.adapter_key"] == "xlsx" for canvas in worksheets)
    for canvas in worksheets:
        assert canvas.root_node_ids
        assert all(
            document.nodes[node_id].canvas_id == canvas.canvas_id
            for node_id in canvas.root_node_ids
        )


def test_nested_json_writable_capability_survives_routing_boundary() -> None:
    source = make_zip(members={"data.json": b'{"name":"Ada"}'})
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    target = next(
        node
        for node in document.nodes.values()
        if node.metadata.get("json.pointer") == "/name"
    )

    decision = capabilities_for_node(target).for_operation("replace_json_scalar")
    assert decision.state is CapabilityState.WRITABLE
    assert target.metadata["zip.member_chain"] == ("data.json",)
    assert target.metadata["zip.adapter_key"] == "json"
    assert target.metadata["zip.inner_node_id"]
    assert target.metadata["zip.inner_source_sha256"]


def test_archive_and_member_structure_are_read_only() -> None:
    source = make_zip(
        members={"data.json": b'{"name":"Ada"}', "keep.txt": b"keep\n"},
    )
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    structure = [
        node
        for node in document.nodes.values()
        if node.semantic_role in {"zip-archive", "zip-member"}
    ]

    assert structure
    for node in structure:
        profile = capabilities_for_node(node)
        assert not any(
            decision.state is CapabilityState.WRITABLE for decision in profile.decisions
        )
