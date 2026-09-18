from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.formats.msg import patch_msg, read_msg_ir
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest

from ._msg_fixtures import make_msg_cfb


def _subject_node(document):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "msg-subject-text"
    )


def _edit(
    document,
    value: str,
    *,
    old_value: str | None = None,
    operation_type: str = "update_msg_subject_text",
    property_tag: int = 0x0037001F,
) -> EditOperation:
    node = _subject_node(document)
    expected_old = node.payload.text if old_value is None else old_value
    return EditOperation(
        operation_id="edit-subject",
        type=operation_type,
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=expected_old,
        ),
        payload={
            "property_tag": property_tag,
            "old_value": expected_old,
            "value": value,
        },
    )


def test_zero_edit_preserves_source_bytes_exactly() -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    output = BytesIO()

    result = patch_msg(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.format == "msg"
    assert result.mode == "patch"
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_semantic_noop_preserves_source_bytes_exactly() -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    output = BytesIO()

    result = patch_msg(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "Alpha"),),
    )

    assert output.getvalue() == source
    assert result.fidelity.claimed_tier == "exact-preserve"


@pytest.mark.parametrize("value", ("Bravo", "Ωlpha"))
def test_equal_encoded_length_subject_replacement(value: str) -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    node = _subject_node(document)
    output = BytesIO()

    patch_msg(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, value),),
    )

    candidate = output.getvalue()
    reread = read_msg_ir(BytesIO(candidate), filename="mail.msg")
    assert len(candidate) == len(source)
    assert _subject_node(reread).payload.text == value

    ranges = node.metadata["msg.subject_physical_ranges"]
    logical = b"".join(
        candidate[item["start"] : item["start"] + item["length"]]
        for item in ranges
    )
    assert logical == value.encode("utf-16-le")


def test_size_change_fails_without_output() -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="size|length|allocation"):
        patch_msg(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "Beta"),),
        )

    assert output.getvalue() == b""


def test_embedded_nul_fails_without_output() -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="NUL"):
        patch_msg(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "A\x00pha"),),
        )

    assert output.getvalue() == b""


def test_source_digest_mismatch_fails_without_output() -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    different = make_msg_cfb(subject="Omega").data
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError):
        patch_msg(document, BytesIO(different), output, edits=())

    assert output.getvalue() == b""


def test_source_size_mismatch_fails_without_output() -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    assert document.source is not None
    forged = replace(
        document,
        source=replace(document.source, size_bytes=len(source) + 1),
    )
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError, match="size"):
        patch_msg(forged, BytesIO(source), output, edits=())

    assert output.getvalue() == b""


def test_stale_old_value_fails_without_output() -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="old|stale"):
        patch_msg(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "Bravo", old_value="stale"),),
        )

    assert output.getvalue() == b""


def test_duplicate_target_fails_without_output() -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="duplicate"):
        patch_msg(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(document, "Bravo"),
                _edit(document, "Delta"),
            ),
        )

    assert output.getvalue() == b""


def test_wrong_operation_fails_without_output() -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="update_msg_subject_text|operation"):
        patch_msg(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "Bravo", operation_type="replace_text"),),
        )

    assert output.getvalue() == b""


def test_property_tag_is_immutable() -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="property|tag|immutable"):
        patch_msg(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "Bravo", property_tag=0x0037001E),),
        )

    assert output.getvalue() == b""


def test_stale_subject_stream_digest_fails_without_output() -> None:
    source = make_msg_cfb(subject="Alpha").data
    document = read_msg_ir(BytesIO(source), filename="mail.msg")
    node = _subject_node(document)
    forged_node = replace(
        node,
        metadata={**node.metadata, "msg.subject_stream_sha256": "0" * 64},
    )
    forged = replace(
        document,
        nodes={**document.nodes, node.node_id: forged_node},
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="stale|forged|digest|owner"):
        patch_msg(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged, "Bravo"),),
        )

    assert output.getvalue() == b""
