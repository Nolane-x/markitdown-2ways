from __future__ import annotations

from bs4 import BeautifulSoup, Comment, Doctype, NavigableString, Tag

from .model import HtmlRecoveryEntry, HtmlRecoverySignature


def _normalized_attribute_names(tag: Tag) -> tuple[str, ...]:
    return tuple(sorted(str(name).lower() for name in tag.attrs))


def build_recovery_signature(text: str) -> HtmlRecoverySignature:
    if not isinstance(text, str):
        raise TypeError("HTML recovery source must be a string")

    soup = BeautifulSoup(text, "html.parser")
    entries: list[HtmlRecoveryEntry] = []

    def visit(node: object, depth: int) -> None:
        if isinstance(node, Doctype):
            entries.append(HtmlRecoveryEntry("doctype", None, depth))
            return
        if isinstance(node, Comment):
            entries.append(HtmlRecoveryEntry("comment", None, depth))
            return
        if isinstance(node, NavigableString):
            entries.append(HtmlRecoveryEntry("text", None, depth))
            return
        if not isinstance(node, Tag):
            return

        entries.append(
            HtmlRecoveryEntry(
                "tag",
                node.name.lower(),
                depth,
                _normalized_attribute_names(node),
            )
        )
        for child in node.children:
            visit(child, depth + 1)

    for child in soup.children:
        visit(child, 0)
    return HtmlRecoverySignature(tuple(entries))
