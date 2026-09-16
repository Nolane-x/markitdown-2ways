from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways._errors import UnsupportedEditError
from markitdown.twoways.formats.ipynb.reader import read_ipynb_ir
from markitdown.twoways.formats.ipynb.writer import patch_ipynb
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest


def _source_node(document, index):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("ipynb.cell_index") == index
        and node.metadata.get("ipynb.source_pointer") is not None
    )


def _edit(document, index, value, operation_id):
    node = _source_node(document, index)
    return EditOperation(
        operation_id=operation_id,
        type="replace_ipynb_cell_source",
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=node.payload.text,
        ),
        payload={"value": value},
    )


def _source():
    return (
        b'{"cells":['
        b'{"cell_type":"markdown","id":"m1","metadata":{"tags":["keep"]},'
        b'"attachments":{"a.txt":{"text/plain":"YQ=="}},'
        b'"source":["hello\\n","world"]},'
        b'{"cell_type":"code","execution_count":7,"metadata":{"x":1},'
        b'"outputs":[{"output_type":"stream","name":"stdout","text":["ok\\n"]}],'
        b'"source":"print(1)"},'
        b'{"cell_type":"raw","metadata":{},"source":["raw\\n"]}'
        b'],"metadata":{"kernelspec":{"name":"python3"}},'
        b'"nbformat":4,"nbformat_minor":5}'
    )


def test_mutation_is_target_only_and_preserves_unrelated_notebook_bytes() -> None:
    source = _source()
    document = read_ipynb_ir(BytesIO(source), filename="book.ipynb")
    output = BytesIO()

    result = patch_ipynb(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, 0, "HELLO\nworld", "edit-md"),),
    )

    expected = source.replace(b'"hello\\n"', b'"HELLO\\n"', 1)
    assert output.getvalue() == expected
    assert result.format == "ipynb"
    assert result.fidelity.claimed_tier == "high"
    assert {item.check_code for item in result.fidelity.evidence} == {
        "ipynb.source_authority",
        "ipynb.native_evidence",
        "ipynb.json_scalar_lowering",
        "ipynb.untouched_bytes",
        "ipynb.candidate_reread",
    }


def test_multiple_cell_edits_are_atomic() -> None:
    source = _source()
    document = read_ipynb_ir(BytesIO(source), filename="book.ipynb")
    output = BytesIO()

    patch_ipynb(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(document, 2, "RAW\n", "edit-raw"),
            _edit(document, 1, "print(2)", "edit-code"),
            _edit(document, 0, "Hello\nWorld", "edit-md"),
        ),
    )

    candidate = output.getvalue()
    assert b'"source":["Hello\\n","World"]' in candidate
    assert b'"source":"print(2)"' in candidate
    assert b'"source":["RAW\\n"]' in candidate
    assert b'"execution_count":7' in candidate
    assert (
        b'"outputs":[{"output_type":"stream","name":"stdout","text":["ok\\n"]}]'
        in candidate
    )
    assert b'"attachments":{"a.txt":{"text/plain":"YQ=="}}' in candidate


def test_unencodable_replacement_leaves_caller_output_empty() -> None:
    source = (
        b'{"cells":[{"cell_type":"markdown","metadata":{},"source":"caf\xe9"}],'
        b'"metadata":{},"nbformat":4,"nbformat_minor":5}'
    )
    document = read_ipynb_ir(
        BytesIO(source),
        filename="book.ipynb",
        encoding="cp1252",
    )
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_ipynb(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, 0, "emoji: 😀", "edit-unencodable"),),
        )
    assert output.getvalue() == b""


def test_h3_failure_never_leaks_partial_candidate(monkeypatch) -> None:
    from markitdown.twoways.formats.ipynb import writer as writer_module

    source = _source()
    document = read_ipynb_ir(BytesIO(source), filename="book.ipynb")
    output = BytesIO()

    def fail_after_internal_write(document, source_stream, internal, *, edits):
        del document, source_stream, edits
        internal.write(b"partial")
        raise UnsupportedEditError("fault injected")

    monkeypatch.setattr(writer_module, "patch_json", fail_after_internal_write)

    with pytest.raises(UnsupportedEditError, match="fault injected"):
        patch_ipynb(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, 0, "changed", "edit-fault"),),
        )
    assert output.getvalue() == b""
