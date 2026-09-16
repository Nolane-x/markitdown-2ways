from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways._errors import PatchPreconditionError
from markitdown.twoways.formats.zip.reader import read_zip_ir
from markitdown.twoways.formats.zip.writer import patch_zip
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest

from ._zip_fixtures import make_zip


def _node(document, chain: tuple[str, ...], pointer: str = "/name"):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("zip.member_chain") == chain
        and node.metadata.get("json.pointer") == pointer
    )


def _edit(
    node,
    value: object,
    *,
    operation_id: str,
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


def _read_member(source: bytes, name: str) -> bytes:
    with ZipFile(BytesIO(source), "r") as archive:
        return archive.read(name)


def test_nested_json_edit_is_target_only_and_transactional() -> None:
    source = make_zip(
        members={
            "data.json": b'{"name":"Ada","count":1}\n',
            "note.txt": b"keep\n",
        }
    )
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    target = _node(document, ("data.json",))
    output = BytesIO()

    result = patch_zip(
        document,
        BytesIO(source),
        output,
        edits=(_edit(target, "Nolane", operation_id="edit-name"),),
    )

    candidate = output.getvalue()
    with ZipFile(BytesIO(candidate), "r") as archive:
        assert archive.read("data.json") == b'{"name":"Nolane","count":1}\n'
        assert archive.read("note.txt") == b"keep\n"
    assert result.fidelity.claimed_tier == "high"


def test_zip_zero_edit_write_is_exact_source_bytes() -> None:
    source = make_zip()
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    output = BytesIO()

    result = patch_zip(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.format == "zip"
    assert result.mode == "patch"
    assert result.bytes_written == len(source)
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_recursive_nested_json_edit_propagates_only_member_chain() -> None:
    nested = make_zip(
        members={
            "data.json": b'{"name":"Ada"}\n',
            "inner-keep.txt": b"inner-keep\n",
        }
    )
    source = make_zip(
        members={
            "nested.zip": nested,
            "outer-keep.txt": b"outer-keep\n",
        }
    )
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    target = _node(document, ("nested.zip", "data.json"))
    output = BytesIO()

    patch_zip(
        document,
        BytesIO(source),
        output,
        edits=(_edit(target, "Nolane", operation_id="nested-edit"),),
    )

    candidate = output.getvalue()
    assert _read_member(candidate, "outer-keep.txt") == b"outer-keep\n"
    candidate_nested = _read_member(candidate, "nested.zip")
    assert _read_member(candidate_nested, "data.json") == b'{"name":"Nolane"}\n'
    assert _read_member(candidate_nested, "inner-keep.txt") == b"inner-keep\n"


def test_edits_across_two_nested_branches_commit_as_one_transaction() -> None:
    first_zip = make_zip(
        members={"data.json": b'{"name":"A"}\n', "keep.txt": b"first\n"}
    )
    second_zip = make_zip(
        members={"data.json": b'{"name":"B"}\n', "keep.txt": b"second\n"}
    )
    source = make_zip(members={"a.zip": first_zip, "b.zip": second_zip})
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    first = _node(document, ("a.zip", "data.json"))
    second = _node(document, ("b.zip", "data.json"))
    output = BytesIO()

    patch_zip(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(first, "AA", operation_id="edit-a"),
            _edit(second, "BB", operation_id="edit-b"),
        ),
    )

    candidate = output.getvalue()
    candidate_a = _read_member(candidate, "a.zip")
    candidate_b = _read_member(candidate, "b.zip")
    assert _read_member(candidate_a, "data.json") == b'{"name":"AA"}\n'
    assert _read_member(candidate_b, "data.json") == b'{"name":"BB"}\n'
    assert _read_member(candidate_a, "keep.txt") == b"first\n"
    assert _read_member(candidate_b, "keep.txt") == b"second\n"


def test_one_inner_failure_rolls_back_all_sibling_edits() -> None:
    source = make_zip(
        members={
            "a.json": b'{"name":"A"}\n',
            "b.json": b'{"name":"B"}\n',
        }
    )
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")
    first = _node(document, ("a.json",))
    second = _node(document, ("b.json",))
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_zip(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(first, "AA", operation_id="good-edit"),
                _edit(
                    second,
                    "BB",
                    operation_id="stale-edit",
                    expected_old_value="stale",
                ),
            ),
        )

    assert output.getvalue() == b""
