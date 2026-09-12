from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..text.model import TextRepresentation

HTML_LEXICAL_KINDS = frozenset({"element", "attribute", "text", "comment", "doctype", "rawtext", "rcdata"})

class HtmlLexicalError(ValueError):
    """Raised when HTML cannot be given deterministic lexical ownership."""

@dataclass(frozen=True)
class HtmlEncodingDeclaration:
    start: int
    end: int
    raw: str
    raw_digest: str
    encoding: str

@dataclass(frozen=True)
class HtmlRecoveryEntry:
    kind: str
    name: str | None
    depth: int
    attribute_names: tuple[str, ...] = ()

@dataclass(frozen=True)
class HtmlRecoverySignature:
    entries: tuple[HtmlRecoveryEntry, ...]

@dataclass(frozen=True)
class HtmlLexicalNode:
    path: str
    kind: str
    start: int
    end: int
    raw: str
    raw_digest: str
    order: int
    parent_path: str | None = None
    children: tuple[str, ...] = ()
    qname: str | None = None
    normalized_name: str | None = None
    value: Any = None
    value_start: int | None = None
    value_end: int | None = None
    quote: str | None = None
    start_tag_start: int | None = None
    start_tag_end: int | None = None
    end_tag_start: int | None = None
    end_tag_end: int | None = None
    recovery_reason: str | None = None

@dataclass(frozen=True)
class HtmlLexicalDocument:
    root_path: str | None
    nodes: tuple[HtmlLexicalNode, ...]
    recovery_reason: str | None = None

@dataclass(frozen=True)
class ParsedHtmlSource:
    text: str
    representation: TextRepresentation
    lexical: HtmlLexicalDocument
    encoding_declarations: tuple[HtmlEncodingDeclaration, ...]
    recovery_signature: HtmlRecoverySignature
    recovery_stable: bool
    recovery_reason: str | None
