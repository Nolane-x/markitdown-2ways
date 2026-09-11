from __future__ import annotations

from typing import Any

from ..._errors import PatchPreconditionError, UnsupportedEditError
from ...ir.nodes import TablePayload
from ...ir.table_edits import validate_table_cell_updates
from .text import patch_text_shape

_DRAWINGML_NAMESPACES = (
    "http://schemas.openxmlformats.org/drawingml/2006/main",
    "http://purl.oclc.org/ooxml/drawingml/main",
)


def _is_drawing_element(element: Any, name: str) -> bool:
    tag = getattr(element, "tag", None)
    return isinstance(tag, str) and any(
        tag == f"{{{namespace}}}{name}" for namespace in _DRAWINGML_NAMESPACES
    )


def _supported_children(element: Any, allowed: set[str]) -> bool:
    for child in element:
        tag = getattr(child, "tag", None)
        if not isinstance(tag, str):
            continue
        if not any(_is_drawing_element(child, name) for name in allowed):
            return False
    return True


def _paragraph_text_nodes(paragraph_element: Any) -> list[Any] | None:
    if not _is_drawing_element(paragraph_element, "p"):
        return None
    if not _supported_children(paragraph_element, {"pPr", "r", "endParaRPr"}):
        return None
    if sum(1 for child in paragraph_element if _is_drawing_element(child, "pPr")) > 1:
        return None
    if (
        sum(
            1
            for child in paragraph_element
            if _is_drawing_element(child, "endParaRPr")
        )
        > 1
    ):
        return None

    text_nodes: list[Any] = []
    for run in paragraph_element:
        if not _is_drawing_element(run, "r"):
            continue
        if not _supported_children(run, {"rPr", "t"}):
            return None
        if sum(1 for child in run if _is_drawing_element(child, "rPr")) > 1:
            return None
        run_text_nodes = [child for child in run if _is_drawing_element(child, "t")]
        if len(run_text_nodes) != 1:
            return None
        text_nodes.append(run_text_nodes[0])
    return text_nodes or None


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
    return _paragraph_text_nodes(paragraphs[0]._p) is not None


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
    matches = [item for item in shape_element.iter() if _is_drawing_element(item, "tbl")]
    return matches[0] if len(matches) == 1 else None


def _cell_paragraph(cell: Any) -> Any | None:
    if not _is_drawing_element(cell, "tc"):
        return None
    if not _supported_children(cell, {"txBody", "tcPr"}):
        return None
    text_bodies = [child for child in cell if _is_drawing_element(child, "txBody")]
    if len(text_bodies) != 1:
        return None
    if sum(1 for child in cell if _is_drawing_element(child, "tcPr")) > 1:
        return None
    text_body = text_bodies[0]
    if not _supported_children(text_body, {"bodyPr", "lstStyle", "p"}):
        return None
    if sum(1 for child in text_body if _is_drawing_element(child, "bodyPr")) > 1:
        return None
    if sum(1 for child in text_body if _is_drawing_element(child, "lstStyle")) > 1:
        return None
    paragraphs = [child for child in text_body if _is_drawing_element(child, "p")]
    if len(paragraphs) != 1:
        return None
    return paragraphs[0] if _paragraph_text_nodes(paragraphs[0]) is not None else None


def _native_grid(table_element: Any) -> list[list[Any]] | None:
    if not _is_drawing_element(table_element, "tbl"):
        return None
    if not _supported_children(table_element, {"tblPr", "tblGrid", "tr"}):
        return None
    if sum(1 for child in table_element if _is_drawing_element(child, "tblPr")) > 1:
        return None
    if sum(1 for child in table_element if _is_drawing_element(child, "tblGrid")) != 1:
        return None

    rows = [child for child in table_element if _is_drawing_element(child, "tr")]
    if not rows:
        return None
    grid: list[list[Any]] = []
    width: int | None = None
    for row in rows:
        if not _supported_children(row, {"tc"}):
            return None
        cells = [child for child in row if _is_drawing_element(child, "tc")]
        if not cells:
            return None
        if width is None:
            width = len(cells)
        elif len(cells) != width:
            return None
        if any(_cell_paragraph(cell) is None for cell in cells):
            return None
        grid.append(cells)

    table_grids = [
        child for child in table_element if _is_drawing_element(child, "tblGrid")
    ]
    grid_columns = [
        child for child in table_grids[0] if _is_drawing_element(child, "gridCol")
    ]
    if len(grid_columns) != width:
        return None
    if not _supported_children(table_grids[0], {"gridCol"}):
        return None
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
            "PPTX table shape does not contain one authoritative DrawingML table.",
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
        paragraph = _cell_paragraph(cell)
        if paragraph is None:
            raise UnsupportedEditError(
                "PPTX table cell native structure is not patch-compatible.",
                details={
                    "reason": "unsupported_table_cell_structure",
                    "row": row,
                    "column": column,
                },
            )
        text_nodes = _paragraph_text_nodes(paragraph)
        if text_nodes is None:
            raise UnsupportedEditError(
                "PPTX table cell text carriers are not patch-compatible.",
                details={
                    "reason": "unsupported_table_cell_structure",
                    "row": row,
                    "column": column,
                },
            )
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
