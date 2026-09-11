from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

from .._errors import PatchPreconditionError, UnsupportedEditError
from .nodes import TablePayload


_TYPED_VALUE_KEY = "xlsx.typed_value"


def _supported_scalar(value: object) -> bool:
    if value is None:
        return True
    if type(value) in (str, int, bool):
        return True
    if type(value) is float:
        return isfinite(value)
    return False


def _same_typed_value(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _source_cells(payload: TablePayload) -> dict[tuple[int, int], object]:
    if payload.rows <= 0 or payload.columns <= 0:
        raise UnsupportedEditError(
            "XLSX cell patching requires a non-empty worksheet grid.",
            details={"reason": "unsupported_sheet_structure"},
        )
    if len(payload.cells) != payload.rows * payload.columns:
        raise UnsupportedEditError(
            "XLSX cell patching requires a complete rectangular worksheet grid.",
            details={"reason": "unsupported_sheet_structure"},
        )

    cells: dict[tuple[int, int], object] = {}
    for cell in payload.cells:
        coordinate = (cell.row, cell.column)
        if (
            cell.row < 0
            or cell.row >= payload.rows
            or cell.column < 0
            or cell.column >= payload.columns
            or coordinate in cells
            or cell.row_span != 1
            or cell.column_span != 1
            or cell.node_ids
        ):
            raise UnsupportedEditError(
                "XLSX cell patching requires a simple rectangular worksheet grid.",
                details={"reason": "unsupported_sheet_structure"},
            )
        if _TYPED_VALUE_KEY not in cell.metadata:
            raise UnsupportedEditError(
                "XLSX cell patching requires authoritative typed source values.",
                details={
                    "reason": "missing_typed_cell_value",
                    "row": cell.row,
                    "column": cell.column,
                },
            )
        typed_value = cell.metadata[_TYPED_VALUE_KEY]
        if not _supported_scalar(typed_value):
            raise UnsupportedEditError(
                "XLSX cell patching does not support this source cell value type.",
                details={
                    "reason": "unsupported_source_cell_value",
                    "row": cell.row,
                    "column": cell.column,
                },
            )
        cells[coordinate] = typed_value
    return cells


def validate_sheet_cell_updates(
    payload: TablePayload,
    raw_updates: Any,
) -> tuple[dict[str, object], ...]:
    source = _source_cells(payload)
    if not isinstance(raw_updates, (list, tuple)) or not raw_updates:
        raise UnsupportedEditError(
            "XLSX update_sheet_cells requires a non-empty cells sequence.",
            details={"reason": "invalid_edit_payload"},
        )

    updates: list[dict[str, object]] = []
    seen: set[tuple[int, int]] = set()
    for raw in raw_updates:
        if not isinstance(raw, Mapping):
            raise UnsupportedEditError(
                "XLSX cell update entries must be mappings.",
                details={"reason": "invalid_edit_payload"},
            )
        row = raw.get("row")
        column = raw.get("column")
        old_value = raw.get("old_value")
        new_value = raw.get("value")
        if type(row) is not int or type(column) is not int:
            raise UnsupportedEditError(
                "XLSX cell coordinates must be integers.",
                details={"reason": "invalid_edit_payload"},
            )

        coordinate = (row, column)
        if coordinate in seen:
            raise UnsupportedEditError(
                "XLSX cell edit contains a duplicate coordinate.",
                details={
                    "reason": "duplicate_cell_coordinate",
                    "row": row,
                    "column": column,
                },
            )
        seen.add(coordinate)
        if coordinate not in source:
            raise UnsupportedEditError(
                "XLSX cell edit coordinate is outside the source grid.",
                details={
                    "reason": "cell_out_of_range",
                    "row": row,
                    "column": column,
                },
            )
        if not _supported_scalar(new_value):
            raise UnsupportedEditError(
                "XLSX cell edit value must be a supported finite scalar or blank.",
                details={
                    "reason": "invalid_cell_value",
                    "row": row,
                    "column": column,
                },
            )

        source_value = source[coordinate]
        if not _same_typed_value(old_value, source_value):
            raise PatchPreconditionError(
                "XLSX cell old_value no longer matches the source IR.",
                details={
                    "reason": "cell_old_value_mismatch",
                    "row": row,
                    "column": column,
                    "expected": source_value,
                    "actual": old_value,
                },
            )
        if _same_typed_value(old_value, new_value):
            raise UnsupportedEditError(
                "XLSX cell edit must change the typed cell value.",
                details={
                    "reason": "no_op_cell_update",
                    "row": row,
                    "column": column,
                },
            )

        updates.append(
            {
                "row": row,
                "column": column,
                "old_value": old_value,
                "value": new_value,
            }
        )

    updates.sort(key=lambda item: (int(item["row"]), int(item["column"])))
    return tuple(updates)


def semantic_sheet_values_after_updates(
    payload: TablePayload,
    raw_updates: Any,
) -> tuple[tuple[object, ...], ...]:
    updates = validate_sheet_cell_updates(payload, raw_updates)
    values = _source_cells(payload)
    for update in updates:
        coordinate = (int(update["row"]), int(update["column"]))
        values[coordinate] = update["value"]
    return tuple(
        tuple(values[(row, column)] for column in range(payload.columns))
        for row in range(payload.rows)
    )
