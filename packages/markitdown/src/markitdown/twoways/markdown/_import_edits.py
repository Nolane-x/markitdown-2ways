from __future__ import annotations

from ..ir.document import DocumentIR
from ..ir.edits import EditOperation, EditPrecondition
from ._import_helpers import (
    block_digest,
    operation_id,
    parse_image_block,
    parse_text_block,
    raise_identity,
    raise_import,
)
from ._import_integrity import IdentityEnvelope
from .model import MarkdownImportResult
from .rendering import semantic_text_for_node, source_semantic_digest


def generate_identity_edits(
    envelope: IdentityEnvelope,
    *,
    original_document: DocumentIR,
) -> MarkdownImportResult:
    edits: list[EditOperation] = []
    unchanged: list[str] = []
    parsed_blocks = envelope.parsed_blocks

    for offset, (line_index, marker) in enumerate(parsed_blocks):
        next_index = parsed_blocks[offset + 1][0] if offset + 1 < len(parsed_blocks) else len(envelope.lines)
        block_text = "\n".join(envelope.lines[line_index + 1:next_index])
        block = envelope.block_by_pid[marker.attributes["pid"]]
        original_node = original_document.nodes.get(block.node_id)
        if original_node is None or source_semantic_digest(original_node) != block.source_semantic_digest:
            raise_identity(
                "markdown.marker.metadata_mismatch",
                "Original node semantic identity no longer matches the projection manifest.",
                projection_id=block.projection_id,
                node_id=block.node_id,
            )
        if block_digest(block_text) == block.rendered_digest:
            unchanged.append(block.node_id)
            continue
        if not block.editable_capabilities:
            raise_import(
                "markdown.edit.read_only",
                "This projected block is read-only in identity Markdown v1.",
                projection_id=block.projection_id,
                node_id=block.node_id,
            )

        if "replace_text" in block.editable_capabilities:
            old_text = semantic_text_for_node(original_node)
            new_text = parse_text_block(block_text, block)
            if new_text == old_text:
                raise_import(
                    "markdown.edit.unsupported",
                    "Formatting-only changes are not silently discarded by identity Markdown v1.",
                    projection_id=block.projection_id,
                    node_id=block.node_id,
                )
            edits.append(
                EditOperation(
                    operation_id=operation_id(block.projection_id, "replace_text", new_text),
                    type="replace_text",
                    target_node_id=block.node_id,
                    precondition=EditPrecondition(
                        expected_semantic_digest=block.source_semantic_digest,
                        expected_native_locator_digest=block.native_locator_digest,
                        expected_old_value=old_text,
                    ),
                    payload={"text": new_text},
                    source_label="markdown.identity.v1",
                )
            )
            continue

        if "set_alt_text" in block.editable_capabilities:
            old_alt = semantic_text_for_node(original_node)
            new_alt, _ = parse_image_block(block_text, block, original_node)
            if new_alt == old_alt:
                raise_import(
                    "markdown.edit.unsupported",
                    "Non-alt-text image Markdown changes are not supported by identity Markdown v1.",
                    projection_id=block.projection_id,
                    node_id=block.node_id,
                )
            edits.append(
                EditOperation(
                    operation_id=operation_id(block.projection_id, "set_alt_text", new_alt),
                    type="set_alt_text",
                    target_node_id=block.node_id,
                    precondition=EditPrecondition(
                        expected_semantic_digest=block.source_semantic_digest,
                        expected_native_locator_digest=block.native_locator_digest,
                        expected_old_value=old_alt,
                    ),
                    payload={"alt_text": new_alt},
                    source_label="markdown.identity.v1",
                )
            )
            continue

        raise_import(
            "markdown.edit.unsupported",
            "No supported identity edit capability matched the changed block.",
            projection_id=block.projection_id,
        )

    return MarkdownImportResult(
        edits=tuple(edits),
        unchanged_node_ids=tuple(unchanged),
        diagnostics=envelope.diagnostics,
    )
