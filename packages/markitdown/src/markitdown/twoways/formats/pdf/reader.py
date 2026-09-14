from __future__ import annotations

from typing import Any, BinaryIO

from ...capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from ...ir.document import Canvas, Diagnostic, DocumentIR, SourceDescriptor
from ...ir.nodes import Node, TextPayload
from ...ir.provenance import NativeLocator, Provenance
from ...ir.serialization import validate_document
from ...readers.base import DocumentIRReader
from .limits import PdfNativeLimits
from .model import ParsedPdfSource, PdfInfoFieldEvidence, PdfLinkEvidence
from .parser import parse_pdf_source

_PDF_EXTENSIONS = frozenset({".pdf"})
_PDF_MIMETYPES = frozenset({"application/pdf"})


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("PDF source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("PDF source stream returned a non-bytes value")
    return bytes(data)


def _reason(parsed: ParsedPdfSource) -> str:
    if parsed.diagnostics:
        return parsed.diagnostics[0]
    return "pdf.structure.read_only"


def _metadata_capability(
    parsed: ParsedPdfSource,
    field: PdfInfoFieldEvidence,
) -> CapabilityDecision:
    del field
    if not parsed.writable:
        return CapabilityDecision(
            operation="update_pdf_metadata",
            state=CapabilityState.READ_ONLY,
            reason_code=_reason(parsed),
        )
    return CapabilityDecision(
        operation="update_pdf_metadata",
        state=CapabilityState.WRITABLE,
        constraints={
            "identity_markdown": False,
            "source_preservation": "incremental-source-prefix",
            "structural_edits": False,
            "existing_keys_only": True,
            "target_only": True,
        },
    )


def _link_capability(link: PdfLinkEvidence) -> CapabilityDecision:
    if not link.writable:
        return CapabilityDecision(
            operation="update_pdf_link_uri",
            state=CapabilityState.READ_ONLY,
            reason_code=link.reason_code or "pdf.link.read_only",
        )
    return CapabilityDecision(
        operation="update_pdf_link_uri",
        state=CapabilityState.WRITABLE,
        constraints={
            "identity_markdown": False,
            "source_preservation": "incremental-source-prefix",
            "structural_edits": False,
            "existing_action_only": True,
            "target_only": True,
        },
    )


def _root_capability(parsed: ParsedPdfSource) -> CapabilityDecision:
    return CapabilityDecision(
        operation="update_pdf_metadata",
        state=CapabilityState.READ_ONLY,
        reason_code=_reason(parsed),
    )


def read_pdf_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    limits: PdfNativeLimits | None = None,
) -> DocumentIR:
    source_bytes = _read_source_bytes(source)
    parsed = parse_pdf_source(source_bytes, limits=limits)
    snapshot = parsed.snapshot
    digest = snapshot.source_sha256
    document_id = f"pdf-document-{digest[:24]}"
    canvas_id = f"pdf-canvas-{digest[:24]}"
    root_id = f"pdf-root-{digest[:24]}"
    root_object_id = (
        f"{snapshot.root_objgen[0]}:{snapshot.root_objgen[1]}"
        if snapshot.root_objgen is not None
        else "catalog"
    )
    root_locator = NativeLocator(
        backend="pdf",
        part_uri="/Root",
        object_id=root_object_id,
    )

    nodes: dict[str, Node] = {}
    child_ids: list[str] = []
    for order, field in enumerate(parsed.fields, start=1):
        field_id = f"pdf-metadata-{digest[:16]}-{field.field.lower()}"
        child_ids.append(field_id)
        locator = NativeLocator(
            backend="pdf",
            part_uri="/Info",
            object_id=f"{field.info_objgen[0]}:{field.info_objgen[1]}",
            path=field.key,
        )
        capability = _metadata_capability(parsed, field)
        nodes[field_id] = Node(
            node_id=field_id,
            kind="text",
            semantic_role="pdf-metadata",
            parent_id=root_id,
            order=order,
            canvas_id=canvas_id,
            provenance=(
                Provenance(
                    source_format="pdf",
                    canvas_index=0,
                    part_uri="/Info",
                    extraction_method="pypdf-document-info",
                ),
            ),
            native_locator=locator,
            payload=TextPayload(text=field.value),
            metadata={
                "pdf.info_key": field.key,
                "pdf.info_field": field.field,
                "pdf.info_objgen": field.info_objgen,
                "pdf.object_type": field.object_type,
                "pdf.identity_markdown": False,
                CAPABILITY_METADATA_KEY: encode_capabilities((capability,)),
            },
        )

    link_order_base = len(child_ids)
    for offset, link in enumerate(parsed.links, start=1):
        link_id = f"pdf-link-{digest[:16]}-{link.page_index}-{link.annotation_index}"
        child_ids.append(link_id)
        annotation_object_id = f"{link.annotation_objgen[0]}:{link.annotation_objgen[1]}"
        part_uri = f"/Pages/{link.page_index}/Annots"
        locator = NativeLocator(
            backend="pdf",
            part_uri=part_uri,
            object_id=annotation_object_id,
            path="/A/URI",
        )
        capability = _link_capability(link)
        nodes[link_id] = Node(
            node_id=link_id,
            kind="text",
            semantic_role="pdf-link-uri",
            parent_id=root_id,
            order=link_order_base + offset,
            canvas_id=canvas_id,
            provenance=(
                Provenance(
                    source_format="pdf",
                    canvas_index=0,
                    part_uri=part_uri,
                    extraction_method="pypdf-uri-link",
                ),
            ),
            native_locator=locator,
            payload=TextPayload(text=link.uri),
            metadata={
                "pdf.page_index": link.page_index,
                "pdf.annotation_index": link.annotation_index,
                "pdf.annotation_objgen": link.annotation_objgen,
                "pdf.action_objgen": link.action_objgen,
                "pdf.action_owner_kind": link.owner_kind,
                "pdf.mutation_owner_objgen": link.mutation_owner_objgen,
                "pdf.link_locator_digest": link.locator_digest,
                "pdf.link_rect": link.rect,
                "pdf.link_subtype": link.subtype,
                "pdf.link_action_type": link.action_type,
                "pdf.identity_markdown": False,
                CAPABILITY_METADATA_KEY: encode_capabilities((capability,)),
            },
        )

    root = Node(
        node_id=root_id,
        kind="unknown_native",
        semantic_role="pdf-document",
        children=tuple(child_ids),
        order=0,
        canvas_id=canvas_id,
        provenance=(
            Provenance(
                source_format="pdf",
                canvas_index=0,
                part_uri="/Root",
                extraction_method="pypdf-strict",
            ),
        ),
        native_locator=root_locator,
        payload={
            "pdf_header": snapshot.pdf_header,
            "page_count": snapshot.page_count,
        },
        metadata={
            "pdf.root_objgen": snapshot.root_objgen,
            "pdf.info_objgen": snapshot.info_objgen,
            "pdf.has_xmp": snapshot.has_xmp,
            "pdf.encrypted": snapshot.encrypted,
            "pdf.has_signature": snapshot.has_signature,
            "pdf.has_certification": snapshot.has_certification,
            "pdf.linearized": snapshot.linearized,
            "pdf.identity_markdown": False,
            CAPABILITY_METADATA_KEY: encode_capabilities((_root_capability(parsed),)),
        },
    )
    nodes[root_id] = root

    diagnostics = tuple(
        Diagnostic(
            code=reason,
            severity="warning",
            message=f"PDF native metadata writeback is read-only: {reason}",
            node_id=root_id,
            canvas_id=canvas_id,
        )
        for reason in parsed.diagnostics
    )
    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(
            format="pdf",
            filename=filename,
            mimetype=mimetype,
            sha256=digest,
            size_bytes=snapshot.source_size,
            preserved_source_ref=f"pdf:sha256:{digest}",
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="document",
                name=filename,
                root_node_ids=(root_id,),
                native_locator=root_locator,
            ),
        ),
        nodes=nodes,
        root_node_ids=(root_id,),
        diagnostics=diagnostics,
    )
    validate_document(document)
    return document


class PdfIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        del file_stream, kwargs
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (
            (getattr(stream_info, "mimetype", None) or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        return extension in _PDF_EXTENSIONS or mimetype in _PDF_MIMETYPES

    def read(
        self,
        file_stream: BinaryIO,
        stream_info: Any,
        **kwargs: Any,
    ) -> DocumentIR:
        limits = kwargs.pop("limits", None)
        if kwargs:
            raise TypeError(f"unexpected PDF reader options: {sorted(kwargs)}")
        return read_pdf_ir(
            file_stream,
            filename=getattr(stream_info, "filename", None),
            mimetype=getattr(stream_info, "mimetype", None),
            limits=limits,
        )
