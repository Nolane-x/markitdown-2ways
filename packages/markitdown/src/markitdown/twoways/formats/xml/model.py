from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..text.model import TextRepresentation


XML_LEXICAL_KINDS = frozenset(
    {
        "element",
        "attribute",
        "namespace",
        "text",
        "cdata",
        "comment",
        "processing_instruction",
    }
)


class XmlLexicalError(ValueError):
    """Raised when XML cannot be given safe, unambiguous lexical ownership."""


@dataclass(frozen=True)
class XmlDeclaration:
    start: int
    end: int
    raw: str
    raw_digest: str
    version: str
    encoding: str | None = None
    standalone: str | None = None

    def __post_init__(self) -> None:
        if self.start != 0 or self.end <= self.start:
            raise ValueError("XML declaration span is invalid")
        if not self.raw or self.version != "1.0":
            raise ValueError("XML declaration must be XML 1.0")
        if self.standalone not in {None, "yes", "no"}:
            raise ValueError("XML standalone value is invalid")


@dataclass(frozen=True)
class XmlLexicalNode:
    path: str
    kind: str
    start: int
    end: int
    raw: str
    raw_digest: str
    parent_path: str | None = None
    children: tuple[str, ...] = ()
    qname: str | None = None
    expanded_name: str | None = None
    value: Any = None
    value_start: int | None = None
    value_end: int | None = None
    quote: str | None = None
    namespace_prefix: str | None = None
    namespace_uri: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in XML_LEXICAL_KINDS:
            raise ValueError(f"unsupported XML lexical kind: {self.kind}")
        if not self.path:
            raise ValueError("XML lexical path must be non-empty")
        if self.start < 0 or self.end < self.start:
            raise ValueError("XML lexical span is invalid")
        if not isinstance(self.raw, str):
            raise TypeError("XML lexical raw source must be a string")
        if not self.raw_digest:
            raise ValueError("XML lexical raw digest must be non-empty")
        object.__setattr__(self, "children", tuple(self.children))
        if (self.value_start is None) != (self.value_end is None):
            raise ValueError("XML lexical value span must be complete")
        if self.value_start is not None:
            assert self.value_end is not None
            if not (self.start <= self.value_start <= self.value_end <= self.end):
                raise ValueError("XML lexical value span falls outside owner span")
        if self.quote not in {None, "'", '"'}:
            raise ValueError("XML attribute quote is invalid")


@dataclass(frozen=True)
class XmlLexicalDocument:
    root_path: str
    nodes: tuple[XmlLexicalNode, ...]
    declaration: XmlDeclaration | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        if not self.nodes:
            raise ValueError("XML lexical document requires native owners")
        paths = [node.path for node in self.nodes]
        if len(paths) != len(set(paths)):
            raise ValueError("XML lexical ownership paths must be unique")
        by_path = {node.path: node for node in self.nodes}
        root = by_path.get(self.root_path)
        if root is None or root.kind != "element" or root.parent_path is not None:
            raise ValueError("XML lexical root ownership is invalid")
        for node in self.nodes:
            if node.parent_path is not None and node.parent_path not in by_path:
                raise ValueError("XML lexical parent path is unknown")
            if any(child not in by_path for child in node.children):
                raise ValueError("XML lexical child path is unknown")


@dataclass(frozen=True)
class ParsedXmlSource:
    text: str
    representation: TextRepresentation
    lexical: XmlLexicalDocument

    @property
    def declaration(self) -> XmlDeclaration | None:
        return self.lexical.declaration
