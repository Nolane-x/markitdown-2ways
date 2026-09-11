from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile

from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import (
    native_locator_digest,
    node_semantic_digest,
    node_semantic_text,
)

from ._docx_fixtures import build_docx_fixture


def _node_edit(node, edit_type: str, value: str) -> EditOperation:
    key = "text" if edit_type == "replace_text" else "alt_text"
    return EditOperation(
        operation_id=f"docx-{edit_type}-{node.node_id}",
        type=edit_type,
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=node_semantic_text(node),
        ),
        payload={key: value},
    )


def _member_bytes(data: bytes) -> dict[str, bytes]:
    with ZipFile(BytesIO(data), "r") as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _patch(source: bytes, document, edits):
    from markitdown.twoways.formats.docx import patch_docx

    output = BytesIO()
    result = patch_docx(document, BytesIO(source), output, edits=edits)
    return output.getvalue(), result


def test_noop_patch_is_byte_identical():
    from markitdown.twoways.formats.docx import read_docx_ir

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    output, result = _patch(source, document, ())
    assert output == source
    assert result.fidelity.claimed_tier == "exact-preserve"
    assert result.metadata["touched_parts"] == ()


def test_body_text_patch_changes_only_document_xml():
    from markitdown.twoways.formats.docx import read_docx_ir

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    node = document.nodes[document.canvases[0].root_node_ids[0]]
    output, result = _patch(
        source, document, (_node_edit(node, "replace_text", "Revenue 42%"),)
    )
    before = _member_bytes(source)
    after = _member_bytes(output)
    changed = sorted(
        name
        for name in before
        if sha256(before[name]).digest() != sha256(after[name]).digest()
    )
    assert changed == ["word/document.xml"]
    assert result.metadata["touched_parts"] == ("word/document.xml",)
    reread = read_docx_ir(BytesIO(output))
    assert reread.nodes[node.node_id].payload.text == "Revenue 42%"


def test_header_and_footer_text_patches_touch_only_their_parts():
    from markitdown.twoways.formats.docx import read_docx_ir

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    for canvas_index, expected_part, new_text in [
        (1, "word/header1.xml", "Updated Header"),
        (2, "word/footer1.xml", "Updated Footer"),
    ]:
        node = document.nodes[document.canvases[canvas_index].root_node_ids[0]]
        output, result = _patch(
            source, document, (_node_edit(node, "replace_text", new_text),)
        )
        before = _member_bytes(source)
        after = _member_bytes(output)
        changed = [name for name in before if before[name] != after[name]]
        assert changed == [expected_part]
        assert result.metadata["touched_parts"] == (expected_part,)
        reread = read_docx_ir(BytesIO(output))
        assert reread.nodes[node.node_id].payload.text == new_text


def test_picture_alt_patch_changes_only_containing_xml_part():
    from markitdown.twoways.formats.docx import read_docx_ir

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    node = next(item for item in document.nodes.values() if item.kind == "image")
    output, result = _patch(
        source,
        document,
        (_node_edit(node, "set_alt_text", "Updated status pixel"),),
    )
    before = _member_bytes(source)
    after = _member_bytes(output)
    changed = [name for name in before if before[name] != after[name]]
    assert changed == ["word/document.xml"]
    reread = read_docx_ir(BytesIO(output))
    assert reread.nodes[node.node_id].payload.alt_text == "Updated status pixel"
    assert result.fidelity.claimed_tier == "high"


def test_identity_markdown_to_typed_edit_to_docx():
    from markitdown.twoways.formats.docx import read_docx_ir
    from markitdown.twoways.markdown import import_identity_markdown, project_markdown
    from markitdown.twoways.markdown.model import (
        MarkdownProjectionMode,
        MarkdownProjectionOptions,
    )

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    projection = project_markdown(
        document,
        options=MarkdownProjectionOptions(mode=MarkdownProjectionMode.IDENTITY),
    )
    edited = projection.markdown.replace("38%", "42%", 1)
    imported = import_identity_markdown(
        edited,
        original_document=document,
        manifest=projection.manifest,
    )
    assert len(imported.edits) == 1
    assert imported.edits[0].type == "replace_text"
    output, _ = _patch(source, document, imported.edits)
    reread = read_docx_ir(BytesIO(output))
    target = reread.nodes[imported.edits[0].target_node_id]
    assert node_semantic_text(target) == "Revenue 42%"


def test_hyperlink_text_roundtrip_preserves_relationship_part():
    from markitdown.twoways.formats.docx import read_docx_ir

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    node = document.nodes[document.canvases[0].root_node_ids[1]]
    before_rels = _member_bytes(source)["word/_rels/document.xml.rels"]
    output, result = _patch(
        source,
        document,
        (_node_edit(node, "replace_text", "Visit OpenUI today"),),
    )
    after = _member_bytes(output)
    assert after["word/_rels/document.xml.rels"] == before_rels
    reread = read_docx_ir(BytesIO(output))
    assert reread.nodes[node.node_id].payload.text == "Visit OpenUI today"
    assert result.metadata["touched_parts"] == ("word/document.xml",)


def test_writer_rejects_stale_source_and_table_edit():
    import pytest

    from markitdown.twoways._errors import (
        SourcePackageMismatchError,
        UnsupportedEditError,
    )
    from markitdown.twoways.formats.docx import patch_docx, read_docx_ir
    from markitdown.twoways.ir.edits import EditOperation

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    with pytest.raises(SourcePackageMismatchError):
        patch_docx(document, BytesIO(source + b"x"), BytesIO(), edits=())

    table = next(node for node in document.nodes.values() if node.kind == "table")
    edit = EditOperation(
        operation_id="docx-table-edit",
        type="update_table_cells",
        target_node_id=table.node_id,
        payload={"cells": [{"row": 0, "column": 0, "text": "Changed"}]},
    )
    with pytest.raises(UnsupportedEditError):
        patch_docx(document, BytesIO(source), BytesIO(), edits=(edit,))
