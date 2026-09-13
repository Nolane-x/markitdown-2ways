from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.formats.epub.package import (
    build_epub_candidate,
    snapshot_epub_package,
)
from markitdown.twoways.formats.epub.reader import read_epub_ir
from markitdown.twoways.formats.epub.writer import patch_epub
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest

from ._epub_fixtures import make_epub, read_member


def _owner(document, value: str):
    matches = [
        node
        for node in document.nodes.values()
        if getattr(node.payload, "text", None) == value
        and node.metadata.get("epub.owner_kind") in {"metadata-text", "xhtml-text"}
    ]
    assert len(matches) == 1
    return matches[0]


def _edit(
    document,
    old_value: str,
    new_value: str,
    *,
    operation_id: str,
    precondition: bool = True,
) -> EditOperation:
    node = _owner(document, old_value)
    operation = {
        "metadata-text": "replace_epub_metadata_text",
        "xhtml-text": "replace_epub_xhtml_text",
    }[node.metadata["epub.owner_kind"]]
    condition = None
    if precondition:
        condition = EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=old_value,
        )
    return EditOperation(
        operation_id=operation_id,
        type=operation,
        target_node_id=node.node_id,
        precondition=condition,
        payload={"value": new_value},
    )


def test_zero_edit_patch_is_byte_identical() -> None:
    source = make_epub()
    document = read_epub_ir(BytesIO(source), filename="book.epub")
    output = BytesIO()

    result = patch_epub(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.format == "epub"
    assert result.mode == "patch"
    assert result.bytes_written == len(source)
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_metadata_and_xhtml_edits_are_transactional_and_target_only() -> None:
    source = make_epub()
    document = read_epub_ir(BytesIO(source), filename="book.epub")
    output = BytesIO()
    edits = (
        _edit(
            document,
            "Demo Book",
            "Renamed Book",
            operation_id="metadata-1",
        ),
        _edit(document, "world", "WORLD", operation_id="xhtml-1"),
    )

    result = patch_epub(document, BytesIO(source), output, edits=edits)
    candidate = output.getvalue()

    assert b"Renamed Book" in read_member(candidate, "OEBPS/content.opf")
    assert b"WORLD" in read_member(candidate, "OEBPS/chapter.xhtml")
    assert read_member(candidate, "META-INF/container.xml") == read_member(
        source, "META-INF/container.xml"
    )
    assert read_member(candidate, "OEBPS/style.css") == read_member(
        source, "OEBPS/style.css"
    )
    assert read_member(candidate, "OEBPS/cover.png") == read_member(
        source, "OEBPS/cover.png"
    )
    assert result.fidelity.claimed_tier == "high"
    evidence = {item.check_code for item in result.fidelity.evidence}
    assert {
        "epub.source_authority",
        "epub.xml_member_lowering",
        "epub.untouched_member_content",
        "epub.candidate_reread",
    } <= evidence


def test_source_authority_mismatch_fails_before_output() -> None:
    source = make_epub()
    document = read_epub_ir(BytesIO(source), filename="book.epub")
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError):
        patch_epub(document, BytesIO(source + b"\n"), output, edits=())

    assert output.getvalue() == b""


def test_duplicate_noop_invalid_type_and_stale_precondition_fail_before_output() -> None:
    source = make_epub()
    document = read_epub_ir(BytesIO(source), filename="book.epub")

    output = BytesIO()
    with pytest.raises(UnsupportedEditError):
        patch_epub(
            document,
            BytesIO(source),
            output,
            edits=(
                _edit(document, "world", "WORLD", operation_id="a"),
                _edit(document, "world", "World 2", operation_id="b"),
            ),
        )
    assert output.getvalue() == b""

    output = BytesIO()
    with pytest.raises(UnsupportedEditError):
        patch_epub(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "world", "world", operation_id="noop"),),
        )
    assert output.getvalue() == b""

    output = BytesIO()
    wrong_type = replace(
        _edit(document, "world", "WORLD", operation_id="wrong"),
        type="replace_epub_metadata_text",
    )
    with pytest.raises(UnsupportedEditError):
        patch_epub(document, BytesIO(source), output, edits=(wrong_type,))
    assert output.getvalue() == b""

    output = BytesIO()
    stale = replace(
        _edit(document, "world", "WORLD", operation_id="stale"),
        precondition=EditPrecondition(expected_old_value="stale"),
    )
    with pytest.raises(PatchPreconditionError):
        patch_epub(document, BytesIO(source), output, edits=(stale,))
    assert output.getvalue() == b""


def test_forged_native_evidence_fails_before_output() -> None:
    source = make_epub()
    document = read_epub_ir(BytesIO(source), filename="book.epub")
    node = _owner(document, "world")
    metadata = dict(node.metadata)
    metadata["epub.xml_path"] = "/forged/path"
    nodes = dict(document.nodes)
    nodes[node.node_id] = replace(node, metadata=metadata)
    forged = replace(document, nodes=nodes)
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_epub(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(document, "world", "WORLD", operation_id="edit"),),
        )
    assert output.getvalue() == b""


def test_sparse_package_candidate_preserves_order_and_untouched_content() -> None:
    source = make_epub()
    snapshot = snapshot_epub_package(source)
    chapter = read_member(source, "OEBPS/chapter.xhtml")
    replacement = chapter.replace(b"world", b"WORLD")

    candidate = build_epub_candidate(
        snapshot,
        source,
        replacements={"OEBPS/chapter.xhtml": replacement},
    )

    with ZipFile(BytesIO(source), "r") as before, ZipFile(
        BytesIO(candidate), "r"
    ) as after:
        assert [item.filename for item in after.infolist()] == [
            item.filename for item in before.infolist()
        ]
        for info in before.infolist():
            if info.filename == "OEBPS/chapter.xhtml":
                assert after.read(info.filename) == replacement
            else:
                assert after.read(info.filename) == before.read(info.filename)


def test_sparse_package_zero_replacements_reuses_exact_source_bytes() -> None:
    source = make_epub()
    snapshot = snapshot_epub_package(source)

    assert build_epub_candidate(snapshot, source, replacements={}) == source
