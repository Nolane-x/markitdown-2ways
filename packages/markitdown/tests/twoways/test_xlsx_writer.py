from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import SourcePackageMismatchError
from markitdown.twoways.formats.xlsx.reader import read_xlsx_ir
from markitdown.twoways.formats.xlsx.writer import patch_xlsx
from markitdown.twoways.ir.document import DocumentIR, SourceDescriptor
from markitdown.twoways.ir.edits import EditOperation
from markitdown.twoways.ir.nodes import TablePayload

from ._xlsx_fixtures import make_xlsx, read_member


def _document_and_sheet() -> tuple[bytes, DocumentIR, str]:
    source = make_xlsx()
    document = read_xlsx_ir(BytesIO(source))
    sheet_id = document.canvases[0].root_node_ids[0]
    return source, document, sheet_id


def test_xlsx_writer_noop_is_byte_identical() -> None:
    source, document, _ = _document_and_sheet()
    output = BytesIO()

    result = patch_xlsx(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.format == "xlsx"
    assert result.mode == "patch"
    assert result.fidelity.claimed_tier == "exact-preserve"
    assert result.metadata["touched_parts"] == ()


def test_xlsx_writer_rejects_non_authoritative_source() -> None:
    source, document, _ = _document_and_sheet()
    assert document.source is not None
    forged = DocumentIR(
        document_id=document.document_id,
        source=SourceDescriptor(format="xlsx", sha256="0" * 64),
        canvases=document.canvases,
        nodes=document.nodes,
    )

    with pytest.raises(SourcePackageMismatchError):
        patch_xlsx(forged, BytesIO(source), BytesIO(), edits=())


def test_xlsx_writer_patches_only_target_sheet_and_re_reads_semantics() -> None:
    source, document, sheet_id = _document_and_sheet()
    edit = EditOperation(
        operation_id="sheet-edit-1",
        type="update_sheet_cells",
        target_node_id=sheet_id,
        payload={
            "cells": [
                {"row": 0, "column": 1, "old_value": 7, "value": 11},
                {"row": 1, "column": 0, "old_value": True, "value": False},
            ]
        },
    )
    output = BytesIO()

    result = patch_xlsx(document, BytesIO(source), output, edits=(edit,))
    output_bytes = output.getvalue()
    reread = read_xlsx_ir(BytesIO(output_bytes))
    table = reread.nodes[reread.canvases[0].root_node_ids[0]]
    assert isinstance(table.payload, TablePayload)
    values = {
        (cell.row, cell.column): cell.metadata["xlsx.typed_value"]
        for cell in table.payload.cells
    }

    assert values[(0, 1)] == 11
    assert values[(1, 0)] is False
    assert read_member(output_bytes, "xl/worksheets/sheet2.xml") == read_member(
        source, "xl/worksheets/sheet2.xml"
    )
    assert read_member(output_bytes, "custom/preserved.bin") == b"preserve-me-exactly"
    assert result.metadata["touched_parts"] == ("xl/worksheets/sheet1.xml",)
    assert result.fidelity.claimed_tier == "high"
    assert not result.fidelity.warnings


def test_xlsx_writer_is_deterministic_for_edit_order() -> None:
    source, document, sheet_id = _document_and_sheet()
    first = EditOperation(
        operation_id="a",
        type="update_sheet_cells",
        target_node_id=sheet_id,
        payload={"cells": [{"row": 0, "column": 1, "old_value": 7, "value": 11}]},
    )
    second = EditOperation(
        operation_id="b",
        type="update_sheet_cells",
        target_node_id=sheet_id,
        payload={"cells": [{"row": 1, "column": 0, "old_value": True, "value": False}]},
    )

    left = BytesIO()
    right = BytesIO()
    patch_xlsx(document, BytesIO(source), left, edits=(first, second))
    patch_xlsx(document, BytesIO(source), right, edits=(second, first))

    assert left.getvalue() == right.getvalue()
