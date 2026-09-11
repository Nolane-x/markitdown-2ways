from __future__ import annotations

from typing import Any

from ..._errors import PatchPreconditionError, UnsupportedEditError
from ...ir.nodes import TablePayload
from ...ir.table_edits import validate_table_cell_updates
from ._text_extract import _collect_carriers, _is_w_element
from ._text_patch import patch_paragraph_text


def _direct_w_children(element: Any, name: str) -> list[Any]:
    return [child for child in element if _is_w_element(child, name)]


def _unsupported_direct_children(element: Any, allowed: set[str]) -> list[str]:
    unsupported: list[str] = []
    for child in element:
        tag = getattr(child, "tag", None)
        if not isinstance(tag, str):
            continue
        local_name = tag.rsplit("}", 1)[-1]
        if local_name not in allowed or not _is_w_element(child, local_name):
            unsupported.append(local_name)
    return unsupported


def _cell_paragraph(cell: Any) -> Any | None:
    if _unsupported_direct_children(cell, {"tcPr", "p"}):
        return None
    tcpr_nodes = _direct_w_children(cell, "tcPr")
    if len(tcpr_nodes) > 1:
        return None
    if tcpr_nodes:
        for descendant in tcpr_nodes[0].iter():
            tag = getattr(descendant, "tag", None)
            if not isinstance(tag, str):
                continue
            if tag.rsplit("}", 1)[-1] in {"gridSpan", "vMerge", "hMerge"}:
                return None
    paragraphs = _direct_w_children(cell, "p")
    if len(paragraphs) != 1:
        return None
    try:
        carriers = _collect_carriers(paragraphs[0])
    except UnsupportedEditError:
        return None
    if not carriers:
        return None
    return paragraphs[0]


def _table_grid(table_element: Any) -> list[list[Any]] | None:
    if not _is_w_element(table_element, "tbl"):
        return None
    if _unsupported_direct_children(table_element, {"tblPr", "tblGrid", "tr"}):
        return None
    if len(_direct_w_children(table_element, "tblPr")) > 1:
        return None
    if len(_direct_w_children(table_element, "tblGrid")) > 1:
        return None

    rows = _direct_w_children(table_element, "tr")
    if not rows:
        return None
    grid: list[list[Any]] = []
    width: int | None = None
    for row in rows:
        if _unsupported_direct_children(row, {"trPr", "tc"}):
            return None
        if len(_direct_w_children(row, "trPr")) > 1:
            return None
        cells = _direct_w_children(row, "tc")
        if not cells:
            return None
        if width is None:
            width = len(cells)
        elif len(cells) != width:
            return None
        if any(_cell_paragraph(cell) is None for cell in cells):
            return None
        grid.append(cells)
    return grid


def docx_table_patch_compatible(table_element: Any) -> bool:
    return _table_grid(table_element) is not None


def patch_docx_table_cells(
    table_element: Any,
    payload: TablePayload,
    raw_updates: Any,
) -> None:
    updates = validate_table_cell_updates(
        payload,
        raw_updates,
        format_label="DOCX",
    )
    grid = _table_grid(table_element)
    if grid is None:
        raise UnsupportedEditError(
            "DOCX table native structure is not patch-compatible.",
            details={"reason": "unsupported_table_structure"},
        )
    native_rows = len(grid)
    native_columns = len(grid[0]) if grid else 0
    if native_rows != payload.rows or native_columns != payload.columns:
        raise PatchPreconditionError(
            "DOCX native table dimensions no longer match the source IR.",
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
        paragraph = _cell_paragraph(grid[row][column])
        if paragraph is None:
            raise UnsupportedEditError(
                "DOCX table cell native structure is not patch-compatible.",
                details={
                    "reason": "unsupported_table_cell_structure",
                    "row": row,
                    "column": column,
                },
            )
        carriers = _collect_carriers(paragraph)
        native_old = "".join(carrier.text_node.text or "" for carrier in carriers)
        expected_old = str(update["old_text"])
        if native_old != expected_old:
            raise PatchPreconditionError(
                "DOCX native table cell text no longer matches the source IR.",
                details={
                    "reason": "native_cell_text_mismatch",
                    "row": row,
                    "column": column,
                    "expected": expected_old,
                    "actual": native_old,
                },
            )
        planned.append((paragraph, expected_old, str(update["text"])))

    for paragraph, old_text, new_text in planned:
        patch_paragraph_text(paragraph, old_text=old_text, new_text=new_text)
