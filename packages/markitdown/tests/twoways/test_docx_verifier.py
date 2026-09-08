from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile

from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import (
    native_locator_digest,
    node_semantic_digest,
    node_semantic_text,
)

from ._docx_fixtures import build_docx_fixture


def _node_edit(node, edit_type: str, value: str) -> EditOperation:
    key = "text" if edit_type == "replace_text" else "alt_text"
    return EditOperation(
        operation_id=f"docx-{edit_type}-{node.node_id}",
        type=edit_type,
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=node_semantic_text(node),
        ),
        payload={key: value},
    )


def _member_bytes(data: bytes) -> dict[str, bytes]:
    with ZipFile(BytesIO(data), "r") as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _patch(source: bytes, document, edits):
    from markitdown.twoways.formats.docx import patch_docx

    output = BytesIO()
    result = patch_docx(document, BytesIO(source), output, edits=edits)
    return output.getvalue(), result


def _replace_zip_member(source: bytes, member: str, replacement: bytes) -> bytes:
    from zipfile import ZipInfo

    output = BytesIO()
    with ZipFile(BytesIO(source), "r") as original, ZipFile(output, "w") as target:
        for info in original.infolist():
            data = replacement if info.filename == member else original.read(info)
            clone = ZipInfo(info.filename, info.date_time)
            clone.compress_type = info.compress_type
            clone.external_attr = info.external_attr
            clone.internal_attr = info.internal_attr
            clone.extra = info.extra
            clone.comment = info.comment
            target.writestr(clone, data)
    return output.getvalue()


def test_verifier_rejects_unrelated_native_subtree_mutation():
    import pytest

    from markitdown.twoways._errors import RoundTripVerificationError
    from markitdown.twoways.formats.docx import read_docx_ir
    from markitdown.twoways.formats.docx.model import DocxPatchOptions
    from markitdown.twoways.formats.docx.verify import verify_docx_output
    from markitdown.twoways.ooxml import parse_xml_part, serialize_xml_part

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    node = document.nodes[document.canvases[0].root_node_ids[0]]
    edit = _node_edit(node, "replace_text", "Revenue 42%")

    from markitdown.twoways.formats.docx import patch_docx

    unverified = BytesIO()
    patch_docx(
        document,
        BytesIO(source),
        unverified,
        edits=(edit,),
        options=DocxPatchOptions(verify_output=False),
    )
    output = unverified.getvalue()
    members = _member_bytes(output)
    root = parse_xml_part(members["word/document.xml"])
    paragraphs = root.xpath(
        '/*[local-name()="document"]/*[local-name()="body"]/*[local-name()="p"]'
    )
    paragraphs[1].set(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rsidR",
        "DEADBEEF",
    )
    corrupted = _replace_zip_member(
        output,
        "word/document.xml",
        serialize_xml_part(root),
    )
    with pytest.raises(RoundTripVerificationError) as exc:
        verify_docx_output(
            document,
            source,
            corrupted,
            edits=(edit,),
            touched_parts=("word/document.xml",),
            limits=DocxPatchOptions().limits,
        )
    assert exc.value.details["check"] == "docx.native.unrelated_subtrees"


def test_verifier_evidence_covers_native_relationships_and_media():
    from markitdown.twoways.formats.docx import read_docx_ir

    source = build_docx_fixture()
    document = read_docx_ir(BytesIO(source))
    node = document.nodes[document.canvases[0].root_node_ids[0]]
    _, result = _patch(
        source, document, (_node_edit(node, "replace_text", "Revenue 42%"),)
    )
    codes = {item.check_code for item in result.fidelity.evidence}
    assert "docx.native.unrelated_subtrees" in codes
    assert "docx.native.target_structure" in codes
    assert "docx.hyperlinks.relationships" in codes
    assert "docx.media.unchanged" in codes
    assert "docx.reopen" in codes
