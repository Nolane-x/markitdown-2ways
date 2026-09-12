from __future__ import annotations

import codecs
from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.formats.text.reader import read_text_ir
from markitdown.twoways.formats.text.writer import patch_text
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.provenance import NativeLocator
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest


def _node(document):
    return document.nodes[document.canvases[0].root_node_ids[0]]


def _replace_edit(
    document, text: str, *, old_value: str | None = None
) -> EditOperation:
    node = _node(document)
    return EditOperation(
        operation_id="edit-1",
        type="replace_text",
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=old_value,
        ),
        payload={"text": text},
    )


def test_noop_patch_preserves_source_bytes_exactly() -> None:
    source = codecs.BOM_UTF8 + b"alpha\r\nbeta\r\n"
    document = read_text_ir(BytesIO(source), filename="notes.txt")
    output = BytesIO()

    result = patch_text(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.format == "text"
    assert result.mode == "patch"
    assert result.bytes_written == len(source)
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_source_digest_mismatch_fails_before_output() -> None:
    document = read_text_ir(BytesIO(b"alpha\n"), filename="notes.txt")
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError):
        patch_text(document, BytesIO(b"different\n"), output, edits=())

    assert output.getvalue() == b""


def test_source_size_metadata_mismatch_fails_before_output() -> None:
    source = b"alpha\n"
    document = read_text_ir(BytesIO(source), filename="notes.txt")
    assert document.source is not None
    forged = replace(
        document,
        source=replace(document.source, size_bytes=len(source) + 1),
    )
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError, match="size"):
        patch_text(forged, BytesIO(source), output, edits=())

    assert output.getvalue() == b""


def test_replace_text_preserves_crlf_and_utf8_bom() -> None:
    source = codecs.BOM_UTF8 + b"alpha\r\nbeta\r\n"
    document = read_text_ir(BytesIO(source), filename="notes.txt")
    output = BytesIO()

    patch_text(
        document,
        BytesIO(source),
        output,
        edits=(
            _replace_edit(
                document,
                "gamma\ndelta\n",
                old_value="alpha\r\nbeta\r\n",
            ),
        ),
    )

    assert output.getvalue() == codecs.BOM_UTF8 + b"gamma\r\ndelta\r\n"


def test_replace_text_preserves_utf16_bom_and_encoding() -> None:
    source = codecs.BOM_UTF16_LE + "alpha\rbeta\r".encode("utf-16-le")
    document = read_text_ir(BytesIO(source), filename="notes.txt")
    output = BytesIO()

    patch_text(
        document,
        BytesIO(source),
        output,
        edits=(_replace_edit(document, "gamma\ndelta\n"),),
    )

    assert output.getvalue() == codecs.BOM_UTF16_LE + "gamma\rdelta\r".encode(
        "utf-16-le"
    )


def test_semantic_noop_replace_returns_original_bytes() -> None:
    source = b"alpha\r\nbeta\r\n"
    document = read_text_ir(BytesIO(source), filename="notes.txt")
    output = BytesIO()

    patch_text(
        document,
        BytesIO(source),
        output,
        edits=(_replace_edit(document, "alpha\r\nbeta\r\n"),),
    )

    assert output.getvalue() == source


def test_stale_old_value_fails_before_output() -> None:
    source = b"alpha\n"
    document = read_text_ir(BytesIO(source), filename="notes.txt")
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_text(
            document,
            BytesIO(source),
            output,
            edits=(_replace_edit(document, "beta\n", old_value="stale\n"),),
        )

    assert output.getvalue() == b""


def test_forged_native_locator_fails_before_output() -> None:
    source = b"alpha\n"
    document = read_text_ir(BytesIO(source), filename="notes.txt")
    node = _node(document)
    forged_node = replace(
        node,
        native_locator=NativeLocator(
            backend="text",
            part_uri="/other",
            object_id="document-body",
        ),
    )
    forged = replace(document, nodes={node.node_id: forged_node})
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="authoritative"):
        patch_text(
            forged,
            BytesIO(source),
            output,
            edits=(
                EditOperation(
                    operation_id="edit-1",
                    type="replace_text",
                    target_node_id=node.node_id,
                    payload={"text": "beta\n"},
                ),
            ),
        )

    assert output.getvalue() == b""


def test_writer_rejects_unknown_or_malformed_edit_payloads() -> None:
    source = b"alpha\n"
    document = read_text_ir(BytesIO(source), filename="notes.txt")
    node = _node(document)

    bad_edits = (
        EditOperation(
            operation_id="bad-type",
            type="set_text_style",
            target_node_id=node.node_id,
        ),
        EditOperation(
            operation_id="bad-key",
            type="replace_text",
            target_node_id=node.node_id,
            payload={"text": "beta\n", "unexpected": True},
        ),
        EditOperation(
            operation_id="bad-value",
            type="replace_text",
            target_node_id=node.node_id,
            payload={"text": 123},
        ),
    )
    for edit in bad_edits:
        output = BytesIO()
        with pytest.raises(UnsupportedEditError):
            patch_text(document, BytesIO(source), output, edits=(edit,))
        assert output.getvalue() == b""


def test_writer_rejects_duplicate_replace_target() -> None:
    source = b"alpha\n"
    document = read_text_ir(BytesIO(source), filename="notes.txt")
    first = _replace_edit(document, "beta\n")
    second = replace(first, operation_id="edit-2", payload={"text": "gamma\n"})
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="duplicate"):
        patch_text(document, BytesIO(source), output, edits=(first, second))

    assert output.getvalue() == b""


def test_writer_rejects_read_only_mixed_newline_source() -> None:
    source = b"alpha\r\nbeta\n"
    document = read_text_ir(BytesIO(source), filename="mixed.txt")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="read-only"):
        patch_text(
            document,
            BytesIO(source),
            output,
            edits=(_replace_edit(document, "gamma\n"),),
        )

    assert output.getvalue() == b""


def test_writer_rejects_unencodable_replacement_without_output() -> None:
    source = b"plain\r\n"
    document = read_text_ir(BytesIO(source), filename="notes.txt", encoding="ascii")
    output = BytesIO()

    with pytest.raises(UnicodeEncodeError):
        patch_text(
            document,
            BytesIO(source),
            output,
            edits=(_replace_edit(document, "\u4f60\u597d\n"),),
        )

    assert output.getvalue() == b""


def test_newline_free_source_cannot_invent_a_newline_convention() -> None:
    source = b"single line"
    document = read_text_ir(BytesIO(source), filename="notes.txt")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="newline convention"):
        patch_text(
            document,
            BytesIO(source),
            output,
            edits=(_replace_edit(document, "first\nsecond"),),
        )

    assert output.getvalue() == b""
