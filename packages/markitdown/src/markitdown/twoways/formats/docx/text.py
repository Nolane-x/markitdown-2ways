from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from ..._errors import PatchPreconditionError, UnsupportedEditError
from ...ir.nodes import Paragraph, TextPayload, TextRun
from ...ir.provenance import NativeLocator
from ...ir.style import Style

_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


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
    ppr_nodes = [child for child in paragraph_element if _local_name(child.tag) == "pPr"]
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


def _owner_map(carriers: list[_Carrier]) -> tuple[list[int], list[str | None]]:
    owners: list[int] = []
    contexts: list[str | None] = []
    for carrier_index, carrier in enumerate(carriers):
        text = carrier.text_node.text or ""
        owners.extend([carrier_index] * len(text))
        contexts.extend([carrier.context] * len(text))
    return owners, contexts


def _single_context(contexts: list[str | None], start: int, end: int) -> str | None:
    observed = set(contexts[start:end])
    if len(observed) > 1:
        raise UnsupportedEditError(
            "DOCX edit crosses a plain-text/hyperlink context boundary.",
            details={"reason": "hyperlink_context_boundary"},
        )
    return next(iter(observed)) if observed else None


def _owner_for_context(
    carriers: list[_Carrier],
    owners: list[int],
    contexts: list[str | None],
    position: int,
    context: str | None,
) -> int:
    if position > 0 and contexts and contexts[position - 1] == context:
        return owners[position - 1]
    if position < len(contexts) and contexts[position] == context:
        return owners[position]
    for index, carrier in enumerate(carriers):
        if carrier.context == context:
            return index
    raise UnsupportedEditError(
        "DOCX paragraph has no existing run that can carry inserted text.",
        details={"reason": "no_style_context"},
    )


def _allocate_new_text(carriers: list[_Carrier], new_text: str) -> list[str]:
    if not carriers:
        if new_text:
            raise UnsupportedEditError(
                "DOCX paragraph has no existing run that can carry inserted text.",
                details={"reason": "no_style_context"},
            )
        return []
    old_text = "".join(carrier.text_node.text or "" for carrier in carriers)
    owners, contexts = _owner_map(carriers)
    output = ["" for _ in carriers]
    matcher = SequenceMatcher(None, old_text, new_text, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for old_index, character in zip(range(i1, i2), new_text[j1:j2]):
                output[owners[old_index]] += character
            continue
        if tag == "delete":
            _single_context(contexts, i1, i2)
            continue
        if tag == "replace":
            context = _single_context(contexts, i1, i2)
            owner = _owner_for_context(carriers, owners, contexts, i1, context)
            output[owner] += new_text[j1:j2]
            continue
        if tag == "insert":
            left_context = contexts[i1 - 1] if i1 > 0 and contexts else None
            right_context = contexts[i1] if i1 < len(contexts) else None
            if i1 > 0 and i1 < len(contexts) and left_context != right_context:
                raise UnsupportedEditError(
                    "DOCX insertion is ambiguous at a plain-text/hyperlink boundary.",
                    details={"reason": "hyperlink_context_boundary"},
                )
            context = left_context if i1 > 0 else right_context
            if not contexts:
                distinct = {carrier.context for carrier in carriers}
                if len(distinct) != 1:
                    raise UnsupportedEditError(
                        "DOCX insertion has no unambiguous native text context.",
                        details={"reason": "hyperlink_context_boundary"},
                    )
                context = next(iter(distinct))
            owner = _owner_for_context(carriers, owners, contexts, i1, context)
            output[owner] += new_text[j1:j2]
            continue
        raise AssertionError(f"unexpected SequenceMatcher opcode: {tag}")
    return output


def patch_paragraph_text(
    paragraph_element: Any,
    *,
    old_text: str,
    new_text: str,
) -> None:
    if "\n" in old_text or "\n" in new_text or "\r" in old_text or "\r" in new_text:
        raise UnsupportedEditError(
            "Phase D v1 cannot add or remove DOCX paragraphs.",
            details={"reason": "paragraph_count_change"},
        )
    carriers = _collect_carriers(paragraph_element)
    actual_old = "".join(carrier.text_node.text or "" for carrier in carriers)
    if actual_old != old_text:
        raise PatchPreconditionError(
            "DOCX native run text no longer matches the IR.",
            details={"reason": "native_text_mismatch", "expected": old_text, "actual": actual_old},
        )
    allocated = _allocate_new_text(carriers, new_text)
    for carrier, text in zip(carriers, allocated):
        carrier.text_node.text = text
        if text[:1].isspace() or text[-1:].isspace():
            carrier.text_node.set(_XML_SPACE, "preserve")
        else:
            carrier.text_node.attrib.pop(_XML_SPACE, None)
