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
class PdfLinkEvidence:
    page_index: int
    annotation_index: int
    annotation_objgen: tuple[int, int]
    action_objgen: tuple[int, int] | None
    owner_kind: str
    mutation_owner_objgen: tuple[int, int]
    uri: str
    rect: tuple[float, float, float, float] | None
    subtype: str
    action_type: str
    locator_digest: str
    writable: bool
    reason_code: str | None = None
    immutable_digest: str = ""


@dataclass(frozen=True)
class PdfTextFieldEvidence:
    field_name: str
    field_objgen: tuple[int, int]
    page_index: int
    annotation_index: int
    value: str
    field_type: str
    field_flags: int
    max_len: int | None
    acroform_objgen: tuple[int, int]
    need_appearances: bool
    locator_digest: str
    immutable_digest: str
    writable: bool
    reason_code: str | None = None


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
    page_objgens: tuple[tuple[int, int] | None, ...] = ()
    annotation_topology: tuple[tuple[tuple[int, int] | None, ...], ...] = ()
    annotation_fingerprints: tuple[tuple[str, ...], ...] = ()
    acroform_objgen: tuple[int, int] | None = None
    acroform_fields_topology: tuple[tuple[int, int] | None, ...] = ()
    form_field_bindings: tuple[tuple[tuple[int, int], int, int], ...] = ()
    form_field_fingerprints: tuple[tuple[tuple[int, int], str], ...] = ()
    need_appearances: bool | None = None


@dataclass(frozen=True)
class ParsedPdfSource:
    snapshot: PdfSourceSnapshot
    fields: tuple[PdfInfoFieldEvidence, ...]
    writable: bool
    diagnostics: tuple[str, ...] = ()
    links: tuple[PdfLinkEvidence, ...] = ()
    form_fields: tuple[PdfTextFieldEvidence, ...] = ()
