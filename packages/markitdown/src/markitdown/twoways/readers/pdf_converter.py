from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
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


_PDF_EVIDENCE_KEY = "twoways.pdf_converter_snapshot.v1"
_PDF_CONVERTER_BLOB_SHA = "ffbcbd990cfc40a577404c453ebe47bf477c4929"
_ACCEPTED_EXTENSIONS = frozenset({".pdf"})
_ACCEPTED_MIME_PREFIXES = ("application/pdf", "application/x-pdf")
_PARTIAL_NUMBERING_PATTERN = re.compile(r"^\.\d+$")


@dataclass(frozen=True)
class PdfDerivedLimits:
    max_source_bytes: int = 64 * 1024 * 1024
    max_extracted_utf8_bytes: int = 32 * 1024 * 1024
    max_markdown_utf8_bytes: int = 32 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in (
            "max_source_bytes",
            "max_extracted_utf8_bytes",
            "max_markdown_utf8_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class PdfConverterExtractionSnapshot:
    extracted_text: str
    provider: str = "caller-materialized"
    extraction_path: str = "caller-extraction"
    materialization_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.extracted_text, str):
            raise TypeError("extracted_text must be a string")

        for name in ("provider", "extraction_path"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string")
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")

        if self.materialization_id is not None:
            if not isinstance(self.materialization_id, str):
                raise TypeError("materialization_id must be a string when provided")
            if not self.materialization_id.strip():
                raise ValueError("materialization_id must be non-empty when provided")


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
            raise TypeError("PdfConverter source stream must return bytes")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("PdfConverter source stream returned a non-bytes value")
        data = bytes(chunk)
        if not data:
            break
        chunks.append(data)
        total += len(data)
        if total > max_bytes:
            raise ValueError("PdfConverter source exceeds max_source_bytes")
    return b"".join(chunks)


def _merge_partial_numbering_lines(text: str) -> str:
    lines = text.split("\n")
    result_lines: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if _PARTIAL_NUMBERING_PATTERN.match(stripped):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines):
                next_line = lines[j].strip()
                result_lines.append(f"{stripped} {next_line}")
                i = j + 1
            else:
                result_lines.append(line)
                i += 1
        else:
            result_lines.append(line)
            i += 1

    return "\n".join(result_lines)


def _derived_capability() -> tuple[dict[str, object], ...]:
    return encode_capabilities(
        (
            CapabilityDecision(
                operation="replace_text",
                state=CapabilityState.DERIVED,
                reason_code="pdf.output.not_native_writable",
                constraints={
                    "identity_markdown": False,
                    "native_owner": False,
                    "remote_writeback": False,
                    "materialization": "explicit-local-only",
                },
            ),
        )
    )


def read_pdf_converter_snapshot_ir(
    source_stream: BinaryIO,
    *,
    stream_info: StreamInfo,
    snapshot: PdfConverterExtractionSnapshot,
    limits: PdfDerivedLimits | None = None,
) -> DocumentIR:
    if not isinstance(snapshot, PdfConverterExtractionSnapshot):
        raise TypeError("snapshot must be a PdfConverterExtractionSnapshot")

    accepted_by = _accepted_by(stream_info)
    if accepted_by is None:
        raise ValueError(
            "source is not owned by the explicit PdfConverter extension/MIME "
            "acceptance surface"
        )

    active_limits = limits or PdfDerivedLimits()
    source_bytes = _capture_source(
        source_stream,
        max_bytes=active_limits.max_source_bytes,
    )

    extracted_bytes = snapshot.extracted_text.encode("utf-8")
    if len(extracted_bytes) > active_limits.max_extracted_utf8_bytes:
        raise ValueError("extracted text exceeds max_extracted_utf8_bytes")

    markdown = _merge_partial_numbering_lines(snapshot.extracted_text)
    markdown_bytes = markdown.encode("utf-8")
    if len(markdown_bytes) > active_limits.max_markdown_utf8_bytes:
        raise ValueError("derived Markdown exceeds max_markdown_utf8_bytes")

    source_digest = sha256(source_bytes).hexdigest()
    extracted_digest = sha256(extracted_bytes).hexdigest()
    markdown_digest = sha256(markdown_bytes).hexdigest()
    uri = stream_info.url

    identity_seed = "\0".join(
        (
            "pdf-converter-derived-extraction",
            source_digest,
            stream_info.filename or "",
            stream_info.mimetype or "",
            stream_info.extension or "",
            uri or "",
            accepted_by,
            extracted_digest,
            snapshot.provider,
            snapshot.extraction_path,
            snapshot.materialization_id or "",
            markdown_digest,
            "PdfConverter",
        )
    )
    ids = DocumentIdFactory(seed=identity_seed)
    document_id = ids.new("document")
    canvas_id = ids.new("canvas")
    node_id = ids.new("root")

    evidence: dict[str, object] = {
        "kind": "pdf-converter-derived",
        "source_sha256": source_digest,
        "source_size_bytes": len(source_bytes),
        "accepted_by": accepted_by,
        "provider": snapshot.provider,
        "extraction_path": snapshot.extraction_path,
        "extracted_text_sha256": extracted_digest,
        "extracted_text_utf8_size_bytes": len(extracted_bytes),
        "markdown_sha256": markdown_digest,
        "markdown_utf8_size_bytes": len(markdown_bytes),
        "converter": "PdfConverter",
        "converter_blob_sha": _PDF_CONVERTER_BLOB_SHA,
        "pdf_parsing_performed_by_twoways": False,
        "pdfminer_executed_by_twoways": False,
        "pdfplumber_executed_by_twoways": False,
        "network_performed_by_twoways": False,
        "subprocess_performed_by_twoways": False,
        "extraction_path_verified_by_twoways": False,
    }
    if snapshot.materialization_id is not None:
        evidence["materialization_id"] = snapshot.materialization_id
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
        semantic_role="derived_document",
        order=0,
        canvas_id=canvas_id,
        provenance=(
            Provenance(
                source_format="pdf-converter-derived",
                canvas_index=0,
                extraction_method="PdfConverter-caller-materialization",
                metadata={
                    "source_sha256": source_digest,
                    "extracted_text_sha256": extracted_digest,
                    "markdown_sha256": markdown_digest,
                    "provider": snapshot.provider,
                    "extraction_path": snapshot.extraction_path,
                    "native_owner": False,
                },
            ),
        ),
        native_locator=None,
        payload=TextPayload(text=markdown),
        metadata={
            CAPABILITY_METADATA_KEY: _derived_capability(),
            "twoways.pdf_converter_snapshot.markdown_sha256": markdown_digest,
        },
    )

    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(
            format="pdf-converter-derived-source",
            filename=stream_info.filename,
            mimetype=stream_info.mimetype,
            uri=uri,
            sha256=source_digest,
            size_bytes=len(source_bytes),
        ),
        metadata=DocumentMetadata(custom={_PDF_EVIDENCE_KEY: evidence}),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="derived-pdf-extraction",
                name=stream_info.filename or "PdfConverter derived extraction",
                root_node_ids=(node_id,),
                native_locator=None,
            ),
        ),
        nodes={node_id: node},
        root_node_ids=(node_id,),
        diagnostics=(
            Diagnostic(
                code="pdf.output.not_native_writable",
                severity="info",
                message=(
                    "Materialized PdfConverter extraction text is derived and has no "
                    "H27 native write authority. H9-H11 retain PDF native mutation "
                    "authority."
                ),
                node_id=node_id,
                canvas_id=canvas_id,
                details={
                    "accepted_by": accepted_by,
                    "provider": snapshot.provider,
                    "extraction_path": snapshot.extraction_path,
                    "native_owner": False,
                },
            ),
        ),
    )
    validate_document(document)
    return document


__all__ = [
    "PdfConverterExtractionSnapshot",
    "PdfDerivedLimits",
    "read_pdf_converter_snapshot_ir",
]
