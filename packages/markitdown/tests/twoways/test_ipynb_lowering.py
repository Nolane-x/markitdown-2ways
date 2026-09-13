from __future__ import annotations

from markitdown.twoways.formats.ipynb.lowering import (
    lower_ipynb_cell_sources,
    repartition_cell_source,
)
from markitdown.twoways.formats.ipynb.parser import parse_ipynb_source
from markitdown.twoways.ir.edits import INITIAL_EDIT_TYPES


def _pointer(shadow, edit):
    assert edit.target_node_id is not None
    return shadow.nodes[edit.target_node_id].metadata["json.pointer"]


def test_h6_edit_type_is_registered() -> None:
    assert "replace_ipynb_cell_source" in INITIAL_EDIT_TYPES


def test_repartition_preserves_cardinality_and_join_invariant() -> None:
    assert repartition_cell_source("a\nb\n", 3) == ("a\n", "b\n", "")
    assert repartition_cell_source("a\nb\nc\nd", 2) == ("a\n", "b\nc\nd")
    assert repartition_cell_source("a\nb", 2) == ("a\n", "b")
    assert repartition_cell_source("one", 3) == ("one", "", "")
    assert repartition_cell_source("", 2) == ("", "")


def test_repartition_rejects_non_positive_segment_count() -> None:
    import pytest

    with pytest.raises(ValueError):
        repartition_cell_source("x", 0)


def test_string_source_lowers_to_one_shadow_json_scalar() -> None:
    source = (
        b'{"cells":[{"cell_type":"markdown","metadata":{},"source":"old"}],'
        b'"metadata":{},"nbformat":4,"nbformat_minor":5}'
    )
    parsed = parse_ipynb_source(source)

    shadow, edits = lower_ipynb_cell_sources(source, parsed, {0: "new"})

    assert len(edits) == 1
    assert edits[0].type == "replace_json_scalar"
    assert edits[0].payload == {"value": "new"}
    assert _pointer(shadow, edits[0]) == "/cells/0/source"


def test_array_source_lowers_only_changed_existing_segments() -> None:
    source = (
        b'{"cells":[{"cell_type":"code","metadata":{},"outputs":[],'
        b'"execution_count":null,"source":["a\\n","b"]}],'
        b'"metadata":{},"nbformat":4,"nbformat_minor":5}'
    )
    parsed = parse_ipynb_source(source)

    shadow, edits = lower_ipynb_cell_sources(source, parsed, {0: "a\nB"})

    assert len(edits) == 1
    assert _pointer(shadow, edits[0]) == "/cells/0/source/1"
    assert edits[0].payload == {"value": "B"}


def test_multi_cell_lowering_is_canonical_by_cell_then_segment() -> None:
    source = (
        b'{"cells":['
        b'{"cell_type":"markdown","metadata":{},"source":["a\\n","b"]},'
        b'{"cell_type":"raw","metadata":{},"source":"c"}'
        b'],"metadata":{},"nbformat":4,"nbformat_minor":5}'
    )
    parsed = parse_ipynb_source(source)

    shadow, edits = lower_ipynb_cell_sources(
        source,
        parsed,
        {1: "C", 0: "A\nB"},
    )

    assert [_pointer(shadow, edit) for edit in edits] == [
        "/cells/0/source/0",
        "/cells/0/source/1",
        "/cells/1/source",
    ]
    assert [edit.payload["value"] for edit in edits] == ["A\n", "B", "C"]
