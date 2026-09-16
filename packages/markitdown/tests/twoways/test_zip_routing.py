from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.formats.zip.reader import read_zip_ir
from markitdown.twoways.formats.zip.writer import patch_zip
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest

from ._zip_fixtures import make_zip


def _node(document, pointer: str):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("json.pointer") == pointer
    )


def _edit_for_node(
    node,
    value: object,
    *,
    operation_id: str = "edit-1",
    expected_old_value: object | None = None,
) -> EditOperation:
    return EditOperation(
        operation_id=operation_id,
        type="replace_json_scalar",
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=expected_old_value,
        ),
        payload={"value": value},
    )


def _replace_node(document, node):
    nodes = dict(document.nodes)
    nodes[node.node_id] = node
    return replace(document, nodes=nodes)


def test_forged_member_chain_fails_before_output() -> None:
    source = make_zip(members={"data.json": b'{"name":"Ada"}'})
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    target = _node(document, "/name")
    metadata = dict(target.metadata)
    metadata["zip.member_chain"] = ("other.json",)
    forged_node = replace(target, metadata=metadata)
    forged = _replace_node(document, forged_node)
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_zip(
            forged,
            BytesIO(source),
            output,
            edits=(_edit_for_node(forged_node, "Nolane"),),
        )

    assert output.getvalue() == b""


def test_stale_root_source_fails_before_output() -> None:
    source = make_zip(members={"data.json": b'{"name":"Ada"}'})
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    target = _node(document, "/name")
    changed_source = make_zip(members={"data.json": b'{"name":"Bob"}'})
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError):
        patch_zip(
            document,
            BytesIO(changed_source),
            output,
            edits=(_edit_for_node(target, "Nolane"),),
        )

    assert output.getvalue() == b""


def test_stale_intermediate_member_digest_fails_before_output() -> None:
    nested = make_zip(members={"data.json": b'{"name":"Ada"}'})
    source = make_zip(members={"nested.zip": nested})
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    target = _node(document, "/name")
    member = next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "zip-member"
        and node.metadata.get("zip.member_chain") == ("nested.zip",)
    )
    member_metadata = dict(member.metadata)
    member_metadata["zip.member_sha256"] = "0" * 64
    forged = _replace_node(document, replace(member, metadata=member_metadata))
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_zip(
            forged,
            BytesIO(source),
            output,
            edits=(_edit_for_node(target, "Nolane"),),
        )

    assert output.getvalue() == b""


def test_adapter_reclassification_fails_before_output() -> None:
    source = make_zip(members={"data.json": b'{"name":"Ada"}'})
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    target = _node(document, "/name")
    metadata = dict(target.metadata)
    metadata["zip.adapter_key"] = "xlsx"
    forged_node = replace(target, metadata=metadata)
    forged = _replace_node(document, forged_node)
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_zip(
            forged,
            BytesIO(source),
            output,
            edits=(_edit_for_node(forged_node, "Nolane"),),
        )

    assert output.getvalue() == b""


def test_unknown_target_fails_before_output() -> None:
    source = make_zip(members={"data.json": b'{"name":"Ada"}'})
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    output = BytesIO()
    edit = EditOperation(
        operation_id="missing-target",
        type="replace_json_scalar",
        target_node_id="missing-node",
        payload={"value": "Nolane"},
    )

    with pytest.raises(PatchPreconditionError):
        patch_zip(document, BytesIO(source), output, edits=(edit,))

    assert output.getvalue() == b""


def test_fresh_inner_read_only_target_fails_before_output() -> None:
    source = make_zip(members={"data.json": b'{"name":"Ada"}'})
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    root = _node(document, "")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_zip(
            document,
            BytesIO(source),
            output,
            edits=(_edit_for_node(root, "not-an-object"),),
        )

    assert output.getvalue() == b""


def test_duplicate_logical_target_fails_before_output() -> None:
    source = make_zip(members={"data.json": b'{"name":"Ada"}'})
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    target = _node(document, "/name")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_zip(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit_for_node(target, "Nolane", operation_id="edit-a"),
                _edit_for_node(target, "Other", operation_id="edit-b"),
            ),
        )

    assert output.getvalue() == b""


def test_contradictory_edits_fail_before_output() -> None:
    source = make_zip(members={"data.json": b'{"a":"A","b":"B"}'})
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    first = _node(document, "/a")
    second = _node(document, "/b")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_zip(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit_for_node(first, "AA", operation_id="same-id"),
                _edit_for_node(second, "BB", operation_id="same-id"),
            ),
        )

    assert output.getvalue() == b""
