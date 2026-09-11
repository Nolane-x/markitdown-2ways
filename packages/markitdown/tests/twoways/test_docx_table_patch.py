from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways import PatchPreconditionError, UnsupportedEditError
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.nodes import TablePayload
from markitdown.twoways.ir.semantics import (
    native_locator_digest,
    node_semantic_digest,
    node_semantic_text,
)

from ._docx_fixtures import build_docx_fixture


def _table(document):
    return next(node for node in document.nodes.values() if node.kind == "table")


def _edit(table, cells):
    return EditOperation(
        operation_id="docx-update-table-cells",
        type="update_table_cells",
        target_node_id=table.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(table),
            expected_native_locator_digest=native_locator_digest(table),
            expected_old_value=node_semantic_text(table),
        ),
        payload={"cells": cells},
    )


def _members(data: bytes):
    with ZipFile(BytesIO(data), "r") as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _cell_text(payload: TablePayload, row: int, column: int) -> str:
    return next(
        (cell.text or "")
        for cell in payload.cells
        if cell.row == row and cell.column == column
    )


def test_docx_reader_marks_fixture_table_cell_patchable():
    from markitdown.twoways.formats.docx import read_docx_ir

    document = read_docx_ir(BytesIO(build_docx_fixture()))
    table = _table(document)

    assert table.metadata["docx:patch_capabilities"] == ("update_table_cells",)


def test_docx_single_cell_patch_changes_only_document_xml_and_reads_back():
    from markitdown.twoways.formats.docx import patch_docx, read_docx_ir

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    table = _table(document)
    output = BytesIO()

    result = patch_docx(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(
                table,
                [{"row": 1, "column": 1, "old_text": "38%", "text": "42%"}],
            ),
        ),
    )

    before = _members(source)
    after = _members(output.getvalue())
    changed = sorted(
        name
        for name in before
        if sha256(before[name]).digest() != sha256(after[name]).digest()
    )
    assert changed == ["word/document.xml"]
    assert result.metadata["touched_parts"] == ("word/document.xml",)
    assert result.fidelity.claimed_tier == "high"

    reread = read_docx_ir(BytesIO(output.getvalue()))
    patched = reread.nodes[table.node_id]
    assert isinstance(patched.payload, TablePayload)
    assert _cell_text(patched.payload, 1, 1) == "42%"
    assert _cell_text(patched.payload, 1, 0) == "Revenue"


def test_docx_multi_cell_patch_preserves_unedited_cells():
    from markitdown.twoways.formats.docx import patch_docx, read_docx_ir

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    table = _table(document)
    output = BytesIO()
    patch_docx(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(
                table,
                [
                    {"row": 0, "column": 0, "old_text": "Metric", "text": "KPI"},
                    {"row": 1, "column": 1, "old_text": "38%", "text": "42%"},
                ],
            ),
        ),
    )
    reread = read_docx_ir(BytesIO(output.getvalue()))
    payload = reread.nodes[table.node_id].payload
    assert isinstance(payload, TablePayload)
    assert _cell_text(payload, 0, 0) == "KPI"
    assert _cell_text(payload, 0, 1) == "Value"
    assert _cell_text(payload, 1, 0) == "Revenue"
    assert _cell_text(payload, 1, 1) == "42%"


def test_docx_table_patch_rejects_stale_old_text_before_output():
    from markitdown.twoways.formats.docx import patch_docx, read_docx_ir

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    table = _table(document)
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_docx(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(
                    table,
                    [{"row": 1, "column": 1, "old_text": "37%", "text": "42%"}],
                ),
            ),
        )
    assert output.getvalue() == b""


def test_docx_table_patch_rejects_duplicate_coordinate():
    from markitdown.twoways.formats.docx import patch_docx, read_docx_ir

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    table = _table(document)

    with pytest.raises(UnsupportedEditError):
        patch_docx(
            document,
            BytesIO(source),
            BytesIO(),
            edits=(
                _edit(
                    table,
                    [
                        {"row": 1, "column": 1, "old_text": "38%", "text": "42%"},
                        {"row": 1, "column": 1, "old_text": "38%", "text": "43%"},
                    ],
                ),
            ),
        )
