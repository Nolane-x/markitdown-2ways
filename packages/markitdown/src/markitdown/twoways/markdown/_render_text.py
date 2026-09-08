from __future__ import annotations

from ..ir.nodes import ImagePayload, Node, TextPayload
from .identity import escape_marker_like_text
from .model import MarkdownProjectionOptions
from ._render_model import RenderedNode
from .semantics import semantic_text_for_node


def user_text(text: str, options: MarkdownProjectionOptions) -> str:
    return escape_marker_like_text(text) if options.mode.value == "identity" else text


def _run_markdown(text: str, style, options: MarkdownProjectionOptions) -> str:
    text = user_text(text, options)
    if style is None:
        return text
    direct = style.direct
    if direct.get("code"):
        text = f"`{text}`"
    if direct.get("bold"):
        text = f"**{text}**"
    if direct.get("italic"):
        text = f"*{text}*"
    return text


def render_text(
    node: Node,
    payload: TextPayload,
    options: MarkdownProjectionOptions,
) -> RenderedNode:
    if payload.paragraphs:
        rendered_paragraphs = [
            "".join(
                _run_markdown(run.text, run.style, options)
                for run in paragraph.runs
            )
            for paragraph in payload.paragraphs
        ]
        body = "\n\n".join(rendered_paragraphs)
    else:
        body = user_text(payload.text, options)

    role = (node.semantic_role or "").lower()
    if role == "title":
        body = f"# {body}"
    elif role.startswith("heading") or role.startswith("section_heading"):
        digits = "".join(character for character in role if character.isdigit())
        level = min(max(int(digits) if digits else 2, 1), 6)
        body = f"{'#' * level} {body}"
    elif role == "code":
        body = f"```\n{body}\n```"
    return RenderedNode(body, semantic_text_for_node(node), ("replace_text",))


def render_image(
    node: Node,
    payload: ImagePayload,
    options: MarkdownProjectionOptions,
) -> RenderedNode:
    del node
    alt = user_text(payload.alt_text or "", options)
    return RenderedNode(
        f"![{alt}]({options.resource_uri_scheme}:{payload.resource_id})",
        payload.alt_text or "",
        ("set_alt_text",),
    )
