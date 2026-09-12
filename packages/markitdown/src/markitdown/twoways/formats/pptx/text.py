from __future__ import annotations

from typing import Any

from ...ir.nodes import Paragraph, TextPayload, TextRun
from ...ir.style import Style
from .locators import stable_run_id
from .style import direct_run_style


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _direct_run_style(run: Any) -> Style | None:
    direct = direct_run_style(run._r)
    return Style(direct=direct) if direct else None


def text_patch_compatible(shape: Any) -> bool:
    if not shape.has_text_frame:
        return False
    for paragraph in shape.text_frame.paragraphs:
        paragraph_element = paragraph._p
        for child in paragraph_element:
            name = _local_name(child.tag)
            if name in {"br", "fld"}:
                return False
            if name == "r":
                text_nodes = [item for item in child if _local_name(item.tag) == "t"]
                if len(text_nodes) != 1:
                    return False
    return True


def extract_text_payload(shape: Any, locator: Any) -> TextPayload:
    paragraphs: list[Paragraph] = []
    for paragraph_index, paragraph in enumerate(shape.text_frame.paragraphs):
        runs: list[TextRun] = []
        for run_index, run in enumerate(paragraph.runs):
            runs.append(
                TextRun(
                    text=run.text or "",
                    style=_direct_run_style(run),
                    native_locator=stable_run_id(
                        locator,
                        paragraph_index=paragraph_index,
                        run_index=run_index,
                    ),
                )
            )
        alignment = None if paragraph.alignment is None else str(paragraph.alignment)
        level = getattr(paragraph, "level", None)
        paragraphs.append(
            Paragraph(
                runs=tuple(runs),
                list_level=level,
                alignment=alignment,
            )
        )
    return TextPayload(text=shape.text or "", paragraphs=tuple(paragraphs))


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _paragraph_run_text_nodes(paragraph_element: Any) -> list[Any]:
    from ..._errors import UnsupportedEditError

    text_nodes: list[Any] = []
    for child in paragraph_element:
        name = _xml_local_name(child.tag)
        if name in {"br", "fld"}:
            raise UnsupportedEditError(
                "PPTX text structure contains unsupported line-break/field elements.",
                details={"reason": "unsupported_text_structure", "element": name},
            )
        if name != "r":
            continue
        run_text_nodes = [item for item in child if _xml_local_name(item.tag) == "t"]
        if len(run_text_nodes) != 1:
            raise UnsupportedEditError(
                "PPTX run does not contain exactly one text node.",
                details={"reason": "unsupported_text_structure", "element": "r"},
            )
        text_nodes.append(run_text_nodes[0])
    return text_nodes


def _owner_map(run_texts: list[str]) -> list[int]:
    owners: list[int] = []
    for run_index, text in enumerate(run_texts):
        owners.extend([run_index] * len(text))
    return owners


def _allocate_new_text(run_texts: list[str], new_text: str) -> list[str]:
    from difflib import SequenceMatcher

    from ..._errors import UnsupportedEditError

    if not run_texts:
        if new_text:
            raise UnsupportedEditError(
                "PPTX paragraph has no existing run that can carry inserted text.",
                details={"reason": "no_style_context"},
            )
        return []

    old_text = "".join(run_texts)
    owners = _owner_map(run_texts)
    output = ["" for _ in run_texts]
    matcher = SequenceMatcher(None, old_text, new_text, autojunk=False)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for old_index, character in zip(range(i1, i2), new_text[j1:j2]):
                output[owners[old_index]] += character
            continue
        if tag == "delete":
            continue
        if tag == "replace":
            if i1 < i2 and owners:
                owner = owners[i1]
            elif i1 > 0 and owners:
                owner = owners[i1 - 1]
            elif i1 < len(owners):
                owner = owners[i1]
            else:
                owner = len(run_texts) - 1
            output[owner] += new_text[j1:j2]
            continue
        if tag == "insert":
            if i1 > 0 and owners:
                owner = owners[i1 - 1]
            elif i1 < len(owners):
                owner = owners[i1]
            else:
                owner = len(run_texts) - 1
            output[owner] += new_text[j1:j2]
            continue
        raise AssertionError(f"unexpected SequenceMatcher opcode: {tag}")
    return output


def patch_text_shape(shape_element: Any, *, old_text: str, new_text: str) -> None:
    from ..._errors import PatchPreconditionError, UnsupportedEditError

    old_paragraphs = old_text.split("\n")
    new_paragraphs = new_text.split("\n")
    if len(old_paragraphs) != len(new_paragraphs):
        raise UnsupportedEditError(
            "Phase C v1 cannot add or remove PPTX paragraphs.",
            details={"reason": "paragraph_count_change"},
        )

    paragraph_elements = shape_element.xpath('.//*[local-name()="p"]')
    if len(paragraph_elements) != len(old_paragraphs):
        raise PatchPreconditionError(
            "PPTX native paragraph structure no longer matches the IR.",
            details={
                "reason": "native_paragraph_count_mismatch",
                "expected": len(old_paragraphs),
                "actual": len(paragraph_elements),
            },
        )

    planned: list[tuple[list[Any], list[str]]] = []
    for paragraph_index, paragraph_element in enumerate(paragraph_elements):
        text_nodes = _paragraph_run_text_nodes(paragraph_element)
        run_texts = [node.text or "" for node in text_nodes]
        actual_old = "".join(run_texts)
        if actual_old != old_paragraphs[paragraph_index]:
            raise PatchPreconditionError(
                "PPTX native run text no longer matches the IR.",
                details={
                    "reason": "native_text_mismatch",
                    "paragraph_index": paragraph_index,
                    "expected": old_paragraphs[paragraph_index],
                    "actual": actual_old,
                },
            )
        planned.append(
            (text_nodes, _allocate_new_text(run_texts, new_paragraphs[paragraph_index]))
        )

    xml_space = "{http://www.w3.org/XML/1998/namespace}space"
    for text_nodes, allocated in planned:
        for node, text in zip(text_nodes, allocated):
            node.text = text
            if text[:1].isspace() or text[-1:].isspace():
                node.set(xml_space, "preserve")
