from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways import (
    DocumentIR,
    EditOperation,
    EditPrecondition,
    NativeLocator,
    Node,
    SourceDescriptor,
    TextPayload,
)


def _document(source_bytes: bytes, *, format_name: str = "pptx") -> DocumentIR:
    node = Node(
        node_id="n1",
        kind="text",
        native_locator=NativeLocator(
            backend="ooxml",
            part_uri="/word/document.xml",
            object_id="1",
        ),
        payload=TextPayload(text="old"),
    )
    return DocumentIR(
        document_id="doc",
        source=SourceDescriptor(
            format=format_name,
            sha256=sha256(source_bytes).hexdigest(),
            size_bytes=len(source_bytes),
        ),
        nodes={node.node_id: node},
        root_node_ids=(node.node_id,),
    )


def _zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return output.getvalue()


def test_shared_source_authority_preserves_format_specific_contract():
    from markitdown.twoways.ooxml.package import validate_source_authority

    source = b"source"
    document = _document(source, format_name="pptx")
    validate_source_authority(document, source, expected_format="pptx")

    from markitdown.twoways import SourcePackageMismatchError

    with pytest.raises(SourcePackageMismatchError) as exc:
        validate_source_authority(document, b"other", expected_format="pptx")
    assert str(exc.value) == (
        "Provided PPTX source does not match the DocumentIR source authority."
    )
    assert exc.value.details["reason"] == "source_digest_mismatch"


def test_shared_preconditions_preserve_format_specific_contract():
    from markitdown.twoways.ir.semantics import validate_edit_preconditions
    from markitdown.twoways.ir.semantics import node_semantic_digest

    source = b"source"
    document = _document(source)
    node = document.nodes["n1"]
    edit = EditOperation(
        operation_id="e1",
        type="replace_text",
        target_node_id="n1",
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_old_value="old",
        ),
        payload={"text": "new"},
    )
    validate_edit_preconditions(document, node, edit, format_label="DOCX")

    from markitdown.twoways import PatchPreconditionError

    stale = replace(
        edit,
        precondition=replace(edit.precondition, expected_old_value="stale"),
    )
    with pytest.raises(PatchPreconditionError) as exc:
        validate_edit_preconditions(document, node, stale, format_label="DOCX")
    assert str(exc.value) == "DOCX edit precondition failed."
    assert exc.value.details["reason"] == "old_value"


def test_shared_package_preservation_reports_only_untouched_changes():
    from markitdown.twoways.ooxml.package import inspect_package_preservation

    source = _zip_bytes([("a.xml", b"a"), ("b.xml", b"b")])
    changed = _zip_bytes([("a.xml", b"changed"), ("b.xml", b"b")])
    result = inspect_package_preservation(
        source,
        changed,
        touched_parts=("a.xml",),
    )
    assert result.inventory_matches is True
    assert result.changed_untouched == ()

    unrelated = _zip_bytes([("a.xml", b"a"), ("b.xml", b"changed")])
    result = inspect_package_preservation(
        source,
        unrelated,
        touched_parts=("a.xml",),
    )
    assert result.inventory_matches is True
    assert result.changed_untouched == ("b.xml",)

def test_shared_binary_stream_reader_preserves_format_error_contract():
    from markitdown.twoways.ooxml.package import read_binary_stream

    class TextStream:
        def read(self):
            return "not-bytes"

    with pytest.raises(TypeError, match="PPTX source stream must yield bytes"):
        read_binary_stream(TextStream(), stream_label="PPTX source")

    with pytest.raises(TypeError, match="DOCX input stream must yield bytes"):
        read_binary_stream(TextStream(), stream_label="DOCX input")

