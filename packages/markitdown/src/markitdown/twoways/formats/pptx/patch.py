from __future__ import annotations

from ..._errors import PatchPreconditionError
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import Node
from ...ir.semantics import (
    native_locator_digest,
    node_semantic_digest,
    node_semantic_text,
)


def _precondition_failure(reason: str, *, edit: EditOperation, actual: object) -> None:
    raise PatchPreconditionError(
        "PPTX edit precondition failed.",
        details={
            "reason": reason,
            "operation_id": edit.operation_id,
            "target_node_id": edit.target_node_id,
            "actual": actual,
        },
    )


def validate_edit_preconditions(
    document: DocumentIR,
    node: Node,
    edit: EditOperation,
) -> None:
    if edit.target_node_id != node.node_id or document.nodes.get(node.node_id) is None:
        _precondition_failure("target_mismatch", edit=edit, actual=node.node_id)
    precondition = edit.precondition
    if precondition is None:
        return
    if precondition.expected_semantic_digest is not None:
        actual = node_semantic_digest(node)
        if actual != precondition.expected_semantic_digest:
            _precondition_failure("semantic_digest", edit=edit, actual=actual)
    if precondition.expected_native_locator_digest is not None:
        actual = native_locator_digest(node)
        if actual != precondition.expected_native_locator_digest:
            _precondition_failure("native_locator_digest", edit=edit, actual=actual)
    if precondition.expected_old_value is not None:
        actual = node_semantic_text(node)
        if actual != precondition.expected_old_value:
            _precondition_failure("old_value", edit=edit, actual=actual)


def patch_picture_alt_text(shape_element, *, new_alt_text: str) -> None:
    from ..._errors import UnsupportedEditError

    c_nv_pr_nodes = shape_element.xpath('.//*[local-name()="cNvPr"]')
    if len(c_nv_pr_nodes) != 1:
        raise UnsupportedEditError(
            "PPTX picture does not expose one unambiguous cNvPr element.",
            details={"reason": "unsupported_picture_structure"},
        )
    c_nv_pr_nodes[0].set("descr", new_alt_text)
