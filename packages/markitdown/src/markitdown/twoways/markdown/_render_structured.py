from __future__ import annotations

from ..ir.nodes import ChartPayload, Node, TablePayload
from .model import MarkdownProjectionOptions, ProjectionDiagnostic
from ._render_model import RenderedNode
from ._render_text import user_text
from .semantics import semantic_text_for_node


def _simple_identity_table(payload: TablePayload) -> bool:
    if payload.rows <= 0 or payload.columns <= 0:
        return False
    if len(payload.cells) != payload.rows * payload.columns:
        return False

    coordinates: set[tuple[int, int]] = set()
    for cell in payload.cells:
        coordinate = (cell.row, cell.column)
        text = cell.text or ""
        if (
            cell.row < 0
            or cell.row >= payload.rows
            or cell.column < 0
            or cell.column >= payload.columns
            or coordinate in coordinates
            or cell.row_span != 1
            or cell.column_span != 1
            or cell.node_ids
            or any(character in text for character in "\r\n|")
        ):
            return False
        coordinates.add(coordinate)
    return len(coordinates) == payload.rows * payload.columns


def _table_edit_capabilities(node: Node, payload: TablePayload) -> tuple[str, ...]:
    if not _simple_identity_table(payload):
        return ()
    native_capabilities: set[str] = set()
    for key in ("docx:patch_capabilities", "pptx:patch_capabilities"):
        value = node.metadata.get(key, ())
        if isinstance(value, (tuple, list, set, frozenset)):
            native_capabilities.update(item for item in value if isinstance(item, str))
    if "update_table_cells" in native_capabilities:
        return ("update_table_cells",)
    return ()


def render_table(
    node: Node,
    payload: TablePayload,
    options: MarkdownProjectionOptions,
) -> RenderedNode:
    complex_table = any(
        cell.row_span != 1 or cell.column_span != 1 or cell.node_ids
        for cell in payload.cells
    )
    diagnostics: list[ProjectionDiagnostic] = []
    if complex_table:
        diagnostics.append(
            ProjectionDiagnostic(
                code="markdown.projection.table_lossy",
                severity="warning",
                message=(
                    "Complex table is rendered read-only because Markdown cannot "
                    "preserve its full structure."
                ),
                node_id=node.node_id,
            )
        )
    grid = [["" for _ in range(payload.columns)] for _ in range(payload.rows)]
    for cell in payload.cells:
        if 0 <= cell.row < payload.rows and 0 <= cell.column < payload.columns:
            grid[cell.row][cell.column] = user_text(cell.text or "", options)
    if not grid:
        return RenderedNode("", semantic_text_for_node(node), (), tuple(diagnostics))
    header = grid[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in grid[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return RenderedNode(
        "\n".join(lines),
        semantic_text_for_node(node),
        _table_edit_capabilities(node, payload),
        tuple(diagnostics),
    )


def render_chart(
    node: Node,
    payload: ChartPayload,
    options: MarkdownProjectionOptions,
) -> RenderedNode:
    del node
    title = user_text(payload.title or "Chart", options)
    lines = [f"### Chart: {title}"]
    values = ()
    if payload.series:
        candidate = payload.series[0].get("values", ())
        if isinstance(candidate, (tuple, list)):
            values = tuple(candidate)
    for index, category in enumerate(payload.categories):
        value = values[index] if index < len(values) else ""
        category_text = user_text(str(category), options)
        value_text = user_text(str(value), options)
        lines.append(f"- {category_text}: {value_text}")
    markdown = (
        "\n\n".join([lines[0], "\n".join(lines[1:])]) if len(lines) > 1 else lines[0]
    )
    return RenderedNode(markdown, payload.title or "", ())
