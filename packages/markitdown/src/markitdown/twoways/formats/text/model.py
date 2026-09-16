from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_BOMS = frozenset(
    {"none", "utf-8", "utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"}
)
SUPPORTED_NEWLINES = frozenset({"none", "lf", "crlf", "cr", "mixed"})


@dataclass(frozen=True)
class TextRepresentation:
    encoding: str
    bom: str = "none"
    newline: str = "none"
    byte_roundtrip: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.encoding, str) or not self.encoding.strip():
            raise ValueError("text encoding must be a non-empty string")
        if self.bom not in SUPPORTED_BOMS:
            raise ValueError("text BOM is unsupported")
        if self.newline not in SUPPORTED_NEWLINES:
            raise ValueError("text newline convention is unsupported")
        if not isinstance(self.byte_roundtrip, bool):
            raise ValueError("text byte_roundtrip must be a boolean")
