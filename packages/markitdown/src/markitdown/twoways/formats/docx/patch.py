from __future__ import annotations

from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import Node
from ...ir.semantics import validate_edit_preconditions as _validate


def validate_edit_preconditions(
    document: DocumentIR,
    node: Node,
    edit: EditOperation,
) -> None:
    _validate(document, node, edit, format_label="DOCX")


def patch_picture_alt_text(docpr_element, *, new_alt_text: str) -> None:
    docpr_element.set("descr", new_alt_text)
