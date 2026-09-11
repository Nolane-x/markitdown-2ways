from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .._errors import PatchPreconditionError, UnsupportedEditError
from .nodes import TablePayload


def _source_cells(payload: TablePayload, *, format_label: str) -> dict[tuple[int, int], str]:
    if payload.rows <= 0 or payload.columns <= 0:
        raise UnsupportedEditError(
            f"{format_label} table cell patching requires a non-empty table.",
            details={"reason": "unsupported_table_structure"},
        )
    if len(payload.cells) != payload.rows * payload.columns:
        raise UnsupportedEditError(
            f"{format_label} table cell patching requires a complete rectangular grid.",
            details={"reason": "unsupported_table_structure"},
        )

    cells: dict[tuple[int, int], str] = {}
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
                f"{format_label} table cell patching requires a simple rectangular table.",
                details={"reason": "unsupported_table_structure"},
            )
        cells[coordinate] = cell.text or ""
    return cells


def validate_table_cell_updates(
    payload: TablePayload,
    raw_updates: Any,
    *,
    format_label: str,
) -> tuple[dict[str, object], ...]:
    source = _source_cells(payload, format_label=format_label)
    if not isinstance(raw_updates, (list, tuple)) or not raw_updates:
        raise UnsupportedEditError(
            f"{format_label} update_table_cells requires a non-empty cells sequence.",
            details={"reason": "invalid_edit_payload"},
        )

    updates: list[dict[str, object]] = []
    seen: set[tuple[int, int]] = set()
    for raw in raw_updates:
        if not isinstance(raw, Mapping):
            raise UnsupportedEditError(
                f"{format_label} table cell update entries must be mappings.",
                details={"reason": "invalid_edit_payload"},
            )
        row = raw.get("row")
        column = raw.get("column")
        old_text = raw.get("old_text")
        new_text = raw.get("text")
        if type(row) is not int or type(column) is not int:
            raise UnsupportedEditError(
                f"{format_label} table cell coordinates must be integers.",
                details={"reason": "invalid_edit_payload"},
            )
        coordinate = (row, column)
        if coordinate in seen:
            raise UnsupportedEditError(
                f"{format_label} table cell edit contains a duplicate coordinate.",
                details={
                    "reason": "duplicate_cell_coordinate",
                    "row": row,
                    "column": column,
                },
            )
        seen.add(coordinate)
        if coordinate not in source:
            raise UnsupportedEditError(
                f"{format_label} table cell edit coordinate is outside the source grid.",
                details={
                    "reason": "cell_out_of_range",
                    "row": row,
                    "column": column,
                },
            )
        if not isinstance(old_text, str) or not isinstance(new_text, str):
            raise UnsupportedEditError(
                f"{format_label} table cell old_text/text values must be strings.",
                details={"reason": "invalid_edit_payload"},
            )
        if old_text != source[coordinate]:
            raise PatchPreconditionError(
                f"{format_label} table cell old_text no longer matches the source IR.",
                details={
                    "reason": "cell_old_value_mismatch",
                    "row": row,
                    "column": column,
                    "expected": source[coordinate],
                    "actual": old_text,
                },
            )
        if old_text == new_text:
            raise UnsupportedEditError(
                f"{format_label} table cell edit must change the cell value.",
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
                "old_text": old_text,
                "text": new_text,
            }
        )
    updates.sort(key=lambda item: (int(item["row"]), int(item["column"])))
    return tuple(updates)


def table_semantic_text_after_updates(
    payload: TablePayload,
    raw_updates: Any,
    *,
    format_label: str,
) -> str:
    updates = validate_table_cell_updates(
        payload,
        raw_updates,
        format_label=format_label,
    )
    values = _source_cells(payload, format_label=format_label)
    for update in updates:
        coordinate = (int(update["row"]), int(update["column"]))
        values[coordinate] = str(update["text"])
    rows = []
    for row in range(payload.rows):
        rows.append(
            "\t".join(values[(row, column)] for column in range(payload.columns))
        )
    return "\n".join(rows)
