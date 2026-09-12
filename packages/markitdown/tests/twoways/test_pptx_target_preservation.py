from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways import RoundTripVerificationError
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import (
    native_locator_digest,
    node_semantic_digest,
    node_semantic_text,
)

from ._pptx_fixtures import make_pptx_bytes


def _precondition(node) -> EditPrecondition:
    return EditPrecondition(
        expected_semantic_digest=node_semantic_digest(node),
        expected_native_locator_digest=native_locator_digest(node),
        expected_old_value=node_semantic_text(node),
    )


def test_pptx_text_verifier_rejects_extra_native_target_mutation(monkeypatch):
    from markitdown.twoways.formats.pptx import patch_pptx, read_pptx_ir
    from markitdown.twoways.formats.pptx import writer as writer_module

    source = make_pptx_bytes()
    document = read_pptx_ir(BytesIO(source))
    node = next(
        item
        for item in document.nodes.values()
        if item.kind == "text" and item.payload.text == "Revenue 38%"
    )
    edit = EditOperation(
        operation_id="pptx-text-preservation",
        type="replace_text",
        target_node_id=node.node_id,
        precondition=_precondition(node),
        payload={"text": "Revenue 42%"},
    )
    original = writer_module.patch_text_shape

    def tampering_patch(shape_element, **kwargs):
        original(shape_element, **kwargs)
        shape_element.set("useBgFill", "1")

    monkeypatch.setattr(writer_module, "patch_text_shape", tampering_patch)
    output = BytesIO()
    with pytest.raises(RoundTripVerificationError) as exc:
        patch_pptx(document, BytesIO(source), output, edits=(edit,))
    assert exc.value.details["check"] == "native.target_structure"
    assert output.getvalue() == b""


def test_pptx_alt_text_verifier_rejects_extra_native_target_mutation(monkeypatch):
    from markitdown.twoways.formats.pptx import patch_pptx, read_pptx_ir
    from markitdown.twoways.formats.pptx import writer as writer_module

    source = make_pptx_bytes()
    document = read_pptx_ir(BytesIO(source))
    node = next(item for item in document.nodes.values() if item.kind == "image")
    edit = EditOperation(
        operation_id="pptx-alt-preservation",
        type="set_alt_text",
        target_node_id=node.node_id,
        precondition=_precondition(node),
        payload={"alt_text": "Updated revenue icon"},
    )
    original = writer_module.patch_picture_alt_text

    def tampering_patch(shape_element, **kwargs):
        original(shape_element, **kwargs)
        c_nv_pr = shape_element.xpath('.//*[local-name()="cNvPr"]')[0]
        c_nv_pr.set("name", "Tampered picture name")

    monkeypatch.setattr(writer_module, "patch_picture_alt_text", tampering_patch)
    output = BytesIO()
    with pytest.raises(RoundTripVerificationError) as exc:
        patch_pptx(document, BytesIO(source), output, edits=(edit,))
    assert exc.value.details["check"] == "native.target_structure"
    assert output.getvalue() == b""
