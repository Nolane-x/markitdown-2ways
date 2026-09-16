from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.formats.ipynb.reader import read_ipynb_ir
from markitdown.twoways.formats.ipynb.writer import patch_ipynb
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest


def _source():
    return (
        b'{"cells":[{"cell_type":"markdown","id":"m1","metadata":{},'
        b'"source":["hello\\n","world"]}],"metadata":{},'
        b'"nbformat":4,"nbformat_minor":5}'
    )


def _source_node(document):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("ipynb.source_pointer") is not None
    )


def _edit(document, value, *, operation_id="edit-1", precondition=True):
    node = _source_node(document)
    condition = None
    if precondition:
        condition = EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=node.payload.text,
        )
    return EditOperation(
        operation_id=operation_id,
        type="replace_ipynb_cell_source",
        target_node_id=node.node_id,
        precondition=condition,
        payload={"value": value},
    )


def test_zero_edit_patch_is_byte_identical() -> None:
    source = _source()
    document = read_ipynb_ir(BytesIO(source), filename="book.ipynb")
    output = BytesIO()

    result = patch_ipynb(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.format == "ipynb"
    assert result.mode == "patch"
    assert result.bytes_written == len(source)
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_source_authority_mismatch_fails_before_output() -> None:
    source = _source()
    document = read_ipynb_ir(BytesIO(source), filename="book.ipynb")
    assert document.source is not None

    output = BytesIO()
    with pytest.raises(SourcePackageMismatchError):
        patch_ipynb(document, BytesIO(source + b"\n"), output, edits=())
    assert output.getvalue() == b""

    output = BytesIO()
    forged = replace(
        document,
        source=replace(document.source, size_bytes=len(source) + 1),
    )
    with pytest.raises(SourcePackageMismatchError):
        patch_ipynb(forged, BytesIO(source), output, edits=())
    assert output.getvalue() == b""


def test_forged_source_pointer_fails_before_lowering() -> None:
    source = _source()
    document = read_ipynb_ir(BytesIO(source), filename="book.ipynb")
    node = _source_node(document)
    metadata = dict(node.metadata)
    metadata["ipynb.source_pointer"] = "/cells/9/source"
    nodes = dict(document.nodes)
    nodes[node.node_id] = replace(node, metadata=metadata)
    forged = replace(document, nodes=nodes)
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_ipynb(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(document, "changed"),),
        )
    assert output.getvalue() == b""


@pytest.mark.parametrize(
    "edit_factory",
    [
        lambda document: replace(_edit(document, "changed"), type="replace_text"),
        lambda document: replace(_edit(document, "changed"), payload={}),
        lambda document: replace(_edit(document, "changed"), payload={"value": 7}),
        lambda document: EditOperation(
            operation_id="missing",
            type="replace_ipynb_cell_source",
            target_node_id="missing",
            payload={"value": "changed"},
        ),
    ],
)
def test_invalid_edit_contract_fails_before_output(edit_factory) -> None:
    source = _source()
    document = read_ipynb_ir(BytesIO(source), filename="book.ipynb")
    output = BytesIO()

    with pytest.raises((PatchPreconditionError, UnsupportedEditError)):
        patch_ipynb(
            document,
            BytesIO(source),
            output,
            edits=(edit_factory(document),),
        )
    assert output.getvalue() == b""


def test_duplicate_noop_and_stale_precondition_fail_before_output() -> None:
    source = _source()
    document = read_ipynb_ir(BytesIO(source), filename="book.ipynb")

    output = BytesIO()
    with pytest.raises(UnsupportedEditError):
        patch_ipynb(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(document, "changed", operation_id="a"),
                _edit(document, "changed again", operation_id="b"),
            ),
        )
    assert output.getvalue() == b""

    output = BytesIO()
    with pytest.raises(UnsupportedEditError):
        patch_ipynb(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "hello\nworld"),),
        )
    assert output.getvalue() == b""

    output = BytesIO()
    stale = replace(
        _edit(document, "changed"),
        precondition=EditPrecondition(expected_old_value="stale"),
    )
    with pytest.raises(PatchPreconditionError):
        patch_ipynb(document, BytesIO(source), output, edits=(stale,))
    assert output.getvalue() == b""
