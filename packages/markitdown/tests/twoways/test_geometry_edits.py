from __future__ import annotations

import pytest

from markitdown.twoways import UnsupportedEditError
from markitdown.twoways.ir.geometry import Geometry


def _validate(current: Geometry | None, raw: object) -> Geometry:
    try:
        from markitdown.twoways.ir.geometry_edits import validate_move_resize
    except ModuleNotFoundError:
        pytest.fail("geometry_edits module is not implemented yet")
    return validate_move_resize(current, raw)


def test_validate_move_resize_applies_partial_update_and_preserves_native_context():
    current = Geometry(
        x=10.0,
        y=20.0,
        width=300.0,
        height=120.0,
        rotation=15.0,
        unit="emu",
        origin="top-left",
        transform=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        source_values={"x": "10", "cx": "300"},
    )
    target = _validate(current, {"x": 25, "height": 150.5})
    assert target == Geometry(
        x=25.0,
        y=20.0,
        width=300.0,
        height=150.5,
        rotation=15.0,
        unit="emu",
        origin="top-left",
        transform=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        source_values={"x": "10", "cx": "300"},
    )


def test_validate_move_resize_requires_existing_geometry():
    with pytest.raises(UnsupportedEditError) as exc:
        _validate(None, {"x": 1})
    assert exc.value.details["reason"] == "missing_geometry"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("x", True),
        ("y", False),
        ("width", "100"),
        ("height", None),
        ("x", float("inf")),
        ("y", float("nan")),
        ("width", 0),
        ("width", -1),
        ("height", 0.0),
        ("height", -0.1),
    ],
)
def test_validate_move_resize_rejects_invalid_values(field: str, value: object):
    current = Geometry(x=1, y=2, width=100, height=50, unit="emu")
    with pytest.raises(UnsupportedEditError) as exc:
        _validate(current, {field: value})
    assert exc.value.details["reason"] == "invalid_geometry_value"


@pytest.mark.parametrize(
    "field",
    ["rotation", "unit", "origin", "transform", "source_values", "skew", "z"],
)
def test_validate_move_resize_rejects_unsupported_fields(field: str):
    current = Geometry(x=1, y=2, width=100, height=50, unit="emu")
    with pytest.raises(UnsupportedEditError) as exc:
        _validate(current, {field: 10})
    assert exc.value.details["reason"] == "unsupported_geometry_field"


def test_validate_move_resize_rejects_empty_and_no_op_payloads():
    current = Geometry(x=1, y=2, width=100, height=50, unit="emu")
    with pytest.raises(UnsupportedEditError) as empty:
        _validate(current, {})
    assert empty.value.details["reason"] == "invalid_edit_payload"

    with pytest.raises(UnsupportedEditError) as noop:
        _validate(current, {"x": 1.0, "width": 100})
    assert noop.value.details["reason"] == "no_op_geometry_update"


def test_validate_move_resize_rejects_non_mapping_payload():
    with pytest.raises(UnsupportedEditError) as exc:
        _validate(Geometry(width=10, height=10), [("x", 1)])
    assert exc.value.details["reason"] == "invalid_edit_payload"
