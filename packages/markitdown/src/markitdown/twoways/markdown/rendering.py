from __future__ import annotations

from ..ir.nodes import ChartPayload, ImagePayload, Node, TablePayload, TextPayload
from .model import MarkdownProjectionOptions
from ._render_model import RenderedNode
from ._render_structured import render_chart, render_table
from ._render_text import render_image, render_text, user_text
from .semantics import (
    native_locator_digest,
    normalize_markdown_block,
    semantic_text_for_node,
    source_semantic_digest,
    stable_digest,
)

__all__ = [
    "RenderedNode",
    "native_locator_digest",
    "normalize_markdown_block",
    "render_node",
    "semantic_text_for_node",
    "source_semantic_digest",
    "stable_digest",
]


def render_node(
    node: Node,
    options: MarkdownProjectionOptions,
) -> RenderedNode | None:
    if node.kind == "text" and isinstance(node.payload, TextPayload):
        return render_text(node, node.payload, options)
    if node.kind == "note" and isinstance(node.payload, TextPayload):
        if not options.include_notes:
            return None
        body = user_text(semantic_text_for_node(node), options)
        return RenderedNode(
            f"### Notes\n\n{body}",
            semantic_text_for_node(node),
            ("replace_text",),
        )
    if node.kind == "image" and isinstance(node.payload, ImagePayload):
        return render_image(node, node.payload, options)
    if node.kind == "table" and isinstance(node.payload, TablePayload):
        return render_table(node, node.payload, options)
    if node.kind == "chart" and isinstance(node.payload, ChartPayload):
        return render_chart(node, node.payload, options)
    if node.kind == "unknown_native":
        if options.include_unknown_placeholders:
            return RenderedNode(
                f"[Unsupported native content: {node.node_id}]", "", ()
            )
        return None
    if node.kind == "shape":
        if isinstance(node.payload, TextPayload):
            return render_text(node, node.payload, options)
        return None
    return None
