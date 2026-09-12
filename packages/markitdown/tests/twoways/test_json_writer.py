from __future__ import annotations

import codecs
from dataclasses import replace
from io import BytesIO
import math

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.formats.json.reader import read_json_ir
from markitdown.twoways.formats.json.writer import patch_json
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.provenance import NativeLocator
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest


def _node(document, pointer):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("json.pointer") == pointer
    )


def _edit(document, pointer, value, *, operation_id="edit-1") -> EditOperation:
    node = _node(document, pointer)
    return EditOperation(
        operation_id=operation_id,
        type="replace_json_scalar",
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
        ),
        payload={"value": value},
    )


def _replace_node(document, node):
    nodes = dict(document.nodes)
    nodes[node.node_id] = node
    return replace(document, nodes=nodes)


def test_zero_edit_patch_is_byte_identical() -> None:
    source = codecs.BOM_UTF8 + b'{"name":"Ada", "n":1e2}\r\n'
    document = read_json_ir(BytesIO(source), filename="data.json")
    output = BytesIO()

    result = patch_json(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.format == "json"
    assert result.mode == "patch"
    assert result.bytes_written == len(source)
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_source_digest_mismatch_fails_before_output() -> None:
    source = b'{"name":"Ada"}\n'
    document = read_json_ir(BytesIO(source), filename="data.json")
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError):
        patch_json(document, BytesIO(b'{"name":"Bob"}\n'), output, edits=())

    assert output.getvalue() == b""


def test_source_size_metadata_mismatch_fails_before_output() -> None:
    source = b'{"name":"Ada"}\n'
    document = read_json_ir(BytesIO(source), filename="data.json")
    assert document.source is not None
    forged = replace(
        document,
        source=replace(document.source, size_bytes=len(source) + 1),
    )
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError, match="size"):
        patch_json(forged, BytesIO(source), output, edits=())

    assert output.getvalue() == b""


def test_string_scalar_is_replaced_by_its_exact_lexical_span() -> None:
    source = b'{ "name" : "Ada", "keep" : [ 1, 2 ] }\n'
    document = read_json_ir(BytesIO(source), filename="data.json")
    output = BytesIO()

    patch_json(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "/name", 'A"B\nC'),),
    )

    assert output.getvalue() == b'{ "name" : "A\\"B\\nC", "keep" : [ 1, 2 ] }\n'


@pytest.mark.parametrize(
    ("source", "pointer", "value", "expected"),
    [
        (b'{"v":1}', "/v", 42, b'{"v":42}'),
        (b'{"v":1}', "/v", -12.5, b'{"v":-12.5}'),
        (b'{"v":true}', "/v", False, b'{"v":false}'),
        (b'{"v":"x"}', "/v", None, b'{"v":null}'),
        (b'{"v":null}', "/v", "x", b'{"v":"x"}'),
        (b"1", "", "root", b'"root"'),
    ],
)
def test_scalar_types_and_type_changes_are_supported(
    source, pointer, value, expected
) -> None:
    document = read_json_ir(BytesIO(source), filename="data.json")
    output = BytesIO()

    patch_json(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, pointer, value),),
    )

    assert output.getvalue() == expected


def test_multiple_targets_are_patched_without_offset_corruption() -> None:
    source = b'{"a":"x","middle":[1,2],"b":100,"tail":true}\n'
    document = read_json_ir(BytesIO(source), filename="data.json")
    output = BytesIO()

    patch_json(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(document, "/b", -7, operation_id="edit-b"),
            _edit(document, "/a", "a much longer value", operation_id="edit-a"),
            _edit(document, "/tail", None, operation_id="edit-tail"),
        ),
    )

    assert (
        output.getvalue()
        == b'{"a":"a much longer value","middle":[1,2],"b":-7,"tail":null}\n'
    )


@pytest.mark.parametrize(
    ("source", "pointer", "value"),
    [
        (b'{"v":"same"}', "/v", "same"),
        (b'{"v":true}', "/v", True),
        (b'{"v":null}', "/v", None),
        (b'{"v":1e2}', "/v", 100),
        (b'{"v":100.0}', "/v", 100),
    ],
)
def test_semantic_noop_is_rejected_before_output(source, pointer, value) -> None:
    document = read_json_ir(BytesIO(source), filename="data.json")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="semantic"):
        patch_json(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, pointer, value),),
        )

    assert output.getvalue() == b""


@pytest.mark.parametrize("value", [[], {}, [1], {"x": 1}])
def test_structural_replacement_values_are_rejected(value) -> None:
    source = b'{"v":1}'
    document = read_json_ir(BytesIO(source), filename="data.json")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_json(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "/v", value),),
        )

    assert output.getvalue() == b""


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_float_replacements_are_rejected(value) -> None:
    source = b'{"v":1}'
    document = read_json_ir(BytesIO(source), filename="data.json")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="finite"):
        patch_json(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "/v", value),),
        )

    assert output.getvalue() == b""


def test_container_target_is_read_only() -> None:
    source = b'{"arr":[1,2]}'
    document = read_json_ir(BytesIO(source), filename="data.json")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_json(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "/arr", "not-an-array"),),
        )

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"value": 2, "unexpected": True},
        {"unexpected": 2},
    ],
)
def test_malformed_edit_payload_fails_closed(payload) -> None:
    source = b'{"v":1}'
    document = read_json_ir(BytesIO(source), filename="data.json")
    node = _node(document, "/v")
    output = BytesIO()
    edit = EditOperation(
        operation_id="bad-payload",
        type="replace_json_scalar",
        target_node_id=node.node_id,
        payload=payload,
    )

    with pytest.raises(UnsupportedEditError):
        patch_json(document, BytesIO(source), output, edits=(edit,))

    assert output.getvalue() == b""


def test_wrong_edit_type_fails_closed() -> None:
    source = b'{"v":1}'
    document = read_json_ir(BytesIO(source), filename="data.json")
    node = _node(document, "/v")
    output = BytesIO()
    edit = EditOperation(
        operation_id="wrong-type",
        type="replace_text",
        target_node_id=node.node_id,
        payload={"value": 2},
    )

    with pytest.raises(UnsupportedEditError):
        patch_json(document, BytesIO(source), output, edits=(edit,))

    assert output.getvalue() == b""


def test_unknown_target_fails_closed() -> None:
    source = b'{"v":1}'
    document = read_json_ir(BytesIO(source), filename="data.json")
    output = BytesIO()
    edit = EditOperation(
        operation_id="missing-target",
        type="replace_json_scalar",
        target_node_id="not-a-json-node",
        payload={"value": 2},
    )

    with pytest.raises(PatchPreconditionError):
        patch_json(document, BytesIO(source), output, edits=(edit,))

    assert output.getvalue() == b""


def test_duplicate_target_edits_fail_closed() -> None:
    source = b'{"v":1}'
    document = read_json_ir(BytesIO(source), filename="data.json")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="duplicate"):
        patch_json(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(document, "/v", 2, operation_id="edit-1"),
                _edit(document, "/v", 3, operation_id="edit-2"),
            ),
        )

    assert output.getvalue() == b""


def test_stale_native_locator_is_rejected_against_actual_source() -> None:
    source = b'{"v":1}'
    document = read_json_ir(BytesIO(source), filename="data.json")
    node = _node(document, "/v")
    assert node.native_locator is not None
    forged_node = replace(
        node,
        native_locator=NativeLocator(
            backend="json",
            part_uri="/",
            object_id="value",
            path="/other",
        ),
    )
    forged = _replace_node(document, forged_node)
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_json(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged, "/v", 2),),
        )

    assert output.getvalue() == b""


def test_stale_source_span_is_rejected_against_actual_source() -> None:
    source = b'{"v":1}'
    document = read_json_ir(BytesIO(source), filename="data.json")
    node = _node(document, "/v")
    metadata = dict(node.metadata)
    metadata["json.char_start"] = metadata["json.char_start"] - 1
    forged = _replace_node(document, replace(node, metadata=metadata))
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_json(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged, "/v", 2),),
        )

    assert output.getvalue() == b""


def test_stale_raw_digest_is_rejected_against_actual_source() -> None:
    source = b'{"v":1}'
    document = read_json_ir(BytesIO(source), filename="data.json")
    node = _node(document, "/v")
    metadata = dict(node.metadata)
    metadata["json.raw_digest"] = "0" * 64
    forged = _replace_node(document, replace(node, metadata=metadata))
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_json(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged, "/v", 2),),
        )

    assert output.getvalue() == b""
