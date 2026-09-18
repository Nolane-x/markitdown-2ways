from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pytest

from markitdown.twoways._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from markitdown.twoways.formats.mp3 import patch_mp3, read_mp3_ir
from markitdown.twoways.ir.edits import EditOperation, EditPrecondition
from markitdown.twoways.ir.semantics import native_locator_digest, node_semantic_digest

from ._mp3_fixtures import make_mp3


def _node(document, field: str = "Title"):
    return next(
        node
        for node in document.nodes.values()
        if node.semantic_role == "mp3-id3v1-text"
        and node.metadata.get("mp3.id3v1_field") == field
    )


def _edit(
    document,
    value: str,
    *,
    field: str = "Title",
    old_value: str | None = None,
    operation_type: str = "update_mp3_id3v1_text",
) -> EditOperation:
    node = _node(document, field)
    expected_old = node.payload.text if old_value is None else old_value
    return EditOperation(
        operation_id=f"edit-{field.lower()}",
        type=operation_type,
        target_node_id=node.node_id,
        precondition=EditPrecondition(
            expected_semantic_digest=node_semantic_digest(node),
            expected_native_locator_digest=native_locator_digest(node),
            expected_old_value=expected_old,
        ),
        payload={
            "field": field,
            "old_value": expected_old,
            "value": value,
        },
    )


def test_noop_patch_preserves_source_bytes_exactly() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source), filename="song.mp3")
    output = BytesIO()

    result = patch_mp3(document, BytesIO(source), output, edits=())

    assert output.getvalue() == source
    assert result.format == "mp3"
    assert result.mode == "patch"
    assert result.fidelity.claimed_tier == "exact-preserve"


def test_semantic_noop_preserves_source_bytes_exactly() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source), filename="song.mp3")
    output = BytesIO()

    result = patch_mp3(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "Alpha"),),
    )

    assert output.getvalue() == source
    assert result.fidelity.claimed_tier == "exact-preserve"


@pytest.mark.parametrize(
    ("field", "value"),
    (("Title", "Beta"), ("Artist", "Ada"), ("Album", "Research")),
)
def test_updates_each_supported_fixed_slot(field: str, value: str) -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source), filename="song.mp3")
    output = BytesIO()

    patch_mp3(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, value, field=field),),
    )

    candidate = output.getvalue()
    reread = read_mp3_ir(BytesIO(candidate), filename="song.mp3")
    assert len(candidate) == len(source)
    assert _node(reread, field).payload.text == value


def test_short_replacement_is_nul_padded_to_exact_slot() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source), filename="song.mp3")
    node = _node(document, "Title")
    output = BytesIO()

    patch_mp3(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "B"),),
    )

    candidate = output.getvalue()
    start = node.metadata["mp3.slot_start"]
    assert candidate[start : start + 30] == b"B" + b"\x00" * 29


def test_full_width_replacement_uses_all_30_bytes() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source), filename="song.mp3")
    node = _node(document, "Title")
    output = BytesIO()
    value = "A" * 30

    patch_mp3(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, value),),
    )

    candidate = output.getvalue()
    start = node.metadata["mp3.slot_start"]
    assert candidate[start : start + 30] == b"A" * 30
    assert _node(read_mp3_ir(BytesIO(candidate)), "Title").payload.text == value


def test_two_field_edits_are_transactional() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source), filename="song.mp3")
    output = BytesIO()

    patch_mp3(
        document,
        BytesIO(source),
        output,
        edits=(
            _edit(document, "Beta", field="Title"),
            _edit(document, "Ada", field="Artist"),
        ),
    )

    reread = read_mp3_ir(BytesIO(output.getvalue()))
    assert _node(reread, "Title").payload.text == "Beta"
    assert _node(reread, "Artist").payload.text == "Ada"
    assert _node(reread, "Album").payload.text == "Lab"


def test_duplicate_target_fails_without_output() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source))
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="duplicate"):
        patch_mp3(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "Beta"), _edit(document, "Gamma")),
        )
    assert output.getvalue() == b""


def test_wrong_operation_fails_without_output() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source))
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="update_mp3_id3v1_text|operation"):
        patch_mp3(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "Beta", operation_type="replace_text"),),
        )
    assert output.getvalue() == b""


def test_source_digest_mismatch_fails_without_output() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source))
    different = make_mp3(title="Different")
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError):
        patch_mp3(document, BytesIO(different), output, edits=())
    assert output.getvalue() == b""


def test_source_size_mismatch_fails_without_output() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source))
    assert document.source is not None
    forged = replace(
        document,
        source=replace(document.source, size_bytes=len(source) + 1),
    )
    output = BytesIO()

    with pytest.raises(SourcePackageMismatchError, match="size"):
        patch_mp3(forged, BytesIO(source), output, edits=())
    assert output.getvalue() == b""


def test_stale_old_value_fails_without_output() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source))
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="old|stale"):
        patch_mp3(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "Beta", old_value="stale"),),
        )
    assert output.getvalue() == b""


def test_immutable_field_identity_fails_without_output() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source))
    node = _node(document)
    edit = EditOperation(
        operation_id="wrong-field",
        type="update_mp3_id3v1_text",
        target_node_id=node.node_id,
        payload={"field": "Artist", "old_value": "Alpha", "value": "Beta"},
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="field|immutable"):
        patch_mp3(document, BytesIO(source), output, edits=(edit,))
    assert output.getvalue() == b""


def test_non_latin1_replacement_fails_without_output() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source))
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="ISO-8859-1|Latin"):
        patch_mp3(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "漢字"),),
        )
    assert output.getvalue() == b""


def test_growth_beyond_30_bytes_fails_without_output() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source))
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="30|growth"):
        patch_mp3(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "A" * 31),),
        )
    assert output.getvalue() == b""


def test_stale_slot_digest_fails_without_output() -> None:
    source = make_mp3()
    document = read_mp3_ir(BytesIO(source))
    node = _node(document)
    forged_node = replace(
        node,
        metadata={**node.metadata, "mp3.slot_sha256": "0" * 64},
    )
    forged = replace(
        document,
        nodes={**document.nodes, node.node_id: forged_node},
    )
    output = BytesIO()

    with pytest.raises(PatchPreconditionError, match="slot|digest|native"):
        patch_mp3(
            forged,
            BytesIO(source),
            output,
            edits=(_edit(forged, "Beta"),),
        )
    assert output.getvalue() == b""
