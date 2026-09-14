from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class PdfParseError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        reason: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.details = dict(details or {})


@dataclass(frozen=True)
class PdfInfoFieldEvidence:
    field: str
    key: str
    value: str
    info_objgen: tuple[int, int]
    object_type: str


@dataclass(frozen=True)
class PdfSourceSnapshot:
    source_sha256: str
    source_size: int
    pdf_header: str
    page_count: int
    root_objgen: tuple[int, int] | None
    info_objgen: tuple[int, int] | None
    supported_metadata: Mapping[str, str]
    has_xmp: bool
    encrypted: bool
    has_signature: bool
    has_certification: bool
    linearized: bool


@dataclass(frozen=True)
class ParsedPdfSource:
    snapshot: PdfSourceSnapshot
    fields: tuple[PdfInfoFieldEvidence, ...]
    writable: bool
    diagnostics: tuple[str, ...] = ()
