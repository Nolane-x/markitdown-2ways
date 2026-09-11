from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..._errors import UnsupportedEditError
from ...ir.nodes import Paragraph, TextPayload, TextRun
from ...ir.provenance import NativeLocator
from ...ir.style import Style

_R_NAMESPACES = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "http://purl.oclc.org/ooxml/officeDocument/relationships",
)
_W_NAMESPACES = (
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _is_w_element(element: Any, name: str) -> bool:
    tag = getattr(element, "tag", None)
    return isinstance(tag, str) and any(
        tag == f"{{{namespace}}}{name}" for namespace in _W_NAMESPACES
    )


def _attribute_value(element: Any, name: str, namespaces: tuple[str, ...]) -> str | None:
    for namespace in namespaces:
        value = element.get(f"{{{namespace}}}{name}")
        if value is not None:
            return value
    return None


def _w_value(element: Any, name: str) -> str | None:
    return _attribute_value(element, name, _W_NAMESPACES)


def _r_value(element: Any, name: str) -> str | None:
    return _attribute_value(element, name, _R_NAMESPACES)


def _bool_property(element: Any | None) -> bool | None:
    if element is None:
        return None
    value = _w_value(element, "val")
    if value is None:
        return True
    return value.lower() not in {"0", "false", "off", "no"}


def _run_style(run_element: Any) -> Style | None:
    rpr_nodes = [child for child in run_element if _is_w_element(child, "rPr")]
    if not rpr_nodes:
        return None
    rpr = rpr_nodes[0]
    direct: dict[str, object] = {}
    children = {
        _local_name(child.tag): child
        for child in rpr
        if isinstance(child.tag, str) and _is_w_element(child, _local_name(child.tag))
    }
    bold = _bool_property(children.get("b"))
    italic = _bool_property(children.get("i"))
    if bold is not None:
        direct["bold"] = bold
    if italic is not None:
        direct["italic"] = italic
    underline = children.get("u")
    if underline is not None:
        value = _w_value(underline, "val")
        direct["underline"] = "single" if value is None else value
    size = children.get("sz")
    size_value = _w_value(size, "val") if size is not None else None
    if size_value:
        try:
            direct["font_size_pt"] = int(size_value) / 2.0
        except (TypeError, ValueError):
            pass
    fonts = children.get("rFonts")
    if fonts is not None:
        family = _w_value(fonts, "ascii") or _w_value(fonts, "hAnsi")
        if family:
            direct["font_family"] = family
    color = children.get("color")
    if color is not None:
        value = _w_value(color, "val")
        if value and value.lower() != "auto":
            direct["color"] = f"#{value}"
    return Style(direct=direct) if direct else None


@dataclass(frozen=True)
class _Carrier:
    text_node: Any
    run_element: Any
    context: str | None
    run_index: int
    context_index: int


def _run_text_node(run_element: Any) -> Any | None:
    rpr_nodes = [child for child in run_element if _is_w_element(child, "rPr")]
    if len(rpr_nodes) > 1:
        raise UnsupportedEditError(
            "DOCX run contains multiple run-property containers.",
            details={"reason": "unsupported_text_structure", "element": "rPr"},
        )
    text_nodes = [child for child in run_element if _is_w_element(child, "t")]
    unsupported = [
        child
        for child in run_element
        if isinstance(child.tag, str)
        and not (_is_w_element(child, "rPr") or _is_w_element(child, "t"))
    ]
    if unsupported:
        raise UnsupportedEditError(
            "DOCX run contains unsupported native text structure.",
            details={
                "reason": "unsupported_text_structure",
                "elements": tuple(_local_name(item.tag) for item in unsupported),
            },
        )
    if len(text_nodes) > 1:
        raise UnsupportedEditError(
            "DOCX run contains multiple text carriers.",
            details={"reason": "unsupported_text_structure", "element": "t"},
        )
    return text_nodes[0] if text_nodes else None


def _collect_carriers(paragraph_element: Any) -> list[_Carrier]:
    if not _is_w_element(paragraph_element, "p"):
        raise UnsupportedEditError(
            "DOCX paragraph is not in a supported WordprocessingML namespace.",
            details={"reason": "unsupported_text_structure", "element": "p"},
        )
    carriers: list[_Carrier] = []
    run_index = 0
    context_index = 0
    seen_ppr = False
    for child in paragraph_element:
        if not isinstance(child.tag, str):
            continue
        name = _local_name(child.tag)
        if name == "pPr":
            if not _is_w_element(child, "pPr"):
                raise UnsupportedEditError(
                    "DOCX paragraph contains unsupported native structure.",
                    details={"reason": "unsupported_text_structure", "element": name},
                )
            if seen_ppr:
                raise UnsupportedEditError(
                    "DOCX paragraph contains multiple paragraph-property containers.",
                    details={"reason": "unsupported_text_structure", "element": "pPr"},
                )
            seen_ppr = True
            continue
        if name == "r":
            if not _is_w_element(child, "r"):
                raise UnsupportedEditError(
                    "DOCX paragraph contains unsupported native structure.",
                    details={"reason": "unsupported_text_structure", "element": name},
                )
            text_node = _run_text_node(child)
            if text_node is not None:
                carriers.append(
                    _Carrier(
                        text_node=text_node,
                        run_element=child,
                        context=None,
                        run_index=run_index,
                        context_index=context_index,
                    )
                )
            run_index += 1
            context_index += 1
            continue
        if name == "hyperlink":
            if not _is_w_element(child, "hyperlink"):
                raise UnsupportedEditError(
                    "DOCX hyperlink uses an unsupported native namespace.",
                    details={"reason": "unsupported_hyperlink_structure"},
                )
            relationship_id = _r_value(child, "id")
            if not relationship_id:
                raise UnsupportedEditError(
                    "DOCX hyperlink is not relationship-bound.",
                    details={"reason": "unsupported_hyperlink_structure"},
                )
            hyperlink_context_index = context_index
            for hyperlink_child in child:
                if not isinstance(hyperlink_child.tag, str):
                    continue
                hyperlink_name = _local_name(hyperlink_child.tag)
                if hyperlink_name != "r" or not _is_w_element(hyperlink_child, "r"):
                    raise UnsupportedEditError(
                        "DOCX hyperlink contains unsupported native structure.",
                        details={
                            "reason": "unsupported_hyperlink_structure",
                            "element": hyperlink_name,
                        },
                    )
                text_node = _run_text_node(hyperlink_child)
                if text_node is not None:
                    carriers.append(
                        _Carrier(
                            text_node=text_node,
                            run_element=hyperlink_child,
                            context=relationship_id,
                            run_index=run_index,
                            context_index=hyperlink_context_index,
                        )
                    )
                run_index += 1
            context_index += 1
            continue
        raise UnsupportedEditError(
            "DOCX paragraph contains unsupported native structure.",
            details={"reason": "unsupported_text_structure", "element": name},
        )
    return carriers


def paragraph_patch_compatible(paragraph_element: Any) -> bool:
    try:
        _collect_carriers(paragraph_element)
    except UnsupportedEditError:
        return False
    return True


def _run_locator(
    paragraph_locator: NativeLocator,
    carrier: _Carrier,
) -> NativeLocator:
    base_path = paragraph_locator.path or ""
    return NativeLocator(
        backend=paragraph_locator.backend,
        part_uri=paragraph_locator.part_uri,
        object_id=paragraph_locator.object_id,
        relationship_id=carrier.context,
        path=f"{base_path}/run[{carrier.run_index + 1}]",
        attributes={
            "run_index": carrier.run_index,
            "context_index": carrier.context_index,
            "hyperlink_relationship_id": carrier.context,
        },
    )


def extract_paragraph_payload(
    paragraph_element: Any,
    locator: NativeLocator,
) -> TextPayload:
    carriers = _collect_carriers(paragraph_element)
    runs = tuple(
        TextRun(
            text=carrier.text_node.text or "",
            style=_run_style(carrier.run_element),
            native_locator=_run_locator(locator, carrier),
        )
        for carrier in carriers
    )
    text = "".join(run.text for run in runs)
    ppr_nodes = [
        child for child in paragraph_element if _is_w_element(child, "pPr")
    ]
    alignment = None
    list_level = None
    if ppr_nodes:
        ppr = ppr_nodes[0]
        for child in ppr:
            if not isinstance(child.tag, str):
                continue
            name = _local_name(child.tag)
            if name == "jc" and _is_w_element(child, "jc"):
                alignment = _w_value(child, "val")
            elif name == "numPr" and _is_w_element(child, "numPr"):
                levels = [item for item in child if _is_w_element(item, "ilvl")]
                level_value = _w_value(levels[0], "val") if levels else None
                if level_value is not None:
                    try:
                        list_level = int(level_value)
                    except (TypeError, ValueError):
                        list_level = None
    return TextPayload(
        text=text,
        paragraphs=(
            Paragraph(
                runs=runs,
                list_level=list_level,
                alignment=alignment,
            ),
        ),
    )
