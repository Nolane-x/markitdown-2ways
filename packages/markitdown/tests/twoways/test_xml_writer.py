from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.formats.xml.reader import read_xml_ir
from markitdown.twoways.formats.xml.writer import patch_xml
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.provenance import NativeLocator
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest


def _node(document, path):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("xml.path") == path
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
):
    node = _node(document, path)
    if edit_type is None:
        edit_type = (
            "replace_xml_attribute"
            if node.metadata.get("xml.kind") == "attribute"
            else "replace_xml_text"
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
        ),
        payload={"value": value},
    )


def test_zero_edit_patch_is_byte_identical() -> None:
    source = b'<?xml version="1.0" encoding="UTF-8"?><r a="1">x&amp;y</r>\r\n'
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    result = patch_xml(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.format == "xml"
    assert result.mode == "patch"
    assert result.bytes_written == len(source)
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_source_digest_mismatch_fails_before_output() -> None:
    source = b"<r>one</r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError):
        patch_xml(document, BytesIO(b"<r>two</r>"), output, edits=())

    assert output.getvalue() == b""


def test_source_size_metadata_mismatch_fails_before_output() -> None:
    source = b"<r>one</r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    assert document.source is not None
    forged = replace(
        document,
        source=replace(document.source, size_bytes=len(source) + 1),
    )
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError, match="size"):
        patch_xml(forged, BytesIO(source), output, edits=())

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    ("path", "metadata_key", "forged_value"),
    [
        ("/r[1]/#text[1]", "xml.path", "/r[1]/#text[9]"),
        ("/r[1]/@a", "xml.qname", "other"),
        ("/r[1]/@a", "xml.expanded_name", "other"),
        ("/r[1]/#text[1]", "xml.char_start", 0),
        ("/r[1]/#text[1]", "xml.char_end", 1),
        ("/r[1]/#text[1]", "xml.raw_digest", "0" * 64),
    ],
)
def test_forged_xml_metadata_is_rejected_against_actual_source(
    path, metadata_key, forged_value
) -> None:
    source = b'<r a="1">text<c>child</c></r>'
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    node = _node(document, path)
    metadata = dict(node.metadata)
    metadata[metadata_key] = forged_value
    forged = _replace_node(document, replace(node, metadata=metadata))
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_xml(forged, BytesIO(source), output, edits=())

    assert output.getvalue() == b""


def test_forged_native_locator_is_rejected_against_actual_source() -> None:
    source = b"<r>text</r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    node = _node(document, "/r[1]/#text[1]")
    forged_node = replace(
        node,
        native_locator=NativeLocator(
            backend="xml",
            part_uri="/",
            object_id="text",
            path="/r[1]/#text[9]",
        ),
    )
    forged = _replace_node(document, forged_node)
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_xml(forged, BytesIO(source), output, edits=())

    assert output.getvalue() == b""


def test_forged_parent_relationship_is_rejected_against_actual_source() -> None:
    source = b"<r><c>text</c></r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    node = _node(document, "/r[1]/c[1]/#text[1]")
    forged = _replace_node(document, replace(node, parent_id=None))
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_xml(forged, BytesIO(source), output, edits=())

    assert output.getvalue() == b""


def test_forged_children_relationship_is_rejected_against_actual_source() -> None:
    source = b"<r><c>text</c></r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    node = _node(document, "/r[1]/c[1]")
    forged = _replace_node(document, replace(node, children=()))
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_xml(forged, BytesIO(source), output, edits=())

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
def test_malformed_xml_edit_payload_fails_closed(payload) -> None:
    source = b"<r>text</r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    node = _node(document, "/r[1]/#text[1]")
    edit = EditOperation(
        operation_id="bad-payload",
        type="replace_xml_text",
        target_node_id=node.node_id,
        payload=payload,
    )
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_xml(document, BytesIO(source), output, edits=(edit,))

    assert output.getvalue() == b""


def test_wrong_operation_for_node_kind_fails_closed() -> None:
    source = b'<r a="1">text</r>'
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_xml(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(
                    document,
                    "/r[1]/#text[1]",
                    "new",
                    edit_type="replace_xml_attribute",
                ),
            ),
        )

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    ("source", "path", "edit_type"),
    [
        (b"<r>text</r>", "/r[1]", "replace_xml_text"),
        (
            b'<r xmlns:m="urn:m">text</r>',
            "/r[1]/@xmlns%3Am",
            "replace_xml_attribute",
        ),
        (b"<r><![CDATA[text]]></r>", "/r[1]/#cdata[1]", "replace_xml_text"),
    ],
)
def test_read_only_xml_owners_cannot_be_mutated(source, path, edit_type) -> None:
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_xml(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, path, "new", edit_type=edit_type),),
        )

    assert output.getvalue() == b""


def test_unknown_target_fails_closed() -> None:
    source = b"<r>text</r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    edit = EditOperation(
        operation_id="missing-target",
        type="replace_xml_text",
        target_node_id="missing-xml-node",
        payload={"value": "new"},
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_xml(document, BytesIO(source), output, edits=(edit,))

    assert output.getvalue() == b""


def test_duplicate_target_edits_fail_closed() -> None:
    source = b"<r>text</r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="duplicate"):
        patch_xml(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(document, "/r[1]/#text[1]", "one", operation_id="one"),
                _edit(document, "/r[1]/#text[1]", "two", operation_id="two"),
            ),
        )

    assert output.getvalue() == b""


@pytest.mark.parametrize(
    ("source", "path", "value"),
    [
        (b"<r>text</r>", "/r[1]/#text[1]", "text"),
        (b'<r a="same"/>', "/r[1]/@a", "same"),
    ],
)
def test_semantic_noop_is_rejected_before_output(source, path, value) -> None:
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="semantic"):
        patch_xml(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, path, value),),
        )

    assert output.getvalue() == b""


def test_invalid_xml_character_replacement_fails_before_output() -> None:
    source = b"<r>text</r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="character"):
        patch_xml(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "/r[1]/#text[1]", "bad\x00value"),),
        )

    assert output.getvalue() == b""


def test_stale_semantic_precondition_is_rejected() -> None:
    source = b"<r>text</r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_xml(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(
                    document,
                    "/r[1]/#text[1]",
                    "new",
                    semantic_digest="0" * 64,
                ),
            ),
        )

    assert output.getvalue() == b""


def test_stale_native_locator_precondition_is_rejected() -> None:
    source = b"<r>text</r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_xml(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(
                    document,
                    "/r[1]/#text[1]",
                    "new",
                    locator_digest="0" * 64,
                ),
            ),
        )

    assert output.getvalue() == b""


def test_non_roundtrippable_xml_is_not_writable() -> None:
    source = b"<r>text</r>"
    document = read_xml_ir(
        BytesIO(source),
        filename="data.xml",
        encoding="utf-8-sig",
    )
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="roundtrippable"):
        patch_xml(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "/r[1]/#text[1]", "new"),),
        )

    assert output.getvalue() == b""


def test_text_replacement_uses_xml_safe_exact_rendering() -> None:
    source = b"<r>old</r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    result = patch_xml(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(
                document,
                "/r[1]/#text[1]",
                "A&B<C>D\rE\n\u03a9",
            ),
        ),
    )

    assert output.getvalue() == "<r>A&amp;B&lt;C&gt;D&#13;E\n\u03a9</r>".encode("utf-8")
    assert result.fidelity.claimed_tier == "high"


def test_double_quoted_attribute_replacement_preserves_quote_style() -> None:
    source = b'<r a="old"/>'
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    patch_xml(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(
                document,
                "/r[1]/@a",
                '"&<>\t\n\r',
            ),
        ),
    )

    assert output.getvalue() == b'<r a="&quot;&amp;&lt;&gt;&#9;&#10;&#13;"/>'


def test_single_quoted_attribute_replacement_preserves_quote_style() -> None:
    source = b"<r a='old'/>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    patch_xml(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "/r[1]/@a", "x'y"),),
    )

    assert output.getvalue() == b"<r a='x&apos;y'/>"


def test_text_renderer_neutralizes_cdata_close_sequence() -> None:
    source = b"<r>old</r>"
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    patch_xml(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "/r[1]/#text[1]", "a]]>b"),),
    )

    assert output.getvalue() == b"<r>a]]&gt;b</r>"


def test_multiple_targets_patch_only_owned_value_spans() -> None:
    source = (
        b'<?xml version="1.0"?><r a="x"><c>much longer</c>'
        b"<keep k='v'>stay</keep></r>"
    )
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    patch_xml(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(
                document,
                "/r[1]/c[1]/#text[1]",
                "z",
                operation_id="text",
            ),
            _edit(
                document,
                "/r[1]/@a",
                "a much longer value",
                operation_id="root-attr",
            ),
            _edit(
                document,
                "/r[1]/keep[1]/@k",
                "changed",
                operation_id="keep-attr",
            ),
        ),
    )

    assert output.getvalue() == (
        b'<?xml version="1.0"?><r a="a much longer value"><c>z</c>'
        b"<keep k='changed'>stay</keep></r>"
    )
