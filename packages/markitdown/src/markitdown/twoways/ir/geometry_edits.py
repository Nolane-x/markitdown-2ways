from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

from .._errors import UnsupportedEditError
from .geometry import Geometry


_MOVE_RESIZE_FIELDS = frozenset({"x", "y", "width", "height"})


def _fail(message: str, *, reason: str, **details: object) -> None:
    raise UnsupportedEditError(message, details={"reason": reason, **details})


def _finite_number(field: str, value: object) -> float:
    if type(value) not in {int, float} or not isfinite(float(value)):
        _fail(
            "move_resize geometry values must be finite numbers.",
            reason="invalid_geometry_value",
            field=field,
        )
    result = float(value)
    if field in {"width", "height"} and result <= 0:
        _fail(
            "move_resize width and height must be strictly positive.",
            reason="invalid_geometry_value",
            field=field,
        )
    return result


def validate_move_resize(current: Geometry | None, raw: Any) -> Geometry:
    if current is None:
        _fail(
            "move_resize requires existing source geometry.",
            reason="missing_geometry",
        )
    if not isinstance(raw, Mapping) or not raw:
        _fail(
            "move_resize requires a non-empty mapping payload.",
            reason="invalid_edit_payload",
        )

    unknown = [field for field in raw if field not in _MOVE_RESIZE_FIELDS]
    if unknown:
        _fail(
            "move_resize payload contains unsupported geometry fields.",
            reason="unsupported_geometry_field",
            fields=tuple(sorted(str(field) for field in unknown)),
        )

    values = {
        "x": float(current.x),
        "y": float(current.y),
        "width": float(current.width),
        "height": float(current.height),
    }
    for field, value in raw.items():
        if not isinstance(field, str):
            _fail(
                "move_resize geometry field names must be strings.",
                reason="unsupported_geometry_field",
                field=repr(field),
            )
        values[field] = _finite_number(field, value)

    for field in ("width", "height"):
        if values[field] <= 0:
            _fail(
                "move_resize target geometry must have positive dimensions.",
                reason="invalid_geometry_value",
                field=field,
            )

    unchanged = (
        values["x"] == float(current.x)
        and values["y"] == float(current.y)
        and values["width"] == float(current.width)
        and values["height"] == float(current.height)
    )
    if unchanged:
        _fail(
            "move_resize must change at least one geometry value.",
            reason="no_op_geometry_update",
        )

    return Geometry(
        x=values["x"],
        y=values["y"],
        width=values["width"],
        height=values["height"],
        rotation=current.rotation,
        unit=current.unit,
        origin=current.origin,
        transform=current.transform,
        source_values=current.source_values,
    )
