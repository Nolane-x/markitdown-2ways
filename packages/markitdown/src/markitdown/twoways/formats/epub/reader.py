from __future__ import annotations

from hashlib import sha256
from typing import Any, BinaryIO

from ...capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    encode_capabilities,
)
from ...ir.document import Canvas, DocumentIR, SourceDescriptor
from ...ir.nodes import Node, TextPayload
from ...ir.provenance import NativeLocator, Provenance
from ...ir.serialization import validate_document
from ...readers.base import DocumentIRReader
from .limits import EpubPackageLimits
from .model import ParsedEpubSource
from .parser import EpubParseError, parse_epub_source


_EPUB_EXTENSIONS = frozenset({".epub"})
_EPUB_MIMETYPES = frozenset({"application/epub+zip"})
_EPUB_COMPAT_MIMETYPES = frozenset({"application/x-epub+zip"})


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("EPUB source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("EPUB source stream returned a non-bytes value")
    return bytes(data)


def _node_id(source_digest: str, label: str) -> str:
    label_digest = sha256(label.encode("utf-8")).hexdigest()[:20]
    return f"epub-{source_digest[:16]}-{label_digest}"


def _read_only(operation: str, reason: str) -> CapabilityDecision:
    return CapabilityDecision(
        operation=operation,
        state=CapabilityState.READ_ONLY,
        reason_code=reason,
    )


def _writable(operation: str) -> CapabilityDecision:
    return CapabilityDecision(
        operation=operation,
        state=CapabilityState.WRITABLE,
        constraints={
            "identity_markdown": False,
            "source_preservation": "epub-xml-member-owner",
            "structural_edits": False,
            "target_only": True,
        },
    )


def _structure_capabilities(reason: str) -> tuple[CapabilityDecision, ...]:
    return (
        _read_only("replace_epub_metadata_text", reason),
        _read_only("replace_epub_xhtml_text", reason),
    )


def _native_locator(
    *,
    part_uri: str,
    object_id: str,
    path: str | None = None,
) -> NativeLocator:
    return NativeLocator(
        backend="epub",
        part_uri=part_uri,
        object_id=object_id,
        path=path,
    )


def _provenance(*, part_uri: str, method: str) -> tuple[Provenance, ...]:
    return (
        Provenance(
            source_format="epub",
            canvas_index=0,
            part_uri=part_uri,
            extraction_method=method,
        ),
    )


def _root_metadata(parsed: ParsedEpubSource) -> dict[str, Any]:
    return {
        "epub.package_path": parsed.package_path,
        "epub.package_version": parsed.package_version,
        "epub.writable_version": parsed.writable_version,
        "epub.read_only_reason": parsed.read_only_reason,
        "epub.rootfiles": tuple((item.path, item.media_type) for item in parsed.rootfiles),
        "epub.unique_identifier_id": parsed.unique_identifier_id,
        "epub.unique_identifier_value": parsed.unique_identifier_value,
        "epub.native_source": True,
        "epub.identity_markdown": False,
        CAPABILITY_METADATA_KEY: encode_capabilities(
            _structure_capabilities("epub.publication.structure_read_only")
        ),
    }


def read_epub_ir(
    source: BinaryIO,
    *,
    filename: str | None = None,
    mimetype: str | None = None,
    limits: EpubPackageLimits | None = None,
) -> DocumentIR:
    source_bytes = _read_source_bytes(source)
    source_digest = sha256(source_bytes).hexdigest()
    parsed = parse_epub_source(source_bytes, limits=limits)

    canvas_id = f"epub-canvas-{source_digest[:24]}"
    root_id = _node_id(source_digest, "publication")
    metadata_group_id = _node_id(source_digest, "metadata")
    manifest_group_id = _node_id(source_digest, "manifest")
    spine_group_id = _node_id(source_digest, "spine")

    manifest_node_ids = {
        item.item_id: _node_id(source_digest, f"manifest:{item.index}:{item.item_id}")
        for item in parsed.manifest
    }
    metadata_node_ids = tuple(
        _node_id(source_digest, f"metadata:{index}:{owner.member_path}:{owner.xml_path}")
        for index, owner in enumerate(parsed.metadata_owners)
    )
    spine_node_ids = tuple(
        _node_id(source_digest, f"spine:{item.index}:{item.idref}")
        for item in parsed.spine
    )
    xhtml_node_ids = {
        (owner.manifest_item_id, owner.xml_path): _node_id(
            source_digest,
            f"xhtml:{owner.manifest_item_id}:{owner.xml_path}",
        )
        for owner in parsed.xhtml_text_owners
    }

    nodes: dict[str, Node] = {}
    root_children = (metadata_group_id, manifest_group_id, spine_group_id)
    nodes[root_id] = Node(
        node_id=root_id,
        kind="group",
        semantic_role="epub-publication",
        children=root_children,
        canvas_id=canvas_id,
        provenance=_provenance(part_uri="/", method="epub-package-graph"),
        native_locator=_native_locator(
            part_uri="/",
            object_id="publication",
            path=parsed.package_path,
        ),
        metadata=_root_metadata(parsed),
    )

    structure_caps = encode_capabilities(
        _structure_capabilities("epub.package.structure_read_only")
    )
    nodes[metadata_group_id] = Node(
        node_id=metadata_group_id,
        kind="group",
        semantic_role="epub-metadata",
        parent_id=root_id,
        children=metadata_node_ids,
        order=0,
        canvas_id=canvas_id,
        provenance=_provenance(
            part_uri=parsed.package_path,
            method="epub-package-metadata",
        ),
        native_locator=_native_locator(
            part_uri=parsed.package_path,
            object_id="metadata",
            path="/package/metadata",
        ),
        metadata={
            "epub.native_source": True,
            "epub.identity_markdown": False,
            CAPABILITY_METADATA_KEY: structure_caps,
        },
    )

    nodes[manifest_group_id] = Node(
        node_id=manifest_group_id,
        kind="group",
        semantic_role="epub-manifest",
        parent_id=root_id,
        children=tuple(manifest_node_ids[item.item_id] for item in parsed.manifest),
        order=1,
        canvas_id=canvas_id,
        provenance=_provenance(
            part_uri=parsed.package_path,
            method="epub-package-manifest",
        ),
        native_locator=_native_locator(
            part_uri=parsed.package_path,
            object_id="manifest",
            path="/package/manifest",
        ),
        metadata={
            "epub.native_source": True,
            "epub.identity_markdown": False,
            CAPABILITY_METADATA_KEY: structure_caps,
        },
    )

    nodes[spine_group_id] = Node(
        node_id=spine_group_id,
        kind="group",
        semantic_role="epub-spine",
        parent_id=root_id,
        children=spine_node_ids,
        order=2,
        canvas_id=canvas_id,
        provenance=_provenance(
            part_uri=parsed.package_path,
            method="epub-package-spine",
        ),
        native_locator=_native_locator(
            part_uri=parsed.package_path,
            object_id="spine",
            path="/package/spine",
        ),
        metadata={
            "epub.native_source": True,
            "epub.identity_markdown": False,
            CAPABILITY_METADATA_KEY: structure_caps,
        },
    )

    for index, owner in enumerate(parsed.metadata_owners):
        node_id = metadata_node_ids[index]
        nodes[node_id] = Node(
            node_id=node_id,
            kind="text",
            semantic_role=f"epub-metadata-{owner.name}",
            parent_id=metadata_group_id,
            order=index,
            canvas_id=canvas_id,
            provenance=_provenance(
                part_uri=owner.member_path,
                method="epub-opf-xml-owner",
            ),
            native_locator=_native_locator(
                part_uri=owner.member_path,
                object_id=owner.name,
                path=owner.xml_path,
            ),
            payload=TextPayload(text=owner.value),
            metadata={
                "epub.owner_kind": "metadata-text",
                "epub.metadata_name": owner.name,
                "epub.member_path": owner.member_path,
                "epub.member_sha256": owner.member_sha256,
                "epub.xml_path": owner.xml_path,
                "epub.raw_digest": owner.raw_digest,
                "epub.native_source": True,
                "epub.identity_markdown": False,
                "text.native_source": True,
                CAPABILITY_METADATA_KEY: encode_capabilities(
                    (_writable("replace_epub_metadata_text"),)
                ),
            },
        )

    xhtml_by_manifest: dict[str, list[str]] = {}
    for owner in parsed.xhtml_text_owners:
        node_id = xhtml_node_ids[(owner.manifest_item_id, owner.xml_path)]
        xhtml_by_manifest.setdefault(owner.manifest_item_id, []).append(node_id)
        nodes[node_id] = Node(
            node_id=node_id,
            kind="text",
            semantic_role="epub-xhtml-text",
            parent_id=manifest_node_ids[owner.manifest_item_id],
            order=len(xhtml_by_manifest[owner.manifest_item_id]) - 1,
            canvas_id=canvas_id,
            provenance=_provenance(
                part_uri=owner.member_path,
                method="epub-xhtml-xml-owner",
            ),
            native_locator=_native_locator(
                part_uri=owner.member_path,
                object_id=owner.manifest_item_id,
                path=owner.xml_path,
            ),
            payload=TextPayload(text=owner.value),
            metadata={
                "epub.owner_kind": "xhtml-text",
                "epub.manifest_item_id": owner.manifest_item_id,
                "epub.member_path": owner.member_path,
                "epub.member_sha256": owner.member_sha256,
                "epub.xml_path": owner.xml_path,
                "epub.raw_digest": owner.raw_digest,
                "epub.native_source": True,
                "epub.identity_markdown": False,
                "text.native_source": True,
                CAPABILITY_METADATA_KEY: encode_capabilities(
                    (_writable("replace_epub_xhtml_text"),)
                ),
            },
        )

    for item in parsed.manifest:
        node_id = manifest_node_ids[item.item_id]
        member_path = item.resolved_path or item.href
        nodes[node_id] = Node(
            node_id=node_id,
            kind="group",
            semantic_role="epub-manifest-resource",
            parent_id=manifest_group_id,
            children=tuple(xhtml_by_manifest.get(item.item_id, ())),
            order=item.index,
            canvas_id=canvas_id,
            provenance=_provenance(
                part_uri=member_path,
                method="epub-manifest-item",
            ),
            native_locator=_native_locator(
                part_uri=member_path,
                object_id=item.item_id,
                path=item.href,
            ),
            metadata={
                "epub.manifest_item_id": item.item_id,
                "epub.href": item.href,
                "epub.media_type": item.media_type,
                "epub.properties": item.properties,
                "epub.resolved_path": item.resolved_path,
                "epub.is_remote": item.is_remote,
                "epub.is_navigation": item.is_navigation,
                "epub.native_source": True,
                "epub.identity_markdown": False,
                CAPABILITY_METADATA_KEY: structure_caps,
            },
        )

    for index, item in enumerate(parsed.spine):
        node_id = spine_node_ids[index]
        nodes[node_id] = Node(
            node_id=node_id,
            kind="unknown_native",
            semantic_role="epub-spine-reference",
            parent_id=spine_group_id,
            order=item.index,
            canvas_id=canvas_id,
            provenance=_provenance(
                part_uri=parsed.package_path,
                method="epub-spine-itemref",
            ),
            native_locator=_native_locator(
                part_uri=parsed.package_path,
                object_id=item.idref,
                path=f"/package/spine/itemref[{item.index}]",
            ),
            metadata={
                "epub.spine_index": item.index,
                "epub.idref": item.idref,
                "epub.linear": item.linear,
                "epub.native_source": True,
                "epub.identity_markdown": False,
                CAPABILITY_METADATA_KEY: structure_caps,
            },
        )

    root_locator = nodes[root_id].native_locator
    document = DocumentIR(
        document_id=f"epub-document-{source_digest[:24]}",
        source=SourceDescriptor(
            format="epub",
            filename=filename,
            mimetype=mimetype,
            sha256=source_digest,
            size_bytes=len(source_bytes),
            preserved_source_ref=f"epub:sha256:{source_digest}",
        ),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="publication",
                name=filename,
                root_node_ids=(root_id,),
                native_locator=root_locator,
            ),
        ),
        nodes=nodes,
        root_node_ids=(root_id,),
    )
    validate_document(document)
    return document


class EpubIRReader(DocumentIRReader):
    def accepts(self, file_stream: BinaryIO, stream_info: Any, **kwargs: Any) -> bool:
        del kwargs
        extension = (getattr(stream_info, "extension", None) or "").lower()
        mimetype = (
            (getattr(stream_info, "mimetype", None) or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        if extension in _EPUB_EXTENSIONS or mimetype in _EPUB_MIMETYPES:
            return True
        if mimetype not in _EPUB_COMPAT_MIMETYPES:
            return False

        try:
            position = file_stream.tell()
        except (AttributeError, OSError):
            position = None
        try:
            source_bytes = _read_source_bytes(file_stream)
            parse_epub_source(source_bytes)
            return True
        except (EpubParseError, TypeError, ValueError):
            return False
        finally:
            if position is not None:
                try:
                    file_stream.seek(position)
                except (AttributeError, OSError):
                    pass

    def read(
        self,
        file_stream: BinaryIO,
        stream_info: Any,
        **kwargs: Any,
    ) -> DocumentIR:
        limits = kwargs.pop("limits", None)
        if kwargs:
            raise TypeError(f"unexpected EPUB reader options: {sorted(kwargs)}")
        return read_epub_ir(
            file_stream,
            filename=getattr(stream_info, "filename", None),
            mimetype=getattr(stream_info, "mimetype", None),
            limits=limits,
        )
