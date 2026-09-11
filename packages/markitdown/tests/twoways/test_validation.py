import dataclasses
import pytest

from markitdown.twoways import (
    IRValidationError,
    ImagePayload,
    SourceDescriptor,
    UnsupportedSchemaVersionError,
    validate_document,
)
from ._fixtures import make_representative_document


def violation_codes(exc: IRValidationError) -> list[str]:
    return [item["code"] for item in exc.details["violations"]]


def test_valid_representative_document_passes_validation():
    assert validate_document(make_representative_document()) is None


def test_missing_child_fails_closed():
    doc = make_representative_document()
    group = dataclasses.replace(doc.nodes["group1"], children=("missing",))
    broken = dataclasses.replace(doc, nodes={**doc.nodes, "group1": group})
    with pytest.raises(IRValidationError) as raised:
        validate_document(broken)
    assert "node.missing_child" in violation_codes(raised.value)


def test_parent_child_disagreement_fails_closed():
    doc = make_representative_document()
    text = dataclasses.replace(doc.nodes["text1"], parent_id=None)
    broken = dataclasses.replace(doc, nodes={**doc.nodes, "text1": text})
    with pytest.raises(IRValidationError) as raised:
        validate_document(broken)
    assert "node.parent_child_mismatch" in violation_codes(raised.value)


def test_cycle_fails_closed():
    doc = make_representative_document()
    text = dataclasses.replace(doc.nodes["text1"], children=("group1",))
    group = dataclasses.replace(doc.nodes["group1"], parent_id="text1")
    broken = dataclasses.replace(
        doc, nodes={**doc.nodes, "text1": text, "group1": group}
    )
    with pytest.raises(IRValidationError) as raised:
        validate_document(broken)
    assert "node.cycle" in violation_codes(raised.value)


def test_nonexistent_canvas_reference_fails_closed():
    doc = make_representative_document()
    image = dataclasses.replace(doc.nodes["image1"], canvas_id="missing-slide")
    broken = dataclasses.replace(doc, nodes={**doc.nodes, "image1": image})
    with pytest.raises(IRValidationError) as raised:
        validate_document(broken)
    assert "node.missing_canvas" in violation_codes(raised.value)


def test_missing_resource_reference_fails_closed():
    doc = make_representative_document()
    image = dataclasses.replace(
        doc.nodes["image1"], payload=ImagePayload(resource_id="missing")
    )
    broken = dataclasses.replace(doc, nodes={**doc.nodes, "image1": image})
    with pytest.raises(IRValidationError) as raised:
        validate_document(broken)
    assert "resource.missing" in violation_codes(raised.value)


def test_invalid_edit_target_fails_closed():
    doc = make_representative_document()
    edit = dataclasses.replace(doc.edits[0], target_node_id="missing")
    broken = dataclasses.replace(doc, edits=(edit, *doc.edits[1:]))
    with pytest.raises(IRValidationError) as raised:
        validate_document(broken)
    assert "edit.missing_target" in violation_codes(raised.value)


def test_invalid_sha256_fails_closed():
    doc = make_representative_document()
    bad_source = SourceDescriptor(format="pptx", sha256="not-a-digest")
    broken = dataclasses.replace(doc, source=bad_source)
    with pytest.raises(IRValidationError) as raised:
        validate_document(broken)
    assert "digest.invalid" in violation_codes(raised.value)


def test_duplicate_canvas_indices_fail_closed():
    doc = make_representative_document()
    second = dataclasses.replace(doc.canvases[1], index=0)
    broken = dataclasses.replace(doc, canvases=(doc.canvases[0], second))
    with pytest.raises(IRValidationError) as raised:
        validate_document(broken)
    assert "canvas.duplicate_index" in violation_codes(raised.value)


def test_node_map_key_must_match_node_id():
    doc = make_representative_document()
    nodes = dict(doc.nodes)
    nodes["alias"] = nodes.pop("table1")
    broken = dataclasses.replace(doc, nodes=nodes)
    with pytest.raises(IRValidationError) as raised:
        validate_document(broken)
    assert "node.key_mismatch" in violation_codes(raised.value)


def test_unknown_schema_major_is_rejected_with_typed_error():
    doc = dataclasses.replace(make_representative_document(), schema_version="1.0.0")
    with pytest.raises(UnsupportedSchemaVersionError) as raised:
        validate_document(doc)
    assert raised.value.code == "two_way.unsupported_schema_version"
