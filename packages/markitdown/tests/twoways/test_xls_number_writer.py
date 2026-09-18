from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.formats.xls import patch_xls, read_xls_ir
from markitdown.twoways.ir.edits import EditOperation

from ._xls_fixtures import make_xls_cfb


def _sheet_node(document):
    return next(iter(document.nodes.values()))


def _edit(document, *, row: int = 0, column: int = 0, old=1.5, value=2.5):
    return EditOperation(
        operation_id=f"cell-{row}-{column}",
        type="update_sheet_cells",
        target_node_id=_sheet_node(document).node_id,
        payload={
            "cells": [
                {
                    "row": row,
                    "column": column,
                    "old_value": old,
                    "value": value,
                }
            ]
        },
    )


def test_zero_edit_preserves_source_bytes_exactly() -> None:
    source = make_xls_cfb().data
    document = read_xls_ir(BytesIO(source), filename="legacy.xls")
    output = BytesIO()

    result = patch_xls(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.format == "xls"
    assert result.mode == "patch"
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_number_value_replacement_changes_only_native_eight_byte_slot() -> None:
    fixture = make_xls_cfb(values=((0, 0, 1.5, 3),))
    source = fixture.data
    document = read_xls_ir(BytesIO(source), filename="legacy.xls")
    node = _sheet_node(document)
    target = node.payload.cells[0]
    output = BytesIO()

    patch_xls(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, old=1.5, value=9.25),),
    )

    candidate = output.getvalue()
    reread = read_xls_ir(BytesIO(candidate), filename="legacy.xls")
    reread_target = _sheet_node(reread).payload.cells[0]
    assert reread_target.metadata["xls.typed_value"] == 9.25
    assert len(candidate) == len(source)

    ranges = target.metadata["xls.value_physical_ranges"]
    authorized = {
        index
        for item in ranges
        for index in range(item["start"], item["start"] + item["length"])
    }
    assert len(authorized) == 8
    assert all(
        source[index] == candidate[index]
        for index in range(len(source))
        if index not in authorized
    )


def test_multiple_disjoint_number_updates_are_transactional() -> None:
    source = make_xls_cfb(values=((0, 0, 1.5, 0), (0, 1, 2.5, 0))).data
    document = read_xls_ir(BytesIO(source), filename="legacy.xls")
    node = _sheet_node(document)
    edit = EditOperation(
        operation_id="two-cells",
        type="update_sheet_cells",
        target_node_id=node.node_id,
        payload={
            "cells": [
                {"row": 0, "column": 0, "old_value": 1.5, "value": 3.5},
                {"row": 0, "column": 1, "old_value": 2.5, "value": 4.5},
            ]
        },
    )
    output = BytesIO()

    patch_xls(document, BytesIO(source), output, edits=(edit,))

    reread = read_xls_ir(BytesIO(output.getvalue()), filename="legacy.xls")
    values = {
        (cell.row, cell.column): cell.metadata["xls.typed_value"]
        for cell in _sheet_node(reread).payload.cells
        if cell.metadata["xls.present"]
    }
    assert values == {(0, 0): 3.5, (0, 1): 4.5}


@pytest.mark.parametrize("value", (float("nan"), float("inf"), True, 2**53 + 1))
def test_invalid_replacement_values_fail_without_output(value) -> None:
    source = make_xls_cfb().data
    document = read_xls_ir(BytesIO(source), filename="legacy.xls")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="numeric|finite|exact|bool"):
        patch_xls(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, value=value),),
        )

    assert output.getvalue() == b""


def test_formula_present_workbook_is_read_only() -> None:
    source = make_xls_cfb(include_formula=True).data
    document = read_xls_ir(BytesIO(source), filename="legacy.xls")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="formula|read-only"):
        patch_xls(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document),),
        )

    assert output.getvalue() == b""


def test_stale_old_value_fails_without_output() -> None:
    source = make_xls_cfb().data
    document = read_xls_ir(BytesIO(source), filename="legacy.xls")
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="old|stale|source"):
        patch_xls(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, old=7.0),),
        )

    assert output.getvalue() == b""


def test_source_digest_mismatch_fails_without_output() -> None:
    source = make_xls_cfb(values=((0, 0, 1.5, 0),)).data
    other = make_xls_cfb(values=((0, 0, 7.5, 0),)).data
    document = read_xls_ir(BytesIO(source), filename="legacy.xls")
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError):
        patch_xls(document, BytesIO(other), output, edits=())

    assert output.getvalue() == b""


def test_stale_native_value_digest_fails_without_output() -> None:
    source = make_xls_cfb().data
    document = read_xls_ir(BytesIO(source), filename="legacy.xls")
    node = _sheet_node(document)
    cell = node.payload.cells[0]
    forged_cell = replace(
        cell,
        metadata={**cell.metadata, "xls.value_sha256": "0" * 64},
    )
    forged_node = replace(
        node,
        payload=replace(node.payload, cells=(forged_cell,)),
    )
    forged = replace(
        document,
        nodes={**document.nodes, node.node_id: forged_node},
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="stale|forged|owner|evidence"):
        patch_xls(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged),),
        )

    assert output.getvalue() == b""


def test_missing_number_owner_coordinate_is_not_writable() -> None:
    source = make_xls_cfb(values=((1, 1, 1.5, 0),)).data
    document = read_xls_ir(BytesIO(source), filename="legacy.xls")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="owner|writable|NUMBER"):
        patch_xls(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, row=0, column=0, old=None, value=2.5),),
        )

    assert output.getvalue() == b""
