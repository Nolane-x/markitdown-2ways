import math
import pytest

from markitdown.twoways import Geometry, NativeLocator, Provenance, TwoWayError


def test_two_way_error_exposes_stable_code_and_details():
    exc = TwoWayError("two_way.test", "boom", {"node_id": "n1"})
    assert exc.code == "two_way.test"
    assert exc.details == {"node_id": "n1"}
    assert str(exc) == "boom"


def test_geometry_accepts_off_canvas_coordinates_but_not_negative_size():
    geometry = Geometry(x=-1, y=2, width=10, height=5, unit="pt")
    assert geometry.x == -1
    with pytest.raises(ValueError, match="width"):
        Geometry(x=0, y=0, width=-1, height=1, unit="pt")


def test_geometry_rejects_non_finite_numbers():
    with pytest.raises(ValueError, match="finite"):
        Geometry(x=math.nan, y=0, width=1, height=1, unit="pt")


def test_provenance_confidence_is_bounded():
    prov = Provenance(source_format="pptx", confidence=0.75)
    assert prov.confidence == 0.75
    with pytest.raises(ValueError, match="confidence"):
        Provenance(source_format="pptx", confidence=1.01)


def test_native_locator_requires_backend_only():
    locator = NativeLocator(backend="ooxml", creation_id="abc")
    assert locator.backend == "ooxml"
    assert locator.creation_id == "abc"


from markitdown.twoways import Resource
from markitdown.twoways.ir.document import DocumentIdFactory
from ._fixtures import make_representative_document


def test_representative_document_contains_ordered_canvases_and_unknown_native_node():
    doc = make_representative_document()
    assert [canvas.index for canvas in doc.canvases] == [0, 1]
    assert doc.nodes["unknown1"].kind == "unknown_native"
    assert doc.canvases[0].root_node_ids == ("group1",)


def test_document_id_factory_is_reproducible_for_same_seed():
    assert DocumentIdFactory("same").new("document") == DocumentIdFactory("same").new(
        "document"
    )


def test_document_id_factory_without_seed_is_explicitly_non_reproducible():
    factory = DocumentIdFactory()
    assert factory.reproducible is False
    assert factory.new("document") != factory.new("document")


def test_resource_does_not_inline_binary_bytes():
    resource = Resource(resource_id="r1", sha256="a" * 64, content_type="image/png")
    assert not hasattr(resource, "blob")


def test_edit_operation_uses_explicit_precondition():
    doc = make_representative_document()
    edit = doc.edits[0]
    assert edit.type == "replace_text"
    assert edit.precondition is not None
    assert edit.precondition.expected_old_value == "Revenue increased 38%"


def test_text_payload_keeps_plain_projection_and_rich_runs():
    doc = make_representative_document()
    payload = doc.nodes["text1"].payload
    assert payload.text == "Revenue increased 38%"
    assert payload.paragraphs[0].runs[1].text == "38%"
