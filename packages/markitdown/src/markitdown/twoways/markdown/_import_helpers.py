from __future__ import annotations

from hashlib import sha256
import re

from .._errors import MarkdownIdentityError, MarkdownImportError
from ..ir.nodes import ImagePayload, TablePayload
from .identity import ParsedMarker, parse_marker_line, unescape_marker_like_text
from .model import ProjectionBlock
from .rendering import normalize_markdown_block

_IMAGE_RE = re.compile(r"^!\[(.*)\]\(([^)]+)\)$", re.DOTALL)
_BOLD_RE = re.compile(r"\*\*(.*?)\*\*", re.DOTALL)
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.*?)\*(?!\*)", re.DOTALL)
_CODE_RE = re.compile(r"`([^`]*)`", re.DOTALL)


def raise_identity(code: str, message: str, **details) -> None:
    raise MarkdownIdentityError(message, details=details, code=code)


def raise_import(code: str, message: str, **details) -> None:
    raise MarkdownImportError(message, details=details, code=code)


def block_digest(text: str) -> str:
    return sha256(normalize_markdown_block(text).encode("utf-8")).hexdigest()


def _strip_inline_markdown(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        text = _BOLD_RE.sub(lambda match: match.group(1), text)
        text = _ITALIC_RE.sub(lambda match: match.group(1), text)
        text = _CODE_RE.sub(lambda match: match.group(1), text)
    return unescape_marker_like_text(text)


def parse_text_block(block_text: str, block: ProjectionBlock) -> str:
    normalized = normalize_markdown_block(block_text)
    if block.node_kind == "note":
        lines = normalized.splitlines()
        if not lines or lines[0].strip() != "### Notes":
            raise_import(
                "markdown.semantic.parse_error",
                "Note block no longer matches the supported identity Markdown structure.",
                projection_id=block.projection_id,
            )
        normalized = "\n".join(lines[1:]).lstrip("\n")
    else:
        role = (block.semantic_role or "").lower()
        if role == "title":
            if not normalized.startswith("# "):
                raise_import(
                    "markdown.semantic.parse_error",
                    "Title block no longer has the supported heading structure.",
                    projection_id=block.projection_id,
                )
            normalized = normalized[2:]
        elif role.startswith("heading") or role.startswith("section_heading"):
            lines = normalized.splitlines()
            if not lines or not re.match(r"^#{1,6} ", lines[0]):
                raise_import(
                    "markdown.semantic.parse_error",
                    "Heading block no longer has the supported heading structure.",
                    projection_id=block.projection_id,
                )
            lines[0] = re.sub(r"^#{1,6} ", "", lines[0], count=1)
            normalized = "\n".join(lines)
        elif role == "code":
            if not (normalized.startswith("```\n") and normalized.endswith("\n```")):
                raise_import(
                    "markdown.semantic.parse_error",
                    "Code block no longer has the supported fenced structure.",
                    projection_id=block.projection_id,
                )
            normalized = normalized[4:-4]

    paragraphs = re.split(r"\n\s*\n", normalized) if normalized else [""]
    return "\n".join(_strip_inline_markdown(part) for part in paragraphs)


def parse_image_block(
    block_text: str, block: ProjectionBlock, original_node
) -> tuple[str, str]:
    normalized = normalize_markdown_block(block_text)
    match = _IMAGE_RE.fullmatch(normalized)
    if match is None:
        raise_import(
            "markdown.semantic.parse_error",
            "Image block no longer matches the supported Markdown image structure.",
            projection_id=block.projection_id,
        )
    alt_text, target = match.groups()
    alt_text = unescape_marker_like_text(alt_text)
    payload = original_node.payload
    if not isinstance(payload, ImagePayload):
        raise_identity(
            "markdown.marker.metadata_mismatch",
            "Manifest image identity does not point to an image payload.",
            projection_id=block.projection_id,
        )
    if not target.endswith(f":{payload.resource_id}"):
        raise_import(
            "markdown.edit.unsupported",
            "Changing the image resource target is not supported by identity Markdown v1.",
            projection_id=block.projection_id,
            target=target,
        )
    return alt_text, target


def _parse_table_row(
    line: str, *, columns: int, block: ProjectionBlock
) -> tuple[str, ...]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        raise_import(
            "markdown.semantic.parse_error",
            "Table row no longer matches the supported identity Markdown structure.",
            projection_id=block.projection_id,
        )
    parts = stripped.split("|")
    if parts[0] or parts[-1] or len(parts) != columns + 2:
        raise_import(
            "markdown.semantic.parse_error",
            "Table row column count changed in identity Markdown.",
            projection_id=block.projection_id,
        )
    return tuple(unescape_marker_like_text(item.strip()) for item in parts[1:-1])


def parse_table_block(
    block_text: str, block: ProjectionBlock, original_node
) -> tuple[tuple[str, ...], ...]:
    payload = original_node.payload
    if not isinstance(payload, TablePayload):
        raise_identity(
            "markdown.marker.metadata_mismatch",
            "Manifest table identity does not point to a table payload.",
            projection_id=block.projection_id,
        )
    if payload.rows <= 0 or payload.columns <= 0:
        raise_import(
            "markdown.semantic.parse_error",
            "Editable identity Markdown tables require a non-empty rectangular grid.",
            projection_id=block.projection_id,
        )

    lines = normalize_markdown_block(block_text).splitlines()
    if len(lines) != payload.rows + 1:
        raise_import(
            "markdown.semantic.parse_error",
            "Table row count changed in identity Markdown.",
            projection_id=block.projection_id,
        )

    header = _parse_table_row(lines[0], columns=payload.columns, block=block)
    separator = _parse_table_row(lines[1], columns=payload.columns, block=block)
    if any(item != "---" for item in separator):
        raise_import(
            "markdown.semantic.parse_error",
            "Table separator row changed in identity Markdown.",
            projection_id=block.projection_id,
        )
    rows = [header]
    rows.extend(
        _parse_table_row(line, columns=payload.columns, block=block)
        for line in lines[2:]
    )
    if len(rows) != payload.rows:
        raise_import(
            "markdown.semantic.parse_error",
            "Table row count changed in identity Markdown.",
            projection_id=block.projection_id,
        )
    return tuple(rows)


def operation_id(projection_id: str, edit_type: str, value: str) -> str:
    value_digest = sha256(value.encode("utf-8")).hexdigest()
    material = f"{projection_id}\0{edit_type}\0{value_digest}".encode("utf-8")
    return "edit_" + sha256(material).hexdigest()[:24]


def scan_markers(
    markdown: str, *, strict: bool
) -> tuple[list[str], list[tuple[int, ParsedMarker]]]:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    markers: list[tuple[int, ParsedMarker]] = []
    for index, line in enumerate(lines):
        marker = parse_marker_line(line, strict=strict)
        if marker is not None:
            markers.append((index, marker))
    return lines, markers
