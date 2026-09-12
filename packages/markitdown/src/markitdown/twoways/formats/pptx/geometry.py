from __future__ import annotations

from collections.abc import Iterable
from math import isfinite
from typing import Any

from ..._errors import (
    PatchPreconditionError,
    RoundTripVerificationError,
    UnsupportedEditError,
)
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.geometry import Geometry
from ...ir.geometry_edits import validate_move_resize


def _local_name(element: Any) -> str | None:
    tag = getattr(element, "tag", None)
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else None


def _direct_children(element: Any, name: str) -> list[Any]:
    return [child for child in element if _local_name(child) == name]


def _shape_transform(shape_element: Any) -> tuple[Any, Any, Any]:
    if _local_name(shape_element) == "grpSp":
        raise UnsupportedEditError(
            "PPTX group geometry uses a separate child coordinate space.",
            details={"reason": "pptx.geometry.group_coordinate_space"},
        )
    xfrms = [item for item in shape_element.iter() if _local_name(item) == "xfrm"]
    if len(xfrms) != 1:
        raise UnsupportedEditError(
            "PPTX shape does not expose one unambiguous native transform.",
            details={
                "reason": "pptx.geometry.ambiguous_transform",
                "count": len(xfrms),
            },
        )
    xfrm = xfrms[0]
    if _direct_children(xfrm, "chOff") or _direct_children(xfrm, "chExt"):
        raise UnsupportedEditError(
            "PPTX child-coordinate transforms require group-aware geometry editing.",
            details={"reason": "pptx.geometry.group_coordinate_space"},
        )
    off = _direct_children(xfrm, "off")
    ext = _direct_children(xfrm, "ext")
    if len(off) != 1 or len(ext) != 1:
        raise UnsupportedEditError(
            "PPTX shape transform must contain exactly one offset and extent.",
            details={"reason": "pptx.geometry.ambiguous_transform"},
        )
    return xfrm, off[0], ext[0]


def _native_values(shape_element: Any) -> tuple[int, int, int, int]:
    _, off, ext = _shape_transform(shape_element)
    raw = (off.get("x"), off.get("y"), ext.get("cx"), ext.get("cy"))
    try:
        values = tuple(int(value) for value in raw)
    except (TypeError, ValueError) as exc:
        raise UnsupportedEditError(
            "PPTX shape transform contains non-integer EMU values.",
            details={"reason": "pptx.geometry.invalid_native_transform"},
        ) from exc
    return values  # type: ignore[return-value]


def _representable_emu(name: str, value: float) -> int:
    if not isfinite(value) or value != round(value):
        raise UnsupportedEditError(
            "PPTX geometry values must be exactly representable as integer EMUs.",
            details={
                "reason": "pptx.geometry.unrepresentable_emu",
                "field": name,
                "value": value,
            },
        )
    return int(value)


def _geometry_values(geometry: Geometry) -> tuple[int, int, int, int]:
    if geometry.unit != "emu":
        raise UnsupportedEditError(
            "PPTX native geometry patching requires EMU source geometry.",
            details={"reason": "pptx.geometry.unsupported_unit", "unit": geometry.unit},
        )
    return (
        _representable_emu("x", float(geometry.x)),
        _representable_emu("y", float(geometry.y)),
        _representable_emu("width", float(geometry.width)),
        _representable_emu("height", float(geometry.height)),
    )


def geometry_patchability(
    shape_element: Any,
    current: Geometry,
) -> tuple[bool, str | None]:
    try:
        current_values = _geometry_values(current)
        native_values = _native_values(shape_element)
    except UnsupportedEditError as exc:
        reason = exc.details.get("reason")
        return False, str(reason or "pptx.geometry.unsupported_native_transform")
    if current_values != native_values:
        return False, "pptx.geometry.native_mismatch"
    return True, None


def patch_shape_geometry(
    shape_element: Any,
    *,
    current: Geometry,
    target: Geometry,
) -> None:
    current_values = _geometry_values(current)
    target_values = _geometry_values(target)
    if target.rotation != current.rotation:
        raise UnsupportedEditError(
            "PPTX move_resize does not mutate rotation in this tranche.",
            details={"reason": "pptx.geometry.rotation_requires_explicit_edit"},
        )
    if target.origin != current.origin or target.transform != current.transform:
        raise UnsupportedEditError(
            "PPTX move_resize does not rewrite origin or transform matrices.",
            details={"reason": "pptx.geometry.transform_requires_explicit_edit"},
        )

    actual = _native_values(shape_element)
    if actual != current_values:
        raise PatchPreconditionError(
            "PPTX native geometry no longer matches the source IR.",
            details={
                "reason": "native_geometry_mismatch",
                "expected": current_values,
                "actual": actual,
            },
        )
    if actual == target_values:
        raise UnsupportedEditError(
            "PPTX geometry patch must change at least one coordinate.",
            details={"reason": "no_op_geometry_update"},
        )

    _, off, ext = _shape_transform(shape_element)
    off.set("x", str(target_values[0]))
    off.set("y", str(target_values[1]))
    ext.set("cx", str(target_values[2]))
    ext.set("cy", str(target_values[3]))


def verify_geometry_readback(
    original_document: DocumentIR,
    output_document: DocumentIR,
    edits: Iterable[EditOperation],
) -> tuple[str, ...]:
    affected: list[str] = []
    for edit in edits:
        if edit.type != "move_resize" or edit.target_node_id is None:
            continue
        source_node = original_document.nodes.get(edit.target_node_id)
        output_node = output_document.nodes.get(edit.target_node_id)
        if source_node is None or output_node is None or source_node.geometry is None:
            raise RoundTripVerificationError(
                "PPTX geometry target identity did not survive round trip.",
                details={
                    "check": "pptx.geometry.readback",
                    "target": edit.target_node_id,
                },
            )
        expected = validate_move_resize(source_node.geometry, edit.payload)
        actual = output_node.geometry
        if actual is None:
            raise RoundTripVerificationError(
                "PPTX geometry target lost its geometry during readback.",
                details={
                    "check": "pptx.geometry.readback",
                    "target": edit.target_node_id,
                },
            )
        expected_values = (
            expected.x,
            expected.y,
            expected.width,
            expected.height,
            expected.rotation,
            expected.unit,
        )
        actual_values = (
            actual.x,
            actual.y,
            actual.width,
            actual.height,
            actual.rotation,
            actual.unit,
        )
        if actual_values != expected_values:
            raise RoundTripVerificationError(
                "PPTX geometry did not read back exactly as requested.",
                details={
                    "check": "pptx.geometry.readback",
                    "target": edit.target_node_id,
                    "expected": expected_values,
                    "actual": actual_values,
                },
            )
        affected.append(edit.target_node_id)
    return tuple(sorted(set(affected)))
