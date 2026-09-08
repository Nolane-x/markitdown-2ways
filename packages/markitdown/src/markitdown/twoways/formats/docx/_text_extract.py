from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..._errors import UnsupportedEditError
from ...ir.nodes import Paragraph, TextPayload, TextRun
from ...ir.provenance import NativeLocator
from ...ir.style import Style

_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _w_attr(name: str) -> str:
    return f"{{{_W_NS}}}{name}"


def _bool_property(element: Any | None) -> bool | None:
    if element is None:
        return None
    value = element.get(_w_attr("val"))
    if value is None:
        return True
    return value.lower() not in {"0", "false", "off", "no"}


def _run_style(run_element: Any) -> Style | None:
    rpr_nodes = [child for child in run_element if _local_name(child.tag) == "rPr"]
    if not rpr_nodes:
        return None
    rpr = rpr_nodes[0]
    direct: dict[str, object] = {}
    children = {_local_name(child.tag): child for child in rpr}
    bold = _bool_property(children.get("b"))
    italic = _bool_property(children.get("i"))
    if bold is not None:
        direct["bold"] = bold
    if italic is not None:
        direct["italic"] = italic
    underline = children.get("u")
    if underline is not None:
        direct["underline"] = underline.get(_w_attr("val"), "single")
    size = children.get("sz")
    if size is not None and size.get(_w_attr("val")):
        try:
            direct["font_size_pt"] = int(size.get(_w_attr("val"))) / 2.0
        except (TypeError, ValueError):
            pass
    fonts = children.get("rFonts")
    if fonts is not None:
        family = fonts.get(_w_attr("ascii")) or fonts.get(_w_attr("hAnsi"))
        if family:
            direct["font_family"] = family
    color = children.get("color")
    if color is not None:
        value = color.get(_w_attr("val"))
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
    text_nodes = [child for child in run_element if _local_name(child.tag) == "t"]
    unsupported = [
        child
        for child in run_element
        if _local_name(child.tag) not in {"rPr", "t"}
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
    carriers: list[_Carrier] = []
    run_index = 0
    context_index = 0
    for child in paragraph_element:
        name = _local_name(child.tag)
        if name == "pPr":
            continue
        if name == "r":
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
            relationship_id = child.get(f"{{{_R_NS}}}id")
            if not relationship_id:
                raise UnsupportedEditError(
                    "DOCX hyperlink is not relationship-bound.",
                    details={"reason": "unsupported_hyperlink_structure"},
                )
            hyperlink_context_index = context_index
            for hyperlink_child in child:
                hyperlink_name = _local_name(hyperlink_child.tag)
                if hyperlink_name != "r":
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
        child for child in paragraph_element if _local_name(child.tag) == "pPr"
    ]
    alignment = None
    list_level = None
    if ppr_nodes:
        ppr = ppr_nodes[0]
        for child in ppr:
            name = _local_name(child.tag)
            if name == "jc":
                alignment = child.get(_w_attr("val"))
            elif name == "numPr":
                levels = [item for item in child if _local_name(item.tag) == "ilvl"]
                if levels and levels[0].get(_w_attr("val")) is not None:
                    try:
                        list_level = int(levels[0].get(_w_attr("val")))
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
