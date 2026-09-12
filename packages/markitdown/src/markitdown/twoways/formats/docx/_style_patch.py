from __future__ import annotations

from collections.abc import Mapping
from math import isclose
from typing import Any

from ..._errors import PatchPreconditionError, UnsupportedEditError
from ._text_extract import _collect_carriers, _run_style


_RPR_ORDER = (
    "rStyle",
    "rFonts",
    "b",
    "bCs",
    "i",
    "iCs",
    "caps",
    "smallCaps",
    "strike",
    "dstrike",
    "outline",
    "shadow",
    "emboss",
    "imprint",
    "noProof",
    "snapToGrid",
    "vanish",
    "webHidden",
    "color",
    "spacing",
    "w",
    "kern",
    "position",
    "sz",
    "szCs",
    "highlight",
    "u",
    "effect",
    "bdr",
    "shd",
    "fitText",
    "vertAlign",
    "rtl",
    "cs",
    "em",
    "lang",
    "eastAsianLayout",
    "specVanish",
    "oMath",
)
_ORDER_INDEX = {name: index for index, name in enumerate(_RPR_ORDER)}
_SUPPORTED_NATIVE = {
    "bold": "b",
    "italic": "i",
    "underline": "u",
    "font_size_pt": "sz",
    "font_family": "rFonts",
    "color": "color",
}


def _local_name(tag: object) -> str | None:
    if not isinstance(tag, str):
        return None
    return tag.rsplit("}", 1)[-1]


def _namespace(tag: str) -> str:
    if not tag.startswith("{") or "}" not in tag:
        raise UnsupportedEditError(
            "DOCX run uses an unsupported namespace.",
            details={"reason": "unsupported_text_structure"},
        )
    return tag[1:].split("}", 1)[0]


def _w_attr(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def _native_style(run_element: Any) -> dict[str, object]:
    style = _run_style(run_element)
    direct = {} if style is None else dict(style.direct)
    color = direct.get("color")
    if isinstance(color, str):
        direct["color"] = color.upper()
    size = direct.get("font_size_pt")
    if type(size) in {int, float}:
        direct["font_size_pt"] = float(size)
    return direct


def _property(rpr: Any, namespace: str, local: str) -> Any | None:
    matches = [
        child
        for child in rpr
        if isinstance(getattr(child, "tag", None), str)
        and child.tag == f"{{{namespace}}}{local}"
    ]
    if len(matches) > 1:
        raise UnsupportedEditError(
            "DOCX run contains duplicate style properties.",
            details={
                "reason": "unsupported_text_structure",
                "element": local,
            },
        )
    return matches[0] if matches else None


def _insert_ordered(rpr: Any, element: Any) -> None:
    local = _local_name(element.tag)
    rank = _ORDER_INDEX.get(local or "", len(_RPR_ORDER))
    insertion_index = len(rpr)
    for index, child in enumerate(rpr):
        child_local = _local_name(getattr(child, "tag", None))
        child_rank = _ORDER_INDEX.get(child_local or "", len(_RPR_ORDER))
        if child_rank > rank:
            insertion_index = index
            break
    rpr.insert(insertion_index, element)


def _get_or_add_property(rpr: Any, namespace: str, local: str) -> Any:
    existing = _property(rpr, namespace, local)
    if existing is not None:
        return existing
    element = rpr.makeelement(f"{{{namespace}}}{local}")
    _insert_ordered(rpr, element)
    return element


def _remove_property(rpr: Any, namespace: str, local: str) -> None:
    element = _property(rpr, namespace, local)
    if element is not None:
        rpr.remove(element)


def _set_on_off(rpr: Any, namespace: str, local: str, value: object | None) -> None:
    if value is None:
        _remove_property(rpr, namespace, local)
        return
    if type(value) is not bool:
        raise UnsupportedEditError(
            "DOCX boolean run style must be true or false.",
            details={"reason": "invalid_style_value", "field": local},
        )
    element = _get_or_add_property(rpr, namespace, local)
    val = _w_attr(namespace, "val")
    if value:
        element.attrib.pop(val, None)
    else:
        element.set(val, "0")


def _set_underline(rpr: Any, namespace: str, value: object | None) -> None:
    if value is None:
        _remove_property(rpr, namespace, "u")
        return
    if value not in {"none", "single", "double"}:
        raise UnsupportedEditError(
            "DOCX underline value is not portable in this tranche.",
            details={"reason": "invalid_style_value", "field": "underline"},
        )
    element = _get_or_add_property(rpr, namespace, "u")
    element.set(_w_attr(namespace, "val"), str(value))


def _set_size(rpr: Any, namespace: str, value: object | None) -> None:
    if value is None:
        _remove_property(rpr, namespace, "sz")
        return
    if type(value) not in {int, float}:
        raise UnsupportedEditError(
            "DOCX font size must be numeric.",
            details={"reason": "invalid_style_value", "field": "font_size_pt"},
        )
    half_points = float(value) * 2.0
    rounded = round(half_points)
    if half_points <= 0 or not isclose(half_points, rounded, rel_tol=0.0, abs_tol=1e-9):
        raise UnsupportedEditError(
            "DOCX font size must be exactly representable in half-points.",
            details={"reason": "docx.style.unrepresentable_font_size"},
        )
    element = _get_or_add_property(rpr, namespace, "sz")
    element.set(_w_attr(namespace, "val"), str(int(rounded)))


def _set_family(rpr: Any, namespace: str, value: object | None) -> None:
    if value is None:
        element = _property(rpr, namespace, "rFonts")
        if element is None:
            return
        element.attrib.pop(_w_attr(namespace, "ascii"), None)
        element.attrib.pop(_w_attr(namespace, "hAnsi"), None)
        if not element.attrib and len(element) == 0:
            rpr.remove(element)
        return
    if not isinstance(value, str) or not value.strip():
        raise UnsupportedEditError(
            "DOCX font family must be a non-empty string.",
            details={"reason": "invalid_style_value", "field": "font_family"},
        )
    element = _get_or_add_property(rpr, namespace, "rFonts")
    element.set(_w_attr(namespace, "ascii"), value.strip())
    element.set(_w_attr(namespace, "hAnsi"), value.strip())


def _set_color(rpr: Any, namespace: str, value: object | None) -> None:
    if value is None:
        _remove_property(rpr, namespace, "color")
        return
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        raise UnsupportedEditError(
            "DOCX color must use #RRGGBB syntax.",
            details={"reason": "invalid_style_value", "field": "color"},
        )
    element = _get_or_add_property(rpr, namespace, "color")
    for related in ("themeColor", "themeTint", "themeShade"):
        element.attrib.pop(_w_attr(namespace, related), None)
    element.set(_w_attr(namespace, "val"), value[1:].upper())


def _ensure_rpr(run_element: Any, namespace: str) -> Any:
    matches = [
        child
        for child in run_element
        if isinstance(getattr(child, "tag", None), str)
        and child.tag == f"{{{namespace}}}rPr"
    ]
    if len(matches) > 1:
        raise UnsupportedEditError(
            "DOCX run contains multiple run-property containers.",
            details={"reason": "unsupported_text_structure", "element": "rPr"},
        )
    if matches:
        return matches[0]
    rpr = run_element.makeelement(f"{{{namespace}}}rPr")
    run_element.insert(0, rpr)
    return rpr


def patch_docx_run_style(
    paragraph_element: Any,
    *,
    run_index: int,
    old_style: Mapping[str, object],
    new_style: Mapping[str, object],
) -> None:
    carriers = _collect_carriers(paragraph_element)
    if type(run_index) is not int or run_index < 0 or run_index >= len(carriers):
        raise UnsupportedEditError(
            "DOCX style run index is outside the native paragraph carriers.",
            details={"reason": "run_out_of_range", "run_index": run_index},
        )
    carrier = carriers[run_index]
    run_element = carrier.run_element
    native_style = _native_style(run_element)
    expected_style = dict(old_style)
    if native_style != expected_style:
        raise PatchPreconditionError(
            "DOCX native run style no longer matches the source IR.",
            details={
                "reason": "run_style_mismatch",
                "run_index": run_index,
                "expected": expected_style,
                "actual": native_style,
            },
        )

    unknown = set(new_style) - set(_SUPPORTED_NATIVE)
    if unknown:
        raise UnsupportedEditError(
            "DOCX style patch contains unsupported fields.",
            details={
                "reason": "unsupported_style_field",
                "fields": tuple(sorted(unknown)),
            },
        )

    namespace = _namespace(run_element.tag)
    rpr = _ensure_rpr(run_element, namespace)
    _set_family(rpr, namespace, new_style.get("font_family"))
    _set_on_off(rpr, namespace, "b", new_style.get("bold"))
    _set_on_off(rpr, namespace, "i", new_style.get("italic"))
    _set_color(rpr, namespace, new_style.get("color"))
    _set_size(rpr, namespace, new_style.get("font_size_pt"))
    _set_underline(rpr, namespace, new_style.get("underline"))

    if len(rpr) == 0 and not rpr.attrib:
        run_element.remove(rpr)
