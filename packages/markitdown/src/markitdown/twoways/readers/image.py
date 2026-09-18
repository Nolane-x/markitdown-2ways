from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import mimetypes
from types import MappingProxyType
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


_IMAGE_EVIDENCE_KEY = "twoways.image_converter_snapshot.v1"
_IMAGE_CONVERTER_BLOB_SHA = "cd49b96d29f50861625cecfb6cee7bdd1eb30b54"
_DEFAULT_DESCRIPTION_PROMPT = "Write a detailed caption for this image."

_ACCEPTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
_ACCEPTED_MIME_PREFIXES = ("image/jpeg", "image/png")
_METADATA_FIELDS = (
    "ImageSize",
    "Title",
    "Caption",
    "Description",
    "Keywords",
    "Artist",
    "Author",
    "DateTimeOriginal",
    "CreateDate",
    "GPSPosition",
)
_METADATA_FIELD_SET = frozenset(_METADATA_FIELDS)


@dataclass(frozen=True)
class ImageDerivedLimits:
    max_source_bytes: int = 64 * 1024 * 1024
    max_metadata_utf8_bytes: int = 4 * 1024 * 1024
    max_description_utf8_bytes: int = 16 * 1024 * 1024
    max_markdown_utf8_bytes: int = 32 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in (
            "max_source_bytes",
            "max_metadata_utf8_bytes",
            "max_description_utf8_bytes",
            "max_markdown_utf8_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class ImageMetadataSnapshot:
    fields: Mapping[str, str]
    provider: str
    materialization_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.fields, Mapping):
            raise TypeError("fields must be a mapping")

        normalized: dict[str, str] = {}
        for key, value in self.fields.items():
            if not isinstance(key, str):
                raise TypeError("metadata field name must be a string")
            if key not in _METADATA_FIELD_SET:
                raise ValueError(f"unsupported ImageConverter metadata field: {key}")
            if not isinstance(value, str):
                raise TypeError(f"metadata value for {key} must be a string")
            normalized[key] = value

        if not isinstance(self.provider, str):
            raise TypeError("provider must be a string")
        if not self.provider.strip():
            raise ValueError("provider must be non-empty")

        if self.materialization_id is not None:
            if not isinstance(self.materialization_id, str):
                raise TypeError("materialization_id must be a string when provided")
            if not self.materialization_id.strip():
                raise ValueError("materialization_id must be non-empty when provided")

        object.__setattr__(self, "fields", MappingProxyType(normalized))


@dataclass(frozen=True)
class ImageDescriptionSnapshot:
    content: str
    provider: str
    model: str
    content_type: str
    prompt: str | None = None
    materialization_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise TypeError("content must be a string")

        for name in ("provider", "model", "content_type"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string")
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")

        if self.prompt is not None and not isinstance(self.prompt, str):
            raise TypeError("prompt must be a string when provided")

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


def _effective_prompt(prompt: str | None) -> str:
    if prompt is None or prompt.strip() == "":
        return _DEFAULT_DESCRIPTION_PROMPT
    return prompt


def _description_content_type(stream_info: StreamInfo) -> str:
    if stream_info.mimetype:
        return stream_info.mimetype

    content_type, _ = mimetypes.guess_type("_dummy" + (stream_info.extension or ""))
    if not content_type:
        return "application/octet-stream"
    return content_type


def _ordered_metadata_items(
    metadata: ImageMetadataSnapshot | None,
) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    return tuple(
        (field, metadata.fields[field])
        for field in _METADATA_FIELDS
        if field in metadata.fields
    )


def _metadata_bytes(items: tuple[tuple[str, str], ...]) -> bytes:
    parts: list[str] = []
    for key, value in items:
        parts.extend((key, value))
    return "\0".join(parts).encode("utf-8")


def _capture_source(source_stream: BinaryIO, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= max_bytes:
        remaining = max_bytes + 1 - total
        if remaining <= 0:
            break

        chunk = source_stream.read(min(64 * 1024, remaining))
        if isinstance(chunk, str):
            raise TypeError("ImageConverter source stream must return bytes")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("ImageConverter source stream returned a non-bytes value")

        data = bytes(chunk)
        if not data:
            break

        chunks.append(data)
        total += len(data)
        if total > max_bytes:
            raise ValueError("ImageConverter source exceeds max_source_bytes")

    return b"".join(chunks)


def _derived_capability() -> tuple[dict[str, object], ...]:
    return encode_capabilities(
        (
            CapabilityDecision(
                operation="replace_text",
                state=CapabilityState.DERIVED,
                reason_code="image.output.not_native_writable",
                constraints={
                    "identity_markdown": False,
                    "native_owner": False,
                    "remote_writeback": False,
                    "materialization": "explicit-local-only",
                },
            ),
        )
    )


def read_image_snapshot_ir(
    source_stream: BinaryIO,
    *,
    stream_info: StreamInfo,
    metadata: ImageMetadataSnapshot | None = None,
    description: ImageDescriptionSnapshot | None = None,
    limits: ImageDerivedLimits | None = None,
) -> DocumentIR:
    if metadata is not None and not isinstance(metadata, ImageMetadataSnapshot):
        raise TypeError("metadata must be an ImageMetadataSnapshot when provided")
    if description is not None and not isinstance(
        description, ImageDescriptionSnapshot
    ):
        raise TypeError("description must be an ImageDescriptionSnapshot when provided")

    accepted_by = _accepted_by(stream_info)
    if accepted_by is None:
        raise ValueError(
            "source is not owned by the existing ImageConverter acceptance surface"
        )

    active_limits = limits or ImageDerivedLimits()
    source_bytes = _capture_source(
        source_stream,
        max_bytes=active_limits.max_source_bytes,
    )

    metadata_items = _ordered_metadata_items(metadata)
    metadata_bytes = _metadata_bytes(metadata_items)
    if len(metadata_bytes) > active_limits.max_metadata_utf8_bytes:
        raise ValueError("metadata snapshot exceeds max_metadata_utf8_bytes")

    description_bytes = b""
    description_output = ""
    description_output_bytes = b""
    description_content_type: str | None = None
    effective_prompt: str | None = None
    if description is not None:
        description_bytes = description.content.encode("utf-8")
        if len(description_bytes) > active_limits.max_description_utf8_bytes:
            raise ValueError("description snapshot exceeds max_description_utf8_bytes")

        description_content_type = _description_content_type(stream_info)
        if description.content_type != description_content_type:
            raise ValueError(
                "description content_type does not match ImageConverter semantics"
            )

        effective_prompt = _effective_prompt(description.prompt)
        description_output = description.content.strip()
        description_output_bytes = description_output.encode("utf-8")

    markdown = "".join(f"{key}: {value}\n" for key, value in metadata_items)
    if description is not None:
        markdown += "\n# Description:\n" + description_output + "\n"

    markdown_bytes = markdown.encode("utf-8")
    if len(markdown_bytes) > active_limits.max_markdown_utf8_bytes:
        raise ValueError("derived Markdown exceeds max_markdown_utf8_bytes")

    source_digest = sha256(source_bytes).hexdigest()
    metadata_digest = sha256(metadata_bytes).hexdigest()
    description_digest = sha256(description_bytes).hexdigest()
    description_output_digest = sha256(description_output_bytes).hexdigest()
    markdown_digest = sha256(markdown_bytes).hexdigest()
    uri = stream_info.url

    identity_seed = "\0".join(
        (
            "image-converter-multi-input-derived",
            source_digest,
            stream_info.filename or "",
            stream_info.mimetype or "",
            stream_info.extension or "",
            uri or "",
            accepted_by,
            "metadata-present" if metadata is not None else "metadata-absent",
            metadata.provider if metadata is not None else "",
            metadata.materialization_id
            if metadata is not None and metadata.materialization_id
            else "",
            metadata_digest,
            "description-present" if description is not None else "description-absent",
            description.provider if description is not None else "",
            description.model if description is not None else "",
            effective_prompt or "",
            description_content_type or "",
            description.materialization_id
            if description is not None and description.materialization_id
            else "",
            description_digest,
            description_output_digest,
            markdown_digest,
            "ImageConverter",
        )
    )
    ids = DocumentIdFactory(seed=identity_seed)
    document_id = ids.new("document")
    canvas_id = ids.new("canvas")
    node_id = ids.new("root")

    evidence: dict[str, object] = {
        "kind": "image-converter-derived",
        "source_sha256": source_digest,
        "source_size_bytes": len(source_bytes),
        "accepted_by": accepted_by,
        "metadata_present": metadata is not None,
        "metadata_field_count": len(metadata_items),
        "metadata_sha256": metadata_digest,
        "metadata_utf8_size_bytes": len(metadata_bytes),
        "description_present": description is not None,
        "markdown_sha256": markdown_digest,
        "markdown_utf8_size_bytes": len(markdown_bytes),
        "converter": "ImageConverter",
        "converter_blob_sha": _IMAGE_CONVERTER_BLOB_SHA,
        "exiftool_executed_by_twoways": False,
        "llm_called_by_twoways": False,
        "network_performed_by_twoways": False,
        "subprocess_performed_by_twoways": False,
    }
    if metadata is not None:
        evidence["metadata_provider"] = metadata.provider
        evidence["metadata_fields"] = [key for key, _ in metadata_items]
        if metadata.materialization_id is not None:
            evidence["metadata_materialization_id"] = metadata.materialization_id
    if description is not None:
        evidence.update(
            {
                "description_provider": description.provider,
                "description_model": description.model,
                "description_effective_prompt": effective_prompt,
                "description_content_type": description_content_type,
                "description_raw_sha256": description_digest,
                "description_raw_utf8_size_bytes": len(description_bytes),
                "description_output_sha256": description_output_digest,
                "description_output_utf8_size_bytes": len(description_output_bytes),
            }
        )
        if description.materialization_id is not None:
            evidence["description_materialization_id"] = description.materialization_id
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
        semantic_role="derived_image",
        order=0,
        canvas_id=canvas_id,
        provenance=(
            Provenance(
                source_format="image-converter-derived",
                canvas_index=0,
                extraction_method="ImageConverter-caller-materializations",
                metadata={
                    "source_sha256": source_digest,
                    "metadata_sha256": metadata_digest,
                    "description_sha256": description_digest,
                    "markdown_sha256": markdown_digest,
                    "accepted_by": accepted_by,
                    "native_owner": False,
                },
            ),
        ),
        native_locator=None,
        payload=TextPayload(text=markdown),
        metadata={
            CAPABILITY_METADATA_KEY: _derived_capability(),
            "twoways.image_converter_snapshot.markdown_sha256": markdown_digest,
        },
    )

    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(
            format="image-converter-derived-source",
            filename=stream_info.filename,
            mimetype=stream_info.mimetype,
            uri=uri,
            sha256=source_digest,
            size_bytes=len(source_bytes),
        ),
        metadata=DocumentMetadata(custom={_IMAGE_EVIDENCE_KEY: evidence}),
        canvases=(
            Canvas(
                canvas_id=canvas_id,
                index=0,
                kind="derived-image",
                name=stream_info.filename or "ImageConverter derived output",
                root_node_ids=(node_id,),
                native_locator=None,
            ),
        ),
        nodes={node_id: node},
        root_node_ids=(node_id,),
        diagnostics=(
            Diagnostic(
                code="image.output.not_native_writable",
                severity="info",
                message=(
                    "ImageConverter metadata/caption text is caller-materialized "
                    "derived evidence and has no H25 native write authority. "
                    "H12-H14 remain the PNG/JPEG native mutation authorities."
                ),
                node_id=node_id,
                canvas_id=canvas_id,
                details={
                    "accepted_by": accepted_by,
                    "metadata_present": metadata is not None,
                    "description_present": description is not None,
                    "native_owner": False,
                },
            ),
        ),
    )
    validate_document(document)
    return document


__all__ = [
    "ImageDescriptionSnapshot",
    "ImageDerivedLimits",
    "ImageMetadataSnapshot",
    "read_image_snapshot_ir",
]
