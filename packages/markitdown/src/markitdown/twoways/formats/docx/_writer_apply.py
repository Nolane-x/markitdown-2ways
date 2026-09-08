from __future__ import annotations

from typing import Any, BinaryIO

from ..._errors import (
    PatchPreconditionError,
    UnsupportedEditError,
)
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import ImagePayload, TextPayload
from ...ir.semantics import node_semantic_text
from .locators import resolve_paragraph_element, resolve_picture_docpr
from .patch import patch_picture_alt_text, validate_edit_preconditions
from .text import patch_paragraph_text


def _apply_edit(
    root: Any, document: DocumentIR, edit: EditOperation, *, part_uri: str
) -> None:
    if edit.target_node_id is None or edit.target_node_id not in document.nodes:
        raise PatchPreconditionError(
            "DOCX edit target node does not exist in the source IR.",
            details={"reason": "missing_target", "target_node_id": edit.target_node_id},
        )
    node = document.nodes[edit.target_node_id]
    if node.native_locator is None:
        raise PatchPreconditionError(
            "DOCX edit target has no native locator.",
            details={
                "reason": "missing_native_locator",
                "target_node_id": node.node_id,
            },
        )
    validate_edit_preconditions(document, node, edit)

    if edit.type == "replace_text":
        if not isinstance(node.payload, TextPayload):
            raise UnsupportedEditError(
                "replace_text requires a DOCX text node.",
                details={"reason": "wrong_node_kind", "target_node_id": node.node_id},
            )
        if node.metadata.get("docx:patch_text_compatible") is not True:
            raise UnsupportedEditError(
                "DOCX paragraph structure is read-only in Phase D v1.",
                details={
                    "reason": "unsupported_text_structure",
                    "target_node_id": node.node_id,
                },
            )
        new_text = edit.payload.get("text")
        if not isinstance(new_text, str):
            raise UnsupportedEditError(
                "replace_text requires payload.text string.",
                details={"reason": "invalid_payload"},
            )
        paragraph = resolve_paragraph_element(
            root,
            node.native_locator,
            part_uri=part_uri,
        )
        patch_paragraph_text(
            paragraph,
            old_text=node_semantic_text(node),
            new_text=new_text,
        )
        return

    if edit.type == "set_alt_text":
        if not isinstance(node.payload, ImagePayload):
            raise UnsupportedEditError(
                "set_alt_text requires a DOCX image node.",
                details={"reason": "wrong_node_kind", "target_node_id": node.node_id},
            )
        new_alt = edit.payload.get("alt_text")
        if not isinstance(new_alt, str):
            raise UnsupportedEditError(
                "set_alt_text requires payload.alt_text string.",
                details={"reason": "invalid_payload"},
            )
        docpr = resolve_picture_docpr(root, node.native_locator, part_uri=part_uri)
        patch_picture_alt_text(docpr, new_alt_text=new_alt)
        return

    raise UnsupportedEditError(
        "Phase D v1 supports only replace_text and set_alt_text.",
        details={"reason": "unsupported_edit_type", "edit_type": edit.type},
    )
