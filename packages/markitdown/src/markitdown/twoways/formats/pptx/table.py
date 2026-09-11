from __future__ import annotations

from typing import Any

from ..._errors import PatchPreconditionError, UnsupportedEditError
from ...ir.nodes import TablePayload
from ...ir.table_edits import validate_table_cell_updates
from .text import _paragraph_run_text_nodes, patch_text_shape


def _local_name(element: Any) -> str | None:
    tag = getattr(element, "tag", None)
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else None


def _python_cell_patch_compatible(cell: Any) -> bool:
    if bool(getattr(cell, "is_spanned", False)):
        return False
    if bool(getattr(cell, "is_merge_origin", False)):
        if int(getattr(cell, "span_width", 1) or 1) != 1:
            return False
        if int(getattr(cell, "span_height", 1) or 1) != 1:
            return False
    paragraphs = cell.text_frame.paragraphs
    if len(paragraphs) != 1:
        return False
    try:
        text_nodes = _paragraph_run_text_nodes(paragraphs[0]._p)
    except UnsupportedEditError:
        return False
    return bool(text_nodes)


def pptx_table_patch_compatible(table: Any) -> bool:
    rows = list(table.rows)
    columns = list(table.columns)
    if not rows or not columns:
        return False
    width = len(columns)
    for row in rows:
        cells = list(row.cells)
        if len(cells) != width:
            return False
        if any(not _python_cell_patch_compatible(cell) for cell in cells):
            return False
    return True


def _native_table(shape_element: Any) -> Any | None:
    matches = [item for item in shape_element.iter() if _local_name(item) == "tbl"]
    return matches[0] if len(matches) == 1 else None


def _native_grid(table_element: Any) -> list[list[Any]] | None:
    rows = [child for child in table_element if _local_name(child) == "tr"]
    if not rows:
        return None
    grid: list[list[Any]] = []
    width: int | None = None
    for row in rows:
        cells = [child for child in row if _local_name(child) == "tc"]
        if not cells:
            return None
        if width is None:
            width = len(cells)
        elif len(cells) != width:
            return None
        for cell in cells:
            paragraphs = [item for item in cell.iter() if _local_name(item) == "p"]
            if len(paragraphs) != 1:
                return None
            try:
                text_nodes = _paragraph_run_text_nodes(paragraphs[0])
            except UnsupportedEditError:
                return None
            if not text_nodes:
                return None
        grid.append(cells)
    return grid


def patch_pptx_table_cells(
    shape_element: Any,
    payload: TablePayload,
    raw_updates: Any,
) -> None:
    updates = validate_table_cell_updates(
        payload,
        raw_updates,
        format_label="PPTX",
    )
    table_element = _native_table(shape_element)
    if table_element is None:
        raise UnsupportedEditError(
            "PPTX table shape does not contain one DrawingML table.",
            details={"reason": "unsupported_table_structure"},
        )
    grid = _native_grid(table_element)
    if grid is None:
        raise UnsupportedEditError(
            "PPTX table native structure is not patch-compatible.",
            details={"reason": "unsupported_table_structure"},
        )
    native_rows = len(grid)
    native_columns = len(grid[0]) if grid else 0
    if native_rows != payload.rows or native_columns != payload.columns:
        raise PatchPreconditionError(
            "PPTX native table dimensions no longer match the source IR.",
            details={
                "reason": "native_table_shape_mismatch",
                "expected": (payload.rows, payload.columns),
                "actual": (native_rows, native_columns),
            },
        )

    planned: list[tuple[Any, str, str]] = []
    for update in updates:
        row = int(update["row"])
        column = int(update["column"])
        cell = grid[row][column]
        paragraphs = [item for item in cell.iter() if _local_name(item) == "p"]
        if len(paragraphs) != 1:
            raise UnsupportedEditError(
                "PPTX table cell native structure is not patch-compatible.",
                details={
                    "reason": "unsupported_table_cell_structure",
                    "row": row,
                    "column": column,
                },
            )
        text_nodes = _paragraph_run_text_nodes(paragraphs[0])
        native_old = "".join(item.text or "" for item in text_nodes)
        expected_old = str(update["old_text"])
        if native_old != expected_old:
            raise PatchPreconditionError(
                "PPTX native table cell text no longer matches the source IR.",
                details={
                    "reason": "native_cell_text_mismatch",
                    "row": row,
                    "column": column,
                    "expected": expected_old,
                    "actual": native_old,
                },
            )
        planned.append((cell, expected_old, str(update["text"])))

    for cell, old_text, new_text in planned:
        patch_text_shape(cell, old_text=old_text, new_text=new_text)
