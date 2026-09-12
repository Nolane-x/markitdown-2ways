from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any, Iterable

from ..._errors import (
    PatchPreconditionError,
    RoundTripVerificationError,
    UnsupportedEditError,
)
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import TextPayload
from ...ir.style_edits import _canonical_style_mapping, validate_text_style_update

_DRAWINGML_NAMESPACES = frozenset(
    {
        "http://schemas.openxmlformats.org/drawingml/2006/main",
        "http://purl.oclc.org/ooxml/drawingml/main",
    }
)
_UNDERLINE_FROM_XML = {"none": "none", "sng": "single", "dbl": "double"}
_UNDERLINE_TO_XML = {"none": "none", "single": "sng", "double": "dbl"}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _namespace(tag: str) -> str | None:
    if not tag.startswith("{") or "}" not in tag:
        return None
    return tag[1:].split("}", 1)[0]


def _bool_attribute(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.lower() not in {"0", "false", "off", "no"}


def _direct_child(element: Any, name: str) -> list[Any]:
    return [
        child
        for child in element
        if isinstance(getattr(child, "tag", None), str)
        and _local_name(child.tag) == name
    ]


def _require_run_namespace(run_element: Any) -> str:
    tag = getattr(run_element, "tag", None)
    namespace = _namespace(tag) if isinstance(tag, str) else None
    if _local_name(tag) != "r" or namespace not in _DRAWINGML_NAMESPACES:
        raise UnsupportedEditError(
            "PPTX style patch requires a DrawingML text run.",
            details={"reason": "pptx.text.ambiguous_run_layout"},
        )
    return namespace


def _run_property_element(run_element: Any) -> Any | None:
    namespace = _require_run_namespace(run_element)
    matches = [
        child
        for child in run_element
        if isinstance(getattr(child, "tag", None), str)
        and child.tag == f"{{{namespace}}}rPr"
    ]
    if len(matches) > 1:
        raise UnsupportedEditError(
            "PPTX text run contains multiple run-property containers.",
            details={"reason": "pptx.text.ambiguous_run_layout"},
        )
    return matches[0] if matches else None


def direct_run_style(run_element: Any) -> dict[str, object]:
    rpr = _run_property_element(run_element)
    if rpr is None:
        return {}

    direct: dict[str, object] = {}
    bold = _bool_attribute(rpr.get("b"))
    italic = _bool_attribute(rpr.get("i"))
    if bold is not None:
        direct["bold"] = bold
    if italic is not None:
        direct["italic"] = italic

    underline = rpr.get("u")
    if underline in _UNDERLINE_FROM_XML:
        direct["underline"] = _UNDERLINE_FROM_XML[underline]

    raw_size = rpr.get("sz")
    if raw_size is not None:
        try:
            size = int(raw_size)
        except ValueError:
            size = 0
        if size > 0:
            direct["font_size_pt"] = size / 100.0

    latin = _direct_child(rpr, "latin")
    if len(latin) > 1:
        raise UnsupportedEditError(
            "PPTX run contains multiple direct Latin font declarations.",
            details={"reason": "pptx.style.ambiguous_font_family"},
        )
    if latin:
        typeface = latin[0].get("typeface")
        if typeface:
            direct["font_family"] = typeface

    solid_fills = _direct_child(rpr, "solidFill")
    if len(solid_fills) > 1:
        raise UnsupportedEditError(
            "PPTX run contains multiple direct text fills.",
            details={"reason": "pptx.style.ambiguous_color"},
        )
    if solid_fills:
        colors = _direct_child(solid_fills[0], "srgbClr")
        if len(colors) == 1:
            value = colors[0].get("val")
            if value and len(value) == 6:
                direct["color"] = f"#{value.upper()}"

    return direct


def _flatten_native_runs(shape_element: Any) -> list[Any]:
    runs: list[Any] = []
    for paragraph in shape_element.xpath('.//*[local-name()="p"]'):
        paragraph_tag = getattr(paragraph, "tag", None)
        if not isinstance(paragraph_tag, str):
            continue
        paragraph_ns = _namespace(paragraph_tag)
        if paragraph_ns not in _DRAWINGML_NAMESPACES:
            continue
        for child in paragraph:
            tag = getattr(child, "tag", None)
            if not isinstance(tag, str):
                continue
            if _namespace(tag) != paragraph_ns:
                raise UnsupportedEditError(
                    "PPTX text paragraph mixes DrawingML namespaces.",
                    details={"reason": "pptx.text.ambiguous_run_layout"},
                )
            name = _local_name(tag)
            if name in {"br", "fld"}:
                raise UnsupportedEditError(
                    "PPTX style editing does not support line-break or field runs.",
                    details={"reason": "pptx.text.ambiguous_run_layout", "element": name},
                )
            if name in {"pPr", "endParaRPr"}:
                continue
            if name != "r":
                raise UnsupportedEditError(
                    "PPTX text paragraph contains unsupported native run structure.",
                    details={"reason": "pptx.text.ambiguous_run_layout", "element": name},
                )
            text_nodes = _direct_child(child, "t")
            rpr_nodes = _direct_child(child, "rPr")
            unsupported = [
                item
                for item in child
                if isinstance(getattr(item, "tag", None), str)
                and _local_name(item.tag) not in {"rPr", "t"}
            ]
            if len(text_nodes) != 1 or len(rpr_nodes) > 1 or unsupported:
                raise UnsupportedEditError(
                    "PPTX text run is not structurally safe for direct style editing.",
                    details={"reason": "pptx.text.ambiguous_run_layout"},
                )
            runs.append(child)
    return runs


def _native_run(shape_element: Any, run_index: int) -> Any:
    runs = _flatten_native_runs(shape_element)
    if run_index < 0 or run_index >= len(runs):
        raise UnsupportedEditError(
            "PPTX style run index is outside the native text runs.",
            details={"reason": "run_out_of_range", "run_index": run_index},
        )
    return runs[run_index]


def _ensure_rpr(run_element: Any) -> Any:
    rpr = _run_property_element(run_element)
    if rpr is not None:
        return rpr
    from lxml import etree

    namespace = _require_run_namespace(run_element)
    rpr = etree.Element(f"{{{namespace}}}rPr")
    run_element.insert(0, rpr)
    return rpr


def _set_bool_attribute(rpr: Any, name: str, value: object | None) -> None:
    if value is None:
        rpr.attrib.pop(name, None)
    else:
        rpr.set(name, "1" if value is True else "0")


def _set_size(rpr: Any, value: object | None) -> None:
    if value is None:
        rpr.attrib.pop("sz", None)
        return
    size = float(value)
    raw = size * 100.0
    rounded = round(raw)
    if not isfinite(raw) or abs(raw - rounded) > 1e-9:
        raise UnsupportedEditError(
            "PPTX font size must be exactly representable in hundredths of a point.",
            details={"reason": "pptx.style.unrepresentable_font_size", "value": value},
        )
    rpr.set("sz", str(int(rounded)))


def _set_font_family(rpr: Any, value: object | None) -> None:
    latin = _direct_child(rpr, "latin")
    if len(latin) > 1:
        raise UnsupportedEditError(
            "PPTX run contains multiple direct Latin font declarations.",
            details={"reason": "pptx.style.ambiguous_font_family"},
        )
    if value is None:
        if latin:
            rpr.remove(latin[0])
        return
    if latin:
        target = latin[0]
    else:
        from lxml import etree

        namespace = _namespace(rpr.tag)
        target = etree.Element(f"{{{namespace}}}latin")
        rpr.append(target)
    target.set("typeface", str(value))


def _simple_rgb_fill(rpr: Any) -> tuple[Any | None, Any | None]:
    fills = _direct_child(rpr, "solidFill")
    if len(fills) > 1:
        raise UnsupportedEditError(
            "PPTX run contains multiple direct text fills.",
            details={"reason": "pptx.style.ambiguous_color"},
        )
    if not fills:
        return None, None
    colors = _direct_child(fills[0], "srgbClr")
    if len(colors) == 1 and len(fills[0]) == 1:
        return fills[0], colors[0]
    return fills[0], None


def _set_color(
    rpr: Any,
    *,
    source_style: Mapping[str, object],
    target_style: Mapping[str, object],
) -> None:
    source_has = "color" in source_style
    target_has = "color" in target_style
    if not source_has and not target_has:
        return

    fill, rgb = _simple_rgb_fill(rpr)
    if fill is not None and rgb is None:
        raise UnsupportedEditError(
            "PPTX theme/complex text color requires an explicit theme-aware edit.",
            details={"reason": "pptx.style.theme_color_requires_explicit_edit"},
        )

    if not target_has:
        if fill is not None:
            rpr.remove(fill)
        return

    if fill is None:
        from lxml import etree

        namespace = _namespace(rpr.tag)
        fill = etree.Element(f"{{{namespace}}}solidFill")
        rgb = etree.Element(f"{{{namespace}}}srgbClr")
        fill.append(rgb)
        rpr.append(fill)
    assert rgb is not None
    rgb.set("val", str(target_style["color"])[1:].upper())


def patch_text_run_style(
    shape_element: Any,
    *,
    run_index: int,
    old_style: Mapping[str, object],
    new_style: Mapping[str, object],
) -> None:
    canonical_old = _canonical_style_mapping(
        old_style,
        allow_clear=False,
        require_non_empty=False,
    )
    canonical_target = _canonical_style_mapping(
        new_style,
        allow_clear=False,
        require_non_empty=False,
    )
    run = _native_run(shape_element, run_index)
    native_style = direct_run_style(run)
    if native_style != canonical_old:
        raise PatchPreconditionError(
            "PPTX native run style no longer matches the source IR.",
            details={
                "reason": "run_style_mismatch",
                "run_index": run_index,
                "expected": canonical_old,
                "actual": native_style,
            },
        )
    if native_style == canonical_target:
        raise UnsupportedEditError(
            "PPTX style patch must change at least one direct style value.",
            details={"reason": "no_op_style_update", "run_index": run_index},
        )

    rpr = _ensure_rpr(run)
    _set_bool_attribute(rpr, "b", canonical_target.get("bold"))
    _set_bool_attribute(rpr, "i", canonical_target.get("italic"))

    underline = canonical_target.get("underline")
    if underline is None:
        rpr.attrib.pop("u", None)
    else:
        rpr.set("u", _UNDERLINE_TO_XML[str(underline)])

    _set_size(rpr, canonical_target.get("font_size_pt"))
    _set_font_family(rpr, canonical_target.get("font_family"))
    _set_color(
        rpr,
        source_style=canonical_old,
        target_style=canonical_target,
    )


def _ir_direct_style(payload: TextPayload, run_index: int) -> dict[str, object]:
    runs = tuple(run for paragraph in payload.paragraphs for run in paragraph.runs)
    if run_index < 0 or run_index >= len(runs):
        raise RoundTripVerificationError(
            "PPTX style target run disappeared during readback.",
            details={"check": "pptx.style.readback", "run_index": run_index},
        )
    raw = {} if runs[run_index].style is None else dict(runs[run_index].style.direct)
    return _canonical_style_mapping(
        raw,
        allow_clear=False,
        require_non_empty=False,
    )


def verify_text_style_readback(
    original_document: DocumentIR,
    output_document: DocumentIR,
    edits: Iterable[EditOperation],
) -> tuple[str, ...]:
    affected: list[str] = []
    for edit in edits:
        if edit.type != "set_text_style" or edit.target_node_id is None:
            continue
        source_node = original_document.nodes.get(edit.target_node_id)
        output_node = output_document.nodes.get(edit.target_node_id)
        if (
            source_node is None
            or output_node is None
            or not isinstance(source_node.payload, TextPayload)
            or not isinstance(output_node.payload, TextPayload)
        ):
            raise RoundTripVerificationError(
                "PPTX style target identity did not survive round trip.",
                details={"check": "pptx.style.readback", "target": edit.target_node_id},
            )
        run_index, _, expected = validate_text_style_update(source_node.payload, edit.payload)
        actual = _ir_direct_style(output_node.payload, run_index)
        if actual != expected:
            raise RoundTripVerificationError(
                "PPTX direct run style did not read back as requested.",
                details={
                    "check": "pptx.style.readback",
                    "target": edit.target_node_id,
                    "run_index": run_index,
                    "expected": expected,
                    "actual": actual,
                },
            )
        affected.append(edit.target_node_id)
    return tuple(sorted(set(affected)))
