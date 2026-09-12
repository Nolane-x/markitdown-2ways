from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.formats.html.reader import read_html_ir
from markitdown.twoways.formats.html.writer import patch_html
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.provenance import NativeLocator
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest


def _node(document, path):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("html.path") == path
    )


def _replace_node(document, node):
    nodes = dict(document.nodes)
    nodes[node.node_id] = node
    return replace(document, nodes=nodes)


def _edit(
    document,
    path,
    value,
    *,
    operation_id="edit-1",
    edit_type=None,
    semantic_digest=None,
    locator_digest=None,
    old_value=None,
):
    node = _node(document, path)
    if edit_type is None:
        edit_type = (
            "replace_html_attribute"
            if node.metadata.get("html.kind") == "attribute"
            else "replace_html_text"
        )
    return EditOperation(
        operation_id=operation_id,
        type=edit_type,
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=(
                node_semantic_digest(node)
                if semantic_digest is None
                else semantic_digest
            ),
            expected_native_locator_digest=(
                native_locator_digest(node)
                if locator_digest is None
                else locator_digest
            ),
            expected_old_value=old_value,
        ),
        payload={"value": value},
    )


def test_zero_edit_patch_is_byte_identical() -> None:
    source = (
        b'<!DOCTYPE html><HTML><body><p CLASS="hero">A&amp;B</p></body></HTML>\r\n'
    )
    document = read_html_ir(BytesIO(source), filename="page.html", mimetype="text/html")
    output = BytesIO()

    result = patch_html(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.format == "html"
    assert result.mode == "patch"
    assert result.bytes_written == len(source)
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_source_digest_mismatch_fails_before_output() -> None:
    source = b"<html><body><p>one</p></body></html>"
    document = read_html_ir(BytesIO(source), filename="page.html")
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError):
        patch_html(
            document,
            BytesIO(b"<html><body><p>two</p></body></html>"),
            output,
            edits=(),
        )

    assert output.getvalue() == b""


def test_source_size_metadata_mismatch_fails_before_output() -> None:
    source = b"<html><body><p>one</p></body></html>"
    document = read_html_ir(BytesIO(source), filename="page.html")
    assert document.source is not None
    forged = replace(
        document,
        source=replace(document.source, size_bytes=len(source) + 1),
    )
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError, match="size"):
        patch_html(forged, BytesIO(source), output, edits=())

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    ("path", "metadata_key", "forged_value"),
    [
        ("/html[1]/body[1]/p[1]/#text[1]", "html.path", "/html[1]/body[1]/p[1]/#text[9]"),
        ("/html[1]/body[1]/p[1]/#text[1]", "html.kind", "rawtext"),
        ("/html[1]/body[1]/p[1]/@class", "html.normalized_name", "other"),
        ("/html[1]/body[1]/p[1]/@class", "html.qname", "OTHER"),
        ("/html[1]/body[1]/p[1]/#text[1]", "html.char_start", 0),
        ("/html[1]/body[1]/p[1]/@class", "html.value_start", 0),
        ("/html[1]/body[1]/p[1]/@class", "html.value_end", 1),
        ("/html[1]/body[1]/p[1]/@class", "html.quote", "'"),
        ("/html[1]/body[1]/p[1]/#text[1]", "html.raw_digest", "0" * 64),
        ("/html[1]/body[1]/p[1]/#text[1]", "html.recovery_signature", ()),
    ],
)
def test_forged_html_metadata_is_rejected_against_actual_source(
    path, metadata_key, forged_value
) -> None:
    source = b'<html><body><p CLASS="hero">text</p></body></html>'
    document = read_html_ir(BytesIO(source), filename="page.html")
    node = _node(document, path)
    metadata = dict(node.metadata)
    metadata[metadata_key] = forged_value
    forged = _replace_node(document, replace(node, metadata=metadata))
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_html(forged, BytesIO(source), output, edits=())

    assert output.getvalue() == b""


def test_forged_native_locator_is_rejected_against_actual_source() -> None:
    source = b"<html><body><p>text</p></body></html>"
    document = read_html_ir(BytesIO(source), filename="page.html")
    node = _node(document, "/html[1]/body[1]/p[1]/#text[1]")
    forged_node = replace(
        node,
        native_locator=NativeLocator(
            backend="html",
            part_uri="/",
            object_id="text",
            path="/html[1]/body[1]/p[1]/#text[9]",
        ),
    )
    forged = _replace_node(document, forged_node)
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_html(forged, BytesIO(source), output, edits=())

    assert output.getvalue() == b""


def test_forged_parent_relationship_is_rejected_against_actual_source() -> None:
    source = b"<html><body><p>text</p></body></html>"
    document = read_html_ir(BytesIO(source), filename="page.html")
    node = _node(document, "/html[1]/body[1]/p[1]/#text[1]")
    forged = _replace_node(document, replace(node, parent_id=None))
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_html(forged, BytesIO(source), output, edits=())

    assert output.getvalue() == b""


def test_forged_children_relationship_is_rejected_against_actual_source() -> None:
    source = b"<html><body><p>text</p></body></html>"
    document = read_html_ir(BytesIO(source), filename="page.html")
    node = _node(document, "/html[1]/body[1]/p[1]")
    forged = _replace_node(document, replace(node, children=()))
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_html(forged, BytesIO(source), output, edits=())

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"value": "x", "unexpected": True},
        {"unexpected": "x"},
        {"value": 7},
        {"value": None},
    ],
)
def test_malformed_html_edit_payload_fails_closed(payload) -> None:
    source = b"<html><body><p>text</p></body></html>"
    document = read_html_ir(BytesIO(source), filename="page.html")
    node = _node(document, "/html[1]/body[1]/p[1]/#text[1]")
    edit = EditOperation(
        operation_id="bad-payload",
        type="replace_html_text",
        target_node_id=node.node_id,
        payload=payload,
    )
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_html(document, BytesIO(source), output, edits=(edit,))

    assert output.getvalue() == b""


def test_wrong_operation_for_node_kind_fails_closed() -> None:
    source = b'<html><body><p class="x">text</p></body></html>'
    document = read_html_ir(BytesIO(source), filename="page.html")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_html(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(
                    document,
                    "/html[1]/body[1]/p[1]/#text[1]",
                    "new",
                    edit_type="replace_html_attribute",
                ),
            ),
        )

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    ("source", "path", "edit_type"),
    [
        (
            b"<html><body><p>text</p></body></html>",
            "/html[1]/body[1]/p[1]",
            "replace_html_text",
        ),
        (
            b"<html><body><p data-x=value>text</p></body></html>",
            "/html[1]/body[1]/p[1]/@data-x",
            "replace_html_attribute",
        ),
        (
            b"<html><body><input disabled></body></html>",
            "/html[1]/body[1]/input[1]/@disabled",
            "replace_html_attribute",
        ),
        (
            b"<html><head><style>body{margin:0}</style></head><body></body></html>",
            "/html[1]/head[1]/style[1]/#rawtext[1]",
            "replace_html_text",
        ),
        (
            b"<html><head><title>Hello</title></head><body></body></html>",
            "/html[1]/head[1]/title[1]/#rcdata[1]",
            "replace_html_text",
        ),
    ],
)
def test_read_only_html_owners_cannot_be_mutated(source, path, edit_type) -> None:
    document = read_html_ir(BytesIO(source), filename="page.html")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_html(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, path, "new", edit_type=edit_type),),
        )

    assert output.getvalue() == b""


def test_recovery_unstable_document_cannot_be_mutated() -> None:
    source = b"<p>one<p>two"
    document = read_html_ir(BytesIO(source), filename="page.html")
    root = _node(document, "/")
    edit = EditOperation(
        operation_id="unstable",
        type="replace_html_text",
        target_node_id=root.node_id,
        payload={"value": "new"},
    )
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_html(document, BytesIO(source), output, edits=(edit,))

    assert output.getvalue() == b""


def test_unknown_target_fails_closed() -> None:
    source = b"<html><body><p>text</p></body></html>"
    document = read_html_ir(BytesIO(source), filename="page.html")
    edit = EditOperation(
        operation_id="missing-target",
        type="replace_html_text",
        target_node_id="missing-html-node",
        payload={"value": "new"},
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_html(document, BytesIO(source), output, edits=(edit,))

    assert output.getvalue() == b""


def test_duplicate_target_edits_fail_closed() -> None:
    source = b"<html><body><p>text</p></body></html>"
    document = read_html_ir(BytesIO(source), filename="page.html")
    path = "/html[1]/body[1]/p[1]/#text[1]"
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="duplicate"):
        patch_html(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(document, path, "one", operation_id="one"),
                _edit(document, path, "two", operation_id="two"),
            ),
        )

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    ("source", "path", "value"),
    [
        (
            b"<html><body><p>text</p></body></html>",
            "/html[1]/body[1]/p[1]/#text[1]",
            "text",
        ),
        (
            b'<html><body><p a="same">x</p></body></html>',
            "/html[1]/body[1]/p[1]/@a",
            "same",
        ),
    ],
)
def test_semantic_noop_is_rejected_before_output(source, path, value) -> None:
    document = read_html_ir(BytesIO(source), filename="page.html")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="semantic"):
        patch_html(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, path, value),),
        )

    assert output.getvalue() == b""


def test_stale_semantic_precondition_is_rejected() -> None:
    source = b"<html><body><p>text</p></body></html>"
    document = read_html_ir(BytesIO(source), filename="page.html")
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_html(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(
                    document,
                    "/html[1]/body[1]/p[1]/#text[1]",
                    "new",
                    semantic_digest="0" * 64,
                ),
            ),
        )

    assert output.getvalue() == b""


def test_stale_native_locator_precondition_is_rejected() -> None:
    source = b"<html><body><p>text</p></body></html>"
    document = read_html_ir(BytesIO(source), filename="page.html")
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_html(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(
                    document,
                    "/html[1]/body[1]/p[1]/#text[1]",
                    "new",
                    locator_digest="0" * 64,
                ),
            ),
        )

    assert output.getvalue() == b""


def test_stale_old_value_precondition_is_rejected() -> None:
    source = b"<html><body><p>text</p></body></html>"
    document = read_html_ir(BytesIO(source), filename="page.html")
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_html(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(
                    document,
                    "/html[1]/body[1]/p[1]/#text[1]",
                    "new",
                    old_value="stale",
                ),
            ),
        )

    assert output.getvalue() == b""
