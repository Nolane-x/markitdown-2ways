from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


JSON_KINDS = frozenset({"object", "array", "string", "number", "boolean", "null"})


@dataclass(frozen=True)
class JsonLexicalNode:
    pointer: str
    kind: str
    start: int
    end: int
    raw: str
    raw_digest: str
    parent_pointer: str | None = None
    children: tuple[str, ...] = ()
    value: Any = None
    number_value: Decimal | None = None

    def __post_init__(self) -> None:
        if self.kind not in JSON_KINDS:
            raise ValueError(f"unsupported JSON lexical kind: {self.kind}")
        if self.start < 0 or self.end < self.start:
            raise ValueError("JSON lexical span is invalid")
        if not isinstance(self.raw, str):
            raise TypeError("JSON lexical raw source must be a string")
        if not self.raw_digest:
            raise ValueError("JSON lexical raw digest must be non-empty")
        object.__setattr__(self, "children", tuple(self.children))
        if self.kind == "number":
            if self.number_value is None:
                raise ValueError("JSON number node requires number_value")
        elif self.number_value is not None:
            raise ValueError("only JSON number nodes may carry number_value")


@dataclass(frozen=True)
class JsonLexicalDocument:
    root_pointer: str
    nodes: tuple[JsonLexicalNode, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        if not self.nodes:
            raise ValueError("JSON lexical document requires a root value")
        if self.root_pointer != "":
            raise ValueError("JSON root pointer must be the empty RFC 6901 pointer")
        if self.nodes[0].pointer != self.root_pointer:
            raise ValueError("first JSON lexical node must be the root value")
        pointers = [node.pointer for node in self.nodes]
        if len(pointers) != len(set(pointers)):
            raise ValueError("JSON lexical pointers must be unique")
