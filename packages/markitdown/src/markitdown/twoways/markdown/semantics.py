from __future__ import annotations

from ..ir.semantics import (
    native_locator_digest,
    node_semantic_digest,
    node_semantic_text,
    stable_digest,
)


def normalize_markdown_block(text: str) -> str:
    lines = [
        line.rstrip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    output: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if not blank:
                output.append("")
            blank = True
        else:
            output.append(line)
            blank = False
    return "\n".join(output)


semantic_text_for_node = node_semantic_text
source_semantic_digest = node_semantic_digest

__all__ = [
    "native_locator_digest",
    "normalize_markdown_block",
    "semantic_text_for_node",
    "source_semantic_digest",
    "stable_digest",
]
