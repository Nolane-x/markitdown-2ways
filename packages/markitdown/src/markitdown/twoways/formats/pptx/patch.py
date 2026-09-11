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
    _validate(document, node, edit, format_label="PPTX")


def patch_picture_alt_text(shape_element, *, new_alt_text: str) -> None:
    from ..._errors import UnsupportedEditError

    c_nv_pr_nodes = shape_element.xpath('.//*[local-name()="cNvPr"]')
    if len(c_nv_pr_nodes) != 1:
        raise UnsupportedEditError(
            "PPTX picture does not expose one unambiguous cNvPr element.",
            details={"reason": "unsupported_picture_structure"},
        )
    c_nv_pr_nodes[0].set("descr", new_alt_text)
