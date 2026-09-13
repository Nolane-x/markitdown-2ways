from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
import json
from typing import Any, BinaryIO
from zipfile import BadZipFile, ZipFile

from ...ir.document import Canvas, Diagnostic, DocumentIR, SourceDescriptor
from ...ir.nodes import (
    ChartPayload,
    ImagePayload,
    Node,
    TablePayload,
    UnknownNativePayload,
)
from ...ir.resources import NativePayload, Relationship, Resource
from ...ir.serialization import validate_document
from ...readers.base import DocumentIRReader
from .limits import ZipRecursiveLimits
from .model import ParsedZipSource, ZipParsedMember, ZipParseError
from .parser import parse_zip_source


_ZIP_EXTENSIONS = frozenset({".zip"})
_ZIP_MIMETYPES = frozenset({"application/zip", "application/x-zip-compressed"})


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("ZIP source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("ZIP source stream returned a non-bytes value")
    return bytes(data)


def _namespace_id(
    kind: str,
    chain: tuple[str, ...],
    adapter_key: str,
    inner_id: str,
) -> str:
    material = json.dumps(
        ["zip", list(chain), adapter_key, inner_id],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"zip-{kind}-{sha256(material).hexdigest()[:24]}"


def _routing_metadata(
    *,
    chain: tuple[str, ...],
    adapter_key: str,
    inner_document: DocumentIR,
    inner_node_id: str | None = None,
    inner_canvas_id: str | None = None,
) -> dict[str, Any]:
    source = inner_document.source
    metadata: dict[str, Any] = {
        "zip.member_chain": chain,
        "zip.adapter_key": adapter_key,
        "zip.inner_document_id": inner_document.document_id,
        "zip.identity_markdown": False,
    }
    if source is not None:
        metadata["zip.inner_source_sha256"] = source.sha256
        metadata["zip.inner_source_size"] = source.size_bytes
    if inner_node_id is not None:
        metadata["zip.inner_node_id"] = inner_node_id
    if inner_canvas_id is not None:
        metadata["zip.inner_canvas_id"] = inner_canvas_id
    return metadata


def _read_inner_document(
    adapter_key: str,
    payload: bytes,
    filename: str,
) -> DocumentIR | None:
    if adapter_key == "json":
        from ..json import read_json_ir

        return read_json_ir(BytesIO(payload), filename=filename)
    if adapter_key == "xlsx":
        from ..xlsx.reader import read_xlsx_ir

        return read_xlsx_ir(BytesIO(payload))
    if adapter_key == "epub":
        from ..epub import read_epub_ir

        return read_epub_ir(BytesIO(payload), filename=filename)
    if adapter_key == "docx":
        from ..docx.reader import read_docx_ir

        return read_docx_ir(BytesIO(payload))
    if adapter_key == "pptx":
        from ..pptx.reader import read_pptx_ir

        return read_pptx_ir(BytesIO(payload))
    return None


def _rewrite_payload(
    payload: object,
    *,
    node_ids: dict[str, str],
    resource_ids: dict[str, str],
    native_payload_ids: dict[str, str],
) -> object:
    if isinstance(payload, ImagePayload):
        return replace(payload, resource_id=resource_ids[payload.resource_id])
    if isinstance(payload, TablePayload):
        return replace(
            payload,
            cells=tuple(
                replace(
                    cell,
                    node_ids=tuple(node_ids[node_id] for node_id in cell.node_ids),
                )
                for cell in payload.cells
            ),
        )
    if isinstance(payload, ChartPayload) and payload.native_payload_ref is not None:
        return replace(
            payload,
            native_payload_ref=native_payload_ids[payload.native_payload_ref],
        )
    if isinstance(payload, UnknownNativePayload):
        return replace(
            payload,
            native_payload_ref=native_payload_ids[payload.native_payload_ref],
        )
    return payload


def _import_inner_document(
    inner: DocumentIR,
    *,
    chain: tuple[str, ...],
    adapter_key: str,
    member_node_id: str,
    canvases: list[Canvas],
    nodes: dict[str, Node],
    resources: dict[str, Resource],
    native_payloads: dict[str, NativePayload],
    relationships: list[Relationship],
    diagnostics: list[Diagnostic],
) -> tuple[str, ...]:
    canvas_ids = {
        canvas.canvas_id: _namespace_id(
            "canvas",
            chain,
            adapter_key,
            canvas.canvas_id,
        )
        for canvas in inner.canvases
    }
    node_ids = {
        node_id: _namespace_id("node", chain, adapter_key, node_id)
        for node_id in inner.nodes
    }
    resource_ids = {
        resource_id: _namespace_id("resource", chain, adapter_key, resource_id)
        for resource_id in inner.resources
    }
    native_payload_ids = {
        payload_id: _namespace_id("payload", chain, adapter_key, payload_id)
        for payload_id in inner.native_payloads
    }

    canvas_index_map: dict[int, int] = {}
    for inner_canvas in inner.canvases:
        new_index = len(canvases)
        canvas_index_map[inner_canvas.index] = new_index
        metadata = dict(inner_canvas.metadata)
        metadata.update(
            _routing_metadata(
                chain=chain,
                adapter_key=adapter_key,
                inner_document=inner,
                inner_canvas_id=inner_canvas.canvas_id,
            )
        )
        canvases.append(
            replace(
                inner_canvas,
                canvas_id=canvas_ids[inner_canvas.canvas_id],
                index=new_index,
                root_node_ids=tuple(
                    node_ids[node_id] for node_id in inner_canvas.root_node_ids
                ),
                metadata=metadata,
            )
        )

    top_level_ids: list[str] = []
    for inner_node_id, inner_node in inner.nodes.items():
        if inner_node.parent_id is None:
            top_level_ids.append(node_ids[inner_node_id])
        metadata = dict(inner_node.metadata)
        metadata.update(
            _routing_metadata(
                chain=chain,
                adapter_key=adapter_key,
                inner_document=inner,
                inner_node_id=inner_node_id,
            )
        )
        provenance = tuple(
            replace(
                item,
                canvas_index=(
                    canvas_index_map[item.canvas_index]
                    if item.canvas_index is not None
                    else None
                ),
            )
            for item in inner_node.provenance
        )
        nodes[node_ids[inner_node_id]] = replace(
            inner_node,
            node_id=node_ids[inner_node_id],
            parent_id=(
                node_ids[inner_node.parent_id]
                if inner_node.parent_id is not None
                else member_node_id
            ),
            children=tuple(node_ids[node_id] for node_id in inner_node.children),
            canvas_id=(
                canvas_ids[inner_node.canvas_id]
                if inner_node.canvas_id is not None
                else None
            ),
            provenance=provenance,
            payload=_rewrite_payload(
                inner_node.payload,
                node_ids=node_ids,
                resource_ids=resource_ids,
                native_payload_ids=native_payload_ids,
            ),
            metadata=metadata,
        )

    for resource_id, resource in inner.resources.items():
        metadata = dict(resource.metadata)
        metadata.update(
            _routing_metadata(
                chain=chain,
                adapter_key=adapter_key,
                inner_document=inner,
            )
        )
        resources[resource_ids[resource_id]] = replace(
            resource,
            resource_id=resource_ids[resource_id],
            metadata=metadata,
        )

    for payload_id, native_payload in inner.native_payloads.items():
        metadata = dict(native_payload.metadata)
        metadata.update(
            _routing_metadata(
                chain=chain,
                adapter_key=adapter_key,
                inner_document=inner,
            )
        )
        native_payloads[native_payload_ids[payload_id]] = replace(
            native_payload,
            payload_id=native_payload_ids[payload_id],
            metadata=metadata,
        )

    known_ids: dict[str, str] = {
        inner.document_id: member_node_id,
        **canvas_ids,
        **node_ids,
        **resource_ids,
        **native_payload_ids,
    }
    for relationship in inner.relationships:
        metadata = dict(relationship.metadata)
        metadata.update(
            _routing_metadata(
                chain=chain,
                adapter_key=adapter_key,
                inner_document=inner,
            )
        )
        relationships.append(
            replace(
                relationship,
                relationship_id=_namespace_id(
                    "relationship",
                    chain,
                    adapter_key,
                    relationship.relationship_id,
                ),
                source_id=known_ids[relationship.source_id],
                target_id=(
                    known_ids[relationship.target_id]
                    if relationship.target_id is not None
                    else None
                ),
                metadata=metadata,
            )
        )

    for diagnostic in inner.diagnostics:
        details = dict(diagnostic.details)
        details.update(
            {
                "zip.member_chain": chain,
                "zip.adapter_key": adapter_key,
            }
        )
        diagnostics.append(
            replace(
                diagnostic,
                node_id=(
                    node_ids[diagnostic.node_id]
                    if diagnostic.node_id is not None
                    else None
                ),
                canvas_id=(
                    canvas_ids[diagnostic.canvas_id]
                    if diagnostic.canvas_id is not None
                    else None
                ),
                details=details,
            )
        )

    return tuple(top_level_ids)


def _member_metadata(member: ZipParsedMember) -> dict[str, Any]:
    return {
        "zip.member_chain": member.chain,
        "zip.member_name": member.entry.name,
        "zip.member_sha256": member.entry.uncompressed_sha256,
        "zip.member_size": member.entry.uncompressed_size,
        "zip.compression_method": member.entry.compression_method,
        "zip.adapter_key": member.classification.adapter_key,
        "zip.classification_state": member.classification.state,
        "zip.classification_probes": member.classification.probes,
        "zip.reason_code": member.classification.reason_code,
        "zip.identity_markdown": False,
    }


def _import_archive(
    parsed: ParsedZipSource,
    source: bytes,
    *,
    parent_node_id: str | None,
    archive_canvas_id: str,
    canvases: list[Canvas],
    nodes: dict[str, Node],
    resources: dict[str, Resource],
    native_payloads: dict[str, NativePayload],
    relationships: list[Relationship],
    diagnostics: list[Diagnostic],
) -> str:
    prefix = parsed.members[0].chain[:-1] if parsed.members else ()
    archive_node_id = _namespace_id("node", prefix, "zip", "archive")
    child_ids: list[str] = []

    try:
        archive = ZipFile(BytesIO(source), "r")
    except (BadZipFile, ValueError) as exc:
        raise ZipParseError(
            "Unable to reopen ZIP source while building DocumentIR.",
            reason="zip.reader.source_reopen_failed",
        ) from exc

    with archive:
        for member in parsed.members:
            member_node_id = _namespace_id(
                "node",
                member.chain,
                "zip",
                "member",
            )
            child_ids.append(member_node_id)
            member_children: list[str] = []
            payload: bytes | None = None
            if not member.entry.is_directory:
                try:
                    payload = archive.read(member.entry.name)
                except (BadZipFile, RuntimeError, ValueError) as exc:
                    raise ZipParseError(
                        "Unable to read ZIP member while building DocumentIR.",
                        reason="zip.reader.member_read_failed",
                        details={"member_chain": member.chain},
                    ) from exc

            if payload is not None and member.nested_archive is not None:
                member_children.append(
                    _import_archive(
                        member.nested_archive,
                        payload,
                        parent_node_id=member_node_id,
                        archive_canvas_id=archive_canvas_id,
                        canvases=canvases,
                        nodes=nodes,
                        resources=resources,
                        native_payloads=native_payloads,
                        relationships=relationships,
                        diagnostics=diagnostics,
                    )
                )
            elif (
                payload is not None
                and member.classification.state == "typed"
                and member.classification.adapter_key not in {None, "zip"}
            ):
                adapter_key = member.classification.adapter_key
                try:
                    inner = _read_inner_document(
                        adapter_key,
                        payload,
                        member.entry.name,
                    )
                except Exception as exc:
                    diagnostics.append(
                        Diagnostic(
                            code="zip.member.inner_read_failed",
                            severity="warning",
                            message="Typed ZIP member failed inner DocumentIR materialization.",
                            details={
                                "member_chain": member.chain,
                                "adapter_key": adapter_key,
                                "error_type": type(exc).__name__,
                            },
                        )
                    )
                else:
                    if inner is not None:
                        member_children.extend(
                            _import_inner_document(
                                inner,
                                chain=member.chain,
                                adapter_key=adapter_key,
                                member_node_id=member_node_id,
                                canvases=canvases,
                                nodes=nodes,
                                resources=resources,
                                native_payloads=native_payloads,
                                relationships=relationships,
                                diagnostics=diagnostics,
                            )
                        )

            nodes[member_node_id] = Node(
                node_id=member_node_id,
                kind="group",
                semantic_role="zip-member",
                parent_id=archive_node_id,
                children=tuple(member_children),
                order=len(child_ids) - 1,
                canvas_id=archive_canvas_id,
                metadata=_member_metadata(member),
            )

    nodes[archive_node_id] = Node(
        node_id=archive_node_id,
        kind="group",
        semantic_role="zip-archive",
        parent_id=parent_node_id,
        children=tuple(child_ids),
        canvas_id=archive_canvas_id,
        metadata={
            "zip.member_chain": prefix,
            "zip.depth": parsed.depth,
            "zip.source_sha256": parsed.snapshot.source_sha256,
            "zip.source_size": parsed.snapshot.source_size,
            "zip.identity_markdown": False,
        },
    )
    return archive_node_id


def read_zip_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    limits: ZipRecursiveLimits | None = None,
) -> DocumentIR:
    source_bytes = _read_source_bytes(source)
    parsed = parse_zip_source(source_bytes, filename=filename, limits=limits)
    digest = parsed.snapshot.source_sha256
    archive_canvas_id = _namespace_id("canvas", (), "zip", "archive")
    canvases: list[Canvas] = [
        Canvas(
            canvas_id=archive_canvas_id,
            index=0,
            kind="archive",
            name=filename,
            metadata={
                "zip.member_chain": (),
                "zip.adapter_key": "zip",
                "zip.identity_markdown": False,
            },
        )
    ]
    nodes: dict[str, Node] = {}
    resources: dict[str, Resource] = {}
    native_payloads: dict[str, NativePayload] = {}
    relationships: list[Relationship] = []
    diagnostics = list(parsed.diagnostics)

    root_node_id = _import_archive(
        parsed,
        source_bytes,
        parent_node_id=None,
        archive_canvas_id=archive_canvas_id,
        canvases=canvases,
        nodes=nodes,
        resources=resources,
        native_payloads=native_payloads,
        relationships=relationships,
        diagnostics=diagnostics,
    )
    canvases[0] = replace(canvases[0], root_node_ids=(root_node_id,))

    document = DocumentIR(
        document_id=f"zip-document-{digest[:24]}",
        source=SourceDescriptor(
            format="zip",
            filename=filename,
            mimetype=mimetype,
            sha256=digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"zip:sha256:{digest}",
        ),
        canvases=tuple(canvases),
        nodes=nodes,
        root_node_ids=(root_node_id,),
        resources=resources,
        relationships=tuple(relationships),
        native_payloads=native_payloads,
        diagnostics=tuple(diagnostics),
    )
    validate_document(document)
    return document


class ZipIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        del file_stream, kwargs
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (
            (getattr(stream_info, "mimetype", None) or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        return extension in _ZIP_EXTENSIONS or mimetype in _ZIP_MIMETYPES

    def read(
        self,
        file_stream: BinaryIO,
        stream_info: Any,
        **kwargs: Any,
    ) -> DocumentIR:
        limits = kwargs.pop("limits", None)
        if kwargs:
            raise TypeError(f"unexpected ZIP reader options: {sorted(kwargs)}")
        return read_zip_ir(
            file_stream,
            filename=getattr(stream_info, "filename", None),
            mimetype=getattr(stream_info, "mimetype", None),
            limits=limits,
        )
