from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..text.model import TextRepresentation


HTML_LEXICAL_KINDS = frozenset(
    {"element", "attribute", "text", "comment", "doctype", "rawtext", "rcdata"}
)


class HtmlLexicalError(ValueError):
    """Raised when HTML cannot be given deterministic lexical ownership."""


@dataclass(frozen=True)
class HtmlEncodingDeclaration:
    start: int
    end: int
    raw: str
    raw_digest: str
    encoding: str

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("HTML encoding declaration span is invalid")
        if not self.raw or not self.raw_digest or not self.encoding:
            raise ValueError("HTML encoding declaration evidence is incomplete")


@dataclass(frozen=True)
class HtmlRecoveryEntry:
    kind: str
    name: str | None
    depth: int
    attribute_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in {"tag", "text", "comment", "doctype"}:
            raise ValueError("HTML recovery entry kind is unsupported")
        if self.depth < 0:
            raise ValueError("HTML recovery entry depth is invalid")
        object.__setattr__(self, "attribute_names", tuple(self.attribute_names))


@dataclass(frozen=True)
class HtmlRecoverySignature:
    entries: tuple[HtmlRecoveryEntry, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))


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

    def __post_init__(self) -> None:
        if self.kind not in HTML_LEXICAL_KINDS:
            raise ValueError(f"unsupported HTML lexical kind: {self.kind}")
        if not self.path:
            raise ValueError("HTML lexical path must be non-empty")
        if self.start < 0 or self.end < self.start:
            raise ValueError("HTML lexical span is invalid")
        if not isinstance(self.raw, str):
            raise TypeError("HTML lexical raw source must be a string")
        if not self.raw_digest:
            raise ValueError("HTML lexical raw digest must be non-empty")
        if self.order < 0:
            raise ValueError("HTML lexical order is invalid")
        object.__setattr__(self, "children", tuple(self.children))
        if (self.value_start is None) != (self.value_end is None):
            raise ValueError("HTML lexical value span must be complete")
        if self.value_start is not None:
            assert self.value_end is not None
            if not (self.start <= self.value_start <= self.value_end <= self.end):
                raise ValueError("HTML lexical value span falls outside owner span")
        if self.quote not in {None, "'", '"'}:
            raise ValueError("HTML attribute quote is invalid")
        if self.kind in {"element", "attribute"} and not self.normalized_name:
            raise ValueError("HTML named owner requires normalized name")


@dataclass(frozen=True)
class HtmlLexicalDocument:
    root_path: str | None
    nodes: tuple[HtmlLexicalNode, ...]
    recovery_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        paths = [node.path for node in self.nodes]
        if len(paths) != len(set(paths)):
            raise ValueError("HTML lexical ownership paths must be unique")
        by_path = {node.path: node for node in self.nodes}
        if self.root_path is not None:
            root = by_path.get(self.root_path)
            if root is None or root.kind != "element" or root.parent_path is not None:
                raise ValueError("HTML lexical root ownership is invalid")
        for node in self.nodes:
            if node.parent_path is not None and node.parent_path not in by_path:
                raise ValueError("HTML lexical parent path is unknown")
            if any(child not in by_path for child in node.children):
                raise ValueError("HTML lexical child path is unknown")


@dataclass(frozen=True)
class ParsedHtmlSource:
    text: str
    representation: TextRepresentation
    lexical: HtmlLexicalDocument
    encoding_declarations: tuple[HtmlEncodingDeclaration, ...]
    recovery_signature: HtmlRecoverySignature
    recovery_stable: bool
    recovery_reason: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "encoding_declarations", tuple(self.encoding_declarations)
        )
        if self.recovery_stable and self.recovery_reason is not None:
            raise ValueError("stable HTML recovery cannot carry a failure reason")
        if not self.recovery_stable and not self.recovery_reason:
            raise ValueError("unstable HTML recovery requires a reason")
