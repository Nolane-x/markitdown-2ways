from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.formats.png import patch_png, read_png_ir
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.provenance import NativeLocator
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest

from ._png_fixtures import make_png


def _node(document, keyword: str = "Title"):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "png-text-metadata"
        and node.metadata.get("png.keyword") == keyword
    )


def _edit(document, value: str, *, keyword: str = "Title", old_value: str | None = None):
    node = _node(document, keyword)
    return EditOperation(
        operation_id=f"edit-{keyword}",
        type="update_png_text_metadata",
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=old_value,
        ),
        payload={
            "keyword": keyword,
            "old_value": node.payload.text if old_value is None else old_value,
            "value": value,
        },
    )


def test_noop_patch_preserves_source_bytes_exactly() -> None:
    source = make_png()
    document = read_png_ir(BytesIO(source), filename="card.png")
    output = BytesIO()

    result = patch_png(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.format == "png"
    assert result.mode == "patch"
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_updates_only_existing_text_chunk_and_rereads_value() -> None:
    source = make_png(
        text=(("Title", "Alpha"), ("Author", "Nolane")),
        ancillary=((b"pHYs", b"\x00\x00\x0e\xc4\x00\x00\x0e\xc4\x01"),),
    )
    document = read_png_ir(BytesIO(source), filename="card.png")
    output = BytesIO()

    result = patch_png(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "A much longer title", old_value="Alpha"),),
    )

    candidate = output.getvalue()
    reread = read_png_ir(BytesIO(candidate), filename="card.png")
    assert _node(reread).payload.text == "A much longer title"
    assert _node(reread, "Author").payload.text == "Nolane"
    assert result.fidelity.claimed_tier == "high"
    assert b"pHYs" in candidate


def test_multiple_distinct_text_edits_are_transactional() -> None:
    source = make_png(text=(("Title", "Alpha"), ("Author", "Ada")))
    document = read_png_ir(BytesIO(source), filename="card.png")
    output = BytesIO()

    patch_png(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(document, "Beta", keyword="Title", old_value="Alpha"),
            _edit(document, "Nolane", keyword="Author", old_value="Ada"),
        ),
    )

    reread = read_png_ir(BytesIO(output.getvalue()), filename="card.png")
    assert _node(reread, "Title").payload.text == "Beta"
    assert _node(reread, "Author").payload.text == "Nolane"


def test_source_digest_mismatch_fails_before_output() -> None:
    source = make_png()
    document = read_png_ir(BytesIO(source), filename="card.png")
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError):
        patch_png(document, BytesIO(make_png(text=(("Title", "Different"),))), output)

    assert output.getvalue() == b""


def test_stale_old_value_fails_before_output() -> None:
    source = make_png()
    document = read_png_ir(BytesIO(source), filename="card.png")
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_png(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "Beta", old_value="stale"),),
        )

    assert output.getvalue() == b""


def test_forged_locator_fails_before_output() -> None:
    source = make_png()
    document = read_png_ir(BytesIO(source), filename="card.png")
    node = _node(document)
    forged_node = replace(
        node,
        native_locator=NativeLocator(
            backend="png",
            part_uri="/",
            object_id="chunk:999:Title",
        ),
    )
    forged = replace(document, nodes={**document.nodes, node.node_id: forged_node})
    output = BytesIO()

    with pytest.raises(PatchPreconditionError):
        patch_png(
            forged,
            BytesIO(source),
            output,
            edits=(
                EditOperation(
                    operation_id="forged",
                    type="update_png_text_metadata",
                    target_node_id=node.node_id,
                    payload={"keyword": "Title", "old_value": "Alpha", "value": "Beta"},
                ),
            ),
        )

    assert output.getvalue() == b""


def test_duplicate_keyword_source_cannot_be_mutated() -> None:
    source = make_png(text=(("Title", "Alpha"), ("Title", "Beta")))
    document = read_png_ir(BytesIO(source), filename="duplicate.png")
    node = next(node for node in document.nodes.values() if node.semantic_role == "png-text-metadata")
    output = BytesIO()

    with pytest.raises(UnsupportedEditError):
        patch_png(
            document,
            BytesIO(source),
            output,
            edits=(
                EditOperation(
                    operation_id="duplicate",
                    type="update_png_text_metadata",
                    target_node_id=node.node_id,
                    payload={"keyword": "Title", "old_value": node.payload.text, "value": "Gamma"},
                ),
            ),
        )

    assert output.getvalue() == b""
