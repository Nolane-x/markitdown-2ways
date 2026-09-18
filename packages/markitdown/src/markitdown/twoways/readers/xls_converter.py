from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import BinaryIO

from ..._stream_info import StreamInfo
from ..capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from ..ir.document import (
    Canvas,
    Diagnostic,
    DocumentIdFactory,
    DocumentIR,
    DocumentMetadata,
    SourceDescriptor,
)
from ..ir.nodes import Node, TextPayload
from ..ir.provenance import Provenance
from ..ir.serialization import validate_document


_XLS_EVIDENCE_KEY = "twoways.xls_converter_snapshot.v1"
_XLS_CONVERTER_BLOB_SHA = "355dd8f8d74ab5c9a40bba37e1f7a7d601eeba27"
_ACCEPTED_EXTENSIONS = frozenset({".xls"})
_ACCEPTED_MIME_PREFIXES = ("application/vnd.ms-excel", "application/excel")


@dataclass(frozen=True)
class XlsDerivedLimits:
    max_source_bytes: int = 64 * 1024 * 1024
    max_sheet_count: int = 1024
    max_materialized_utf8_bytes: int = 64 * 1024 * 1024
    max_markdown_utf8_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in (
            "max_source_bytes",
            "max_sheet_count",
            "max_materialized_utf8_bytes",
            "max_markdown_utf8_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class XlsSheetMarkdownSnapshot:
    name: str
    markdown: str
    materialization_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not self.name.strip():
            raise ValueError("name must be non-empty")
        if not isinstance(self.markdown, str):
            raise TypeError("markdown must be a string")

        if self.materialization_id is not None:
            if not isinstance(self.materialization_id, str):
                raise TypeError("materialization_id must be a string when provided")
            if not self.materialization_id.strip():
                raise ValueError("materialization_id must be non-empty when provided")


@dataclass(frozen=True)
class XlsConverterSnapshot:
    sheets: tuple[XlsSheetMarkdownSnapshot, ...]
    provider: str
    materialization_id: str | None = None
    table_provider: str | None = None
    html_markdown_provider: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.sheets, tuple):
            raise TypeError("sheets must be a tuple")
        if not self.sheets:
            raise ValueError("sheets must be non-empty")

        normalized_names: set[str] = set()
        for sheet in self.sheets:
            if not isinstance(sheet, XlsSheetMarkdownSnapshot):
                raise TypeError("sheets must contain XlsSheetMarkdownSnapshot values")
            normalized = sheet.name.casefold()
            if normalized in normalized_names:
                raise ValueError("sheet names must be unique")
            normalized_names.add(normalized)

        if not isinstance(self.provider, str):
            raise TypeError("provider must be a string")
        if not self.provider.strip():
            raise ValueError("provider must be non-empty")

        for name in (
            "materialization_id",
            "table_provider",
            "html_markdown_provider",
        ):
            value = getattr(self, name)
            if value is None:
                continue
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string when provided")
            if not value.strip():
                raise ValueError(f"{name} must be non-empty when provided")


def _accepted_by(stream_info: StreamInfo) -> str | None:
    extension = (stream_info.extension or "").lower()
    mimetype = (stream_info.mimetype or "").lower()

    if extension in _ACCEPTED_EXTENSIONS:
        return "extension"
    if any(mimetype.startswith(prefix) for prefix in _ACCEPTED_MIME_PREFIXES):
        return "mimetype"
    return None


def _capture_source(source_stream: BinaryIO, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= max_bytes:
        remaining = max_bytes + 1 - total
        if remaining <= 0:
            break

        chunk = source_stream.read(min(64 * 1024, remaining))
        if isinstance(chunk, str):
            raise TypeError("XlsConverter source stream must return bytes")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("XlsConverter source stream returned a non-bytes value")

        data = bytes(chunk)
        if not data:
            break

        chunks.append(data)
        total += len(data)
        if total > max_bytes:
            raise ValueError("XlsConverter source exceeds max_source_bytes")

    return b"".join(chunks)


def _project_markdown(snapshot: XlsConverterSnapshot) -> str:
    markdown = ""
    for sheet in snapshot.sheets:
        markdown += f"## {sheet.name}\n"
        markdown += sheet.markdown.strip() + "\n\n"
    return markdown.strip()


def _derived_capability() -> tuple[dict[str, object], ...]:
    return encode_capabilities(
        (
            CapabilityDecision(
                operation="replace_text",
                state=CapabilityState.DERIVED,
                reason_code="xls.output.not_native_writable",
                constraints={
                    "identity_markdown": False,
                    "native_owner": False,
                    "remote_writeback": False,
                    "materialization": "explicit-local-only",
                },
            ),
        )
    )


def read_xls_converter_snapshot_ir(
    source_stream: BinaryIO,
    *,
    stream_info: StreamInfo,
    snapshot: XlsConverterSnapshot,
    limits: XlsDerivedLimits | None = None,
) -> DocumentIR:
    if not isinstance(snapshot, XlsConverterSnapshot):
        raise TypeError("snapshot must be an XlsConverterSnapshot")

    accepted_by = _accepted_by(stream_info)
    if accepted_by is None:
        raise ValueError(
            "source is not owned by the explicit XlsConverter extension/MIME "
            "acceptance surface"
        )

    active_limits = limits or XlsDerivedLimits()
    source_bytes = _capture_source(
        source_stream,
        max_bytes=active_limits.max_source_bytes,
    )

    if len(snapshot.sheets) > active_limits.max_sheet_count:
        raise ValueError("materialized sheets exceed max_sheet_count")

    raw_materialized_size = sum(
        len(sheet.markdown.encode("utf-8")) for sheet in snapshot.sheets
    )
    if raw_materialized_size > active_limits.max_materialized_utf8_bytes:
        raise ValueError(
            "materialized sheet Markdown exceeds max_materialized_utf8_bytes"
        )

    markdown = _project_markdown(snapshot)
    markdown_bytes = markdown.encode("utf-8")
    if len(markdown_bytes) > active_limits.max_markdown_utf8_bytes:
        raise ValueError("derived Markdown exceeds max_markdown_utf8_bytes")

    source_digest = sha256(source_bytes).hexdigest()
    markdown_digest = sha256(markdown_bytes).hexdigest()
    uri = stream_info.url

    sheet_identity: list[str] = []
    sheet_evidence: list[dict[str, object]] = []
    for index, sheet in enumerate(snapshot.sheets):
        raw_bytes = sheet.markdown.encode("utf-8")
        stripped_bytes = sheet.markdown.strip().encode("utf-8")
        raw_digest = sha256(raw_bytes).hexdigest()
        stripped_digest = sha256(stripped_bytes).hexdigest()

        sheet_identity.extend(
            (
                str(index),
                sheet.name,
                raw_digest,
                stripped_digest,
                sheet.materialization_id or "",
            )
        )
        item: dict[str, object] = {
            "index": index,
            "name": sheet.name,
            "raw_markdown_sha256": raw_digest,
            "raw_markdown_utf8_size_bytes": len(raw_bytes),
            "stripped_markdown_sha256": stripped_digest,
            "stripped_markdown_utf8_size_bytes": len(stripped_bytes),
        }
        if sheet.materialization_id is not None:
            item["materialization_id"] = sheet.materialization_id
        sheet_evidence.append(item)

    identity_seed = "\0".join(
        (
            "xls-converter-derived-sheet-snapshot",
            source_digest,
            stream_info.filename or "",
            stream_info.mimetype or "",
            stream_info.extension or "",
            uri or "",
            accepted_by,
            snapshot.provider,
            snapshot.materialization_id or "",
            snapshot.table_provider or "",
            snapshot.html_markdown_provider or "",
            *sheet_identity,
            markdown_digest,
            "XlsConverter",
        )
    )
    ids = DocumentIdFactory(seed=identity_seed)
    document_id = ids.new("document")
    canvas_id = ids.new("canvas")
    node_id = ids.new("root")

    evidence: dict[str, object] = {
        "kind": "xls-converter-derived",
        "source_sha256": source_digest,
        "source_size_bytes": len(source_bytes),
        "accepted_by": accepted_by,
        "provider": snapshot.provider,
        "sheet_count": len(snapshot.sheets),
        "sheet_names": [sheet.name for sheet in snapshot.sheets],
        "sheets": sheet_evidence,
        "materialized_markdown_utf8_size_bytes": raw_materialized_size,
        "markdown_sha256": markdown_digest,
        "markdown_utf8_size_bytes": len(markdown_bytes),
        "converter": "XlsConverter",
        "converter_blob_sha": _XLS_CONVERTER_BLOB_SHA,
        "cfb_biff_parsing_performed_by_twoways": False,
        "pandas_executed_by_twoways": False,
        "xlrd_executed_by_twoways": False,
        "html_conversion_executed_by_twoways": False,
        "network_performed_by_twoways": False,
        "subprocess_performed_by_twoways": False,
    }
    if snapshot.materialization_id is not None:
        evidence["materialization_id"] = snapshot.materialization_id
    if snapshot.table_provider is not None:
        evidence["table_provider"] = snapshot.table_provider
    if snapshot.html_markdown_provider is not None:
        evidence["html_markdown_provider"] = snapshot.html_markdown_provider
    if stream_info.filename is not None:
        evidence["filename"] = stream_info.filename
    if stream_info.mimetype is not None:
        evidence["mimetype"] = stream_info.mimetype
    if stream_info.extension is not None:
        evidence["extension"] = stream_info.extension
    if uri is not None:
        evidence["uri"] = uri

    node = Node(
        node_id=node_id,
        kind="text",
        semantic_role="derived_workbook",
        order=0,
        canvas_id=canvas_id,
        provenance=(
            Provenance(
                source_format="xls-converter-derived",
                canvas_index=0,
                extraction_method="XlsConverter-caller-materialization",
                metadata={
                    "source_sha256": source_digest,
                    "sheet_count": len(snapshot.sheets),
                    "markdown_sha256": markdown_digest,
                    "provider": snapshot.provider,
                    "native_owner": False,
                },
            ),
        ),
        native_locator=None,
        payload=TextPayload(text=markdown),
        metadata={
            CAPABILITY_METADATA_KEY: _derived_capability(),
            "twoways.xls_converter_snapshot.markdown_sha256": markdown_digest,
        },
    )

    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(
            format="xls-converter-derived-source",
            filename=stream_info.filename,
            mimetype=stream_info.mimetype,
            uri=uri,
            sha256=source_digest,
            size_bytes=len(source_bytes),
        ),
        metadata=DocumentMetadata(custom={_XLS_EVIDENCE_KEY: evidence}),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="derived-xls-workbook",
                name=stream_info.filename or "XlsConverter derived output",
                root_node_ids=(node_id,),
                native_locator=None,
            ),
        ),
        nodes={node_id: node},
        root_node_ids=(node_id,),
        diagnostics=(
            Diagnostic(
                code="xls.output.not_native_writable",
                severity="info",
                message=(
                    "Materialized XlsConverter workbook Markdown is derived and has "
                    "no H28 native write authority. H17 remains the native BIFF8 "
                    "NUMBER-slot authority."
                ),
                node_id=node_id,
                canvas_id=canvas_id,
                details={
                    "accepted_by": accepted_by,
                    "provider": snapshot.provider,
                    "sheet_count": len(snapshot.sheets),
                    "native_owner": False,
                },
            ),
        ),
    )
    validate_document(document)
    return document


__all__ = [
    "XlsConverterSnapshot",
    "XlsDerivedLimits",
    "XlsSheetMarkdownSnapshot",
    "read_xls_converter_snapshot_ir",
]
