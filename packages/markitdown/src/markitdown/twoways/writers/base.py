from __future__ import annotations

from dataclasses import dataclass
from typing import Any, BinaryIO, Protocol, runtime_checkable

from .._results import WriterResult
from ..ir.document import DocumentIR


@dataclass(frozen=True)
class TargetInfo:
    format: str
    mimetype: str | None = None
    extension: str | None = None

    def __post_init__(self) -> None:
        if not self.format.strip():
            raise ValueError("format must be non-empty")


@runtime_checkable
class DocumentWriter(Protocol):
    def accepts(
        self,
        document: DocumentIR,
        target: TargetInfo,
        **kwargs: Any,
    ) -> bool: ...

    def write(
        self,
        document: DocumentIR,
        output: BinaryIO,
        target: TargetInfo,
        **kwargs: Any,
    ) -> WriterResult: ...
