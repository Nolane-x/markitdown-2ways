from __future__ import annotations

from difflib import SequenceMatcher

from ..._errors import PatchPreconditionError, UnsupportedEditError
from ._text_extract import _Carrier, _collect_carriers

_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


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
            details={
                "reason": "native_text_mismatch",
                "expected": old_text,
                "actual": actual_old,
            },
        )
    allocated = _allocate_new_text(carriers, new_text)
    for carrier, text in zip(carriers, allocated):
        carrier.text_node.text = text
        if text[:1].isspace() or text[-1:].isspace():
            carrier.text_node.set(_XML_SPACE, "preserve")
        else:
            carrier.text_node.attrib.pop(_XML_SPACE, None)
