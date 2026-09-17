from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import struct
from typing import Any, BinaryIO
import zlib

from ..._errors import (
    PatchPreconditionError,
    SourcePackageMismatchError,
    UnsupportedEditError,
)
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus, WriterResult
from ...capabilities import CapabilityState, capabilities_for_node
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.nodes import Node, TextPayload
from ...ir.semantics import validate_edit_preconditions
from ...ir.serialization import validate_document
from ...writers.base import DocumentWriter, TargetInfo
from .limits import PngLimits
from .model import ParsedPng, PngTextOwner
from .parser import PngFormatError, parse_png
from .verification import verify_png_candidate

_PNG_READ_LIMITS_KEY = "png.read_limits.v1"
_LIMIT_FIELD_NAMES = (
    "max_source_bytes",
    "max_chunks",
    "max_chunk_data_bytes",
    "max_text_value_bytes",
)
_SUPPORTED_TEXT_CHUNK_TYPES = frozenset({"tEXt", "zTXt", "iTXt"})
_XMP_ITXT_KEYWORD = "XML:com.adobe.xmp"


@dataclass(frozen=True)
class _PreparedEdit:
    node: Node
    chunk_index: int
    owner: PngTextOwner
    old_value: str
    value: str
    replacement_chunk: bytes


def _read_source_bytes(source: BinaryIO) -> bytes:
    data = source.read()
    if isinstance(data, str):
        raise TypeError("PNG source stream must return bytes")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("PNG source stream returned a non-bytes value")
    return bytes(data)


def _validate_source_authority(document: DocumentIR, source_bytes: bytes) -> None:
    source = document.source
    actual_digest = sha256(source_bytes).hexdigest()
    if source is None or source.format != "png" or not source.sha256:
        raise SourcePackageMismatchError(
            "DocumentIR does not contain authoritative PNG source metadata.",
            details={"reason": "missing_source_authority", "actual": actual_digest},
        )
    if source.sha256 != actual_digest:
        raise SourcePackageMismatchError(
            "Provided PNG source does not match the DocumentIR source authority.",
            details={
                "reason": "source_digest_mismatch",
                "expected": source.sha256,
                "actual": actual_digest,
            },
        )
    if source.size_bytes is not None and source.size_bytes != len(source_bytes):
        raise SourcePackageMismatchError(
            "Provided PNG source size does not match the DocumentIR source authority.",
            details={
                "reason": "source_size_mismatch",
                "expected": source.size_bytes,
                "actual": len(source_bytes),
            },
        )


def _read_time_limits(document: DocumentIR) -> PngLimits:
    raw = document.metadata.custom.get(_PNG_READ_LIMITS_KEY)
    if not isinstance(raw, Mapping) or set(raw) != set(_LIMIT_FIELD_NAMES):
        raise PatchPreconditionError(
            "PNG DocumentIR is missing authoritative read-time limits.",
            details={"reason": "png_read_limits_missing_or_invalid"},
        )
    try:
        values = {name: raw[name] for name in _LIMIT_FIELD_NAMES}
        return PngLimits(**values)
    except (KeyError, TypeError, ValueError) as exc:
        raise PatchPreconditionError(
            "PNG DocumentIR contains invalid authoritative read-time limits.",
            details={"reason": "png_read_limits_missing_or_invalid"},
        ) from exc


def _intersect_limits(requested: PngLimits, read_time: PngLimits) -> PngLimits:
    return PngLimits(
        max_source_bytes=min(requested.max_source_bytes, read_time.max_source_bytes),
        max_chunks=min(requested.max_chunks, read_time.max_chunks),
        max_chunk_data_bytes=min(
            requested.max_chunk_data_bytes, read_time.max_chunk_data_bytes
        ),
        max_text_value_bytes=min(
            requested.max_text_value_bytes, read_time.max_text_value_bytes
        ),
    )


def _fresh_parse(source_bytes: bytes, limits: PngLimits) -> ParsedPng:
    try:
        return parse_png(source_bytes, limits=limits)
    except PngFormatError as exc:
        raise PatchPreconditionError(
            "Authoritative PNG source no longer satisfies the H13 structural contract.",
            details={"reason": "png_source_parse_failure", "error": str(exc)},
        ) from exc


def _validate_owner_metadata(node: Node, owner: PngTextOwner) -> None:
    expected = {
        "png.chunk_type": owner.chunk_type,
        "png.compression_method": owner.compression_method,
        "png.compression_flag": owner.compression_flag,
        "png.language_tag": owner.language_tag,
        "png.translated_keyword": owner.translated_keyword,
        "png.language_tag_sha256": owner.language_tag_sha256,
        "png.translated_keyword_sha256": owner.translated_keyword_sha256,
    }
    for key, value in expected.items():
        actual = node.metadata.get(key)
        if actual != value:
            raise PatchPreconditionError(
                "PNG metadata immutable native evidence no longer matches the source.",
                details={
                    "reason": "png_owner_metadata_mismatch",
                    "metadata_key": key,
                    "expected": value,
                    "actual": actual,
                    "target_node_id": node.node_id,
                },
            )


def _validate_native_binding(
    node: Node,
    fresh: ParsedPng,
) -> tuple[int, PngTextOwner]:
    locator = node.native_locator
    chunk_index = node.metadata.get("png.chunk_index")
    keyword = node.metadata.get("png.keyword")
    chunk_type = node.metadata.get("png.chunk_type")
    if (
        not isinstance(chunk_index, int)
        or isinstance(chunk_index, bool)
        or not isinstance(keyword, str)
        or chunk_type not in _SUPPORTED_TEXT_CHUNK_TYPES
        or locator is None
        or locator.backend != "png"
        or locator.part_uri != "/"
        or locator.object_id != f"chunk:{chunk_index}:{keyword}"
        or locator.name != keyword
        or locator.attributes.get("chunk_index") != chunk_index
        or locator.attributes.get("chunk_type") != chunk_type
        or locator.attributes.get("keyword") != keyword
    ):
        raise PatchPreconditionError(
            "PNG metadata target is not bound to its authoritative native chunk.",
            details={
                "reason": "missing_or_unauthorized_png_locator",
                "target_node_id": node.node_id,
            },
        )
    if chunk_index < 0 or chunk_index >= len(fresh.chunks):
        raise PatchPreconditionError(
            "PNG metadata native chunk no longer exists.",
            details={"reason": "png_chunk_missing", "chunk_index": chunk_index},
        )
    chunk = fresh.chunk(chunk_index)
    owner = fresh.text_owner(chunk_index)
    if (
        chunk.chunk_type != chunk_type
        or owner is None
        or owner.chunk_type != chunk_type
    ):
        raise PatchPreconditionError(
            "PNG metadata native owner type no longer matches the authoritative source.",
            details={
                "reason": "png_owner_type_mismatch",
                "chunk_index": chunk_index,
                "expected": chunk_type,
                "actual": chunk.chunk_type,
            },
        )
    if owner.keyword != keyword:
        raise PatchPreconditionError(
            "PNG metadata keyword no longer matches the authoritative owner.",
            details={
                "reason": "png_keyword_mismatch",
                "expected": keyword,
                "actual": owner.keyword,
            },
        )
    if node.metadata.get("png.raw_sha256") != owner.raw_sha256:
        raise PatchPreconditionError(
            "PNG metadata raw owner evidence no longer matches the source.",
            details={
                "reason": "png_raw_owner_digest_mismatch",
                "chunk_index": chunk_index,
            },
        )
    if node.metadata.get("png.data_sha256") != owner.data_sha256:
        raise PatchPreconditionError(
            "PNG metadata data evidence no longer matches the source.",
            details={
                "reason": "png_data_owner_digest_mismatch",
                "chunk_index": chunk_index,
            },
        )
    _validate_owner_metadata(node, owner)
    if not isinstance(node.payload, TextPayload) or node.payload.text != owner.value:
        raise PatchPreconditionError(
            "PNG metadata semantic owner no longer matches the source.",
            details={
                "reason": "png_owner_semantic_mismatch",
                "chunk_index": chunk_index,
            },
        )
    return chunk_index, owner


def _encode_png_chunk(chunk_type: str, data: bytes) -> bytes:
    chunk_type_raw = chunk_type.encode("ascii")
    crc = zlib.crc32(chunk_type_raw)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type_raw + data + struct.pack(">I", crc)


def _encode_replacement_chunk(
    owner: PngTextOwner,
    value: str,
    *,
    limits: PngLimits,
) -> bytes:
    if "\x00" in value:
        raise UnsupportedEditError(
            "PNG text replacement cannot contain NUL.",
            details={"reason": "png_text_nul_unsupported"},
        )

    if owner.chunk_type in {"tEXt", "zTXt"}:
        try:
            encoded_value = value.encode("latin-1")
        except UnicodeEncodeError as exc:
            raise UnsupportedEditError(
                "PNG tEXt/zTXt replacement must be representable in ISO-8859-1.",
                details={"reason": "png_text_value_not_latin1"},
            ) from exc
    elif owner.chunk_type == "iTXt":
        encoded_value = value.encode("utf-8")
    else:
        raise UnsupportedEditError(
            "PNG text owner type is not writable in H13.",
            details={
                "reason": "png.text.unsupported_chunk_type",
                "chunk_type": owner.chunk_type,
            },
        )

    if len(encoded_value) > limits.max_text_value_bytes:
        raise UnsupportedEditError(
            "PNG text replacement exceeds the effective read-time/writer value limit.",
            details={"reason": "png_text_value_limit"},
        )

    keyword_raw = owner.keyword.encode("latin-1")
    if owner.chunk_type == "tEXt":
        data = keyword_raw + b"\x00" + encoded_value
    elif owner.chunk_type == "zTXt":
        if owner.compression_method != 0:
            raise UnsupportedEditError(
                "PNG zTXt compression method is not writable in H13.",
                details={"reason": "png.ztxt.unsupported_compression_method"},
            )
        data = (
            keyword_raw
            + b"\x00"
            + bytes((owner.compression_method,))
            + zlib.compress(encoded_value)
        )
    else:
        if owner.compression_flag not in (0, 1):
            raise UnsupportedEditError(
                "PNG iTXt compression flag is not writable in H13.",
                details={"reason": "png.itxt.invalid_compression_flag"},
            )
        if owner.compression_method != 0:
            raise UnsupportedEditError(
                "PNG iTXt compression method is not writable in H13.",
                details={"reason": "png.itxt.unsupported_compression_method"},
            )
        language_raw = (owner.language_tag or "").encode("ascii")
        translated_raw = (owner.translated_keyword or "").encode("utf-8")
        text_raw = (
            zlib.compress(encoded_value)
            if owner.compression_flag == 1
            else encoded_value
        )
        data = (
            keyword_raw
            + b"\x00"
            + bytes((owner.compression_flag, owner.compression_method))
            + language_raw
            + b"\x00"
            + translated_raw
            + b"\x00"
            + text_raw
        )

    if len(data) > limits.max_chunk_data_bytes:
        raise UnsupportedEditError(
            "PNG text replacement exceeds the effective read-time/writer chunk limit.",
            details={"reason": "png_chunk_data_limit"},
        )
    return _encode_png_chunk(owner.chunk_type, data)


def _prepare_edits(
    document: DocumentIR,
    fresh: ParsedPng,
    edits: tuple[EditOperation, ...],
    limits: PngLimits,
) -> tuple[_PreparedEdit, ...]:
    prepared: list[_PreparedEdit] = []
    seen_chunks: set[int] = set()
    keyword_counts = Counter(owner.keyword for owner in fresh.text_owners)

    for edit in edits:
        if edit.type != "update_png_text_metadata":
            raise UnsupportedEditError(
                "PNG H13 supports only update_png_text_metadata.",
                details={"reason": "unsupported_edit_type", "edit_type": edit.type},
            )
        if edit.target_node_id is None or edit.target_node_id not in document.nodes:
            raise PatchPreconditionError(
                "PNG metadata edit target node does not exist in the source IR.",
                details={
                    "reason": "missing_target",
                    "target_node_id": edit.target_node_id,
                },
            )
        node = document.nodes[edit.target_node_id]
        if node.semantic_role != "png-text-metadata" or not isinstance(
            node.payload, TextPayload
        ):
            raise UnsupportedEditError(
                "update_png_text_metadata requires a PNG native text metadata node.",
                details={"reason": "wrong_node_kind", "target_node_id": node.node_id},
            )

        chunk_index, owner = _validate_native_binding(node, fresh)
        if fresh.is_apng:
            raise UnsupportedEditError(
                "PNG APNG sources are read-only in H13.",
                details={"reason": "png.apng.read_only"},
            )
        if owner.chunk_type == "iTXt" and owner.keyword == _XMP_ITXT_KEYWORD:
            raise UnsupportedEditError(
                "PNG XMP iTXt owners are read-only in H13.",
                details={"reason": "png.itxt.xmp_read_only"},
            )
        if keyword_counts[owner.keyword] != 1:
            raise UnsupportedEditError(
                "PNG duplicate keyword owners are read-only in H13.",
                details={
                    "reason": "png.text.duplicate_keyword",
                    "keyword": owner.keyword,
                },
            )
        if chunk_index in seen_chunks:
            raise UnsupportedEditError(
                "PNG patch contains duplicate edits for one native chunk.",
                details={"reason": "duplicate_png_target", "chunk_index": chunk_index},
            )
        seen_chunks.add(chunk_index)

        decision = capabilities_for_node(node).for_operation("update_png_text_metadata")
        if decision.state is not CapabilityState.WRITABLE:
            raise UnsupportedEditError(
                "PNG metadata capability is read-only for this owner.",
                details={
                    "reason": decision.reason_code or "capability.read_only",
                    "target_node_id": node.node_id,
                },
            )
        validate_edit_preconditions(document, node, edit, format_label="PNG")

        if set(edit.payload) != {"keyword", "old_value", "value"}:
            raise UnsupportedEditError(
                "PNG metadata payload must contain keyword, old_value and value only.",
                details={"reason": "invalid_png_text_payload"},
            )
        keyword = edit.payload.get("keyword")
        old_value = edit.payload.get("old_value")
        value = edit.payload.get("value")
        if not all(isinstance(item, str) for item in (keyword, old_value, value)):
            raise UnsupportedEditError(
                "PNG metadata payload fields must all be strings.",
                details={"reason": "invalid_png_text_payload"},
            )
        assert isinstance(keyword, str)
        assert isinstance(old_value, str)
        assert isinstance(value, str)
        if keyword != owner.keyword or keyword != node.metadata.get("png.keyword"):
            raise PatchPreconditionError(
                "PNG metadata keyword is immutable in H13.",
                details={"reason": "png_keyword_immutable", "chunk_index": chunk_index},
            )
        if old_value != owner.value or old_value != node.payload.text:
            raise PatchPreconditionError(
                "PNG metadata old_value is stale.",
                details={
                    "reason": "png_old_value_mismatch",
                    "expected": owner.value,
                    "actual": old_value,
                },
            )

        replacement_chunk = _encode_replacement_chunk(owner, value, limits=limits)
        prepared.append(
            _PreparedEdit(
                node=node,
                chunk_index=chunk_index,
                owner=owner,
                old_value=old_value,
                value=value,
                replacement_chunk=replacement_chunk,
            )
        )

    return tuple(prepared)


def _construct_candidate(
    source_bytes: bytes,
    fresh: ParsedPng,
    prepared: tuple[_PreparedEdit, ...],
) -> bytes:
    replacements: list[tuple[int, int, bytes]] = []
    for item in prepared:
        if item.value == item.old_value:
            continue
        chunk = fresh.chunk(item.chunk_index)
        replacements.append((chunk.start, chunk.end, item.replacement_chunk))

    candidate = source_bytes
    for start, end, replacement in sorted(replacements, reverse=True):
        candidate = candidate[:start] + replacement + candidate[end:]
    return candidate


def patch_png(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation] = (),
    limits: PngLimits | None = None,
) -> WriterResult:
    validate_document(document)
    requested_limits = limits or PngLimits()
    active_limits = _intersect_limits(requested_limits, _read_time_limits(document))
    source_bytes = _read_source_bytes(source_stream)
    _validate_source_authority(document, source_bytes)
    fresh = _fresh_parse(source_bytes, active_limits)
    edit_list = tuple(edits)
    prepared = _prepare_edits(document, fresh, edit_list, active_limits)

    if not prepared:
        candidate = source_bytes
        fidelity = FidelityReport(
            claimed_tier="exact-preserve",
            evidence=(
                FidelityEvidence(
                    check_code="png.byte_identity",
                    status=FidelityStatus.PASSED,
                    description="No-op PNG patch preserves source bytes exactly.",
                    expected=sha256(source_bytes).hexdigest(),
                    actual=sha256(candidate).hexdigest(),
                ),
            ),
        )
    else:
        candidate = _construct_candidate(source_bytes, fresh, prepared)
        requested_values = {
            item.chunk_index: (item.owner.keyword, item.value) for item in prepared
        }
        verify_png_candidate(
            source_bytes,
            candidate,
            requested_values=requested_values,
            limits=active_limits,
        )
        exact = candidate == source_bytes
        fidelity = FidelityReport(
            claimed_tier="exact-preserve" if exact else "high",
            evidence=(
                FidelityEvidence(
                    check_code="png.semantic_readback",
                    status=FidelityStatus.PASSED,
                    description="Requested PNG text values passed strict semantic re-read.",
                    expected={item.owner.keyword: item.value for item in prepared},
                    actual={item.owner.keyword: item.value for item in prepared},
                    affected_node_ids=tuple(item.node.node_id for item in prepared),
                ),
                FidelityEvidence(
                    check_code="png.unrequested_chunk_identity",
                    status=FidelityStatus.PASSED,
                    description="Every unrequested PNG chunk remained byte-identical.",
                    expected="exact",
                    actual="exact",
                    affected_node_ids=tuple(item.node.node_id for item in prepared),
                ),
            ),
        )

    written = output.write(candidate)
    return WriterResult(
        format="png",
        mode="patch",
        bytes_written=len(candidate) if written is None else written,
        fidelity=fidelity,
        metadata={
            "touched_nodes": tuple(item.node.node_id for item in prepared),
            "touched_chunk_indexes": tuple(item.chunk_index for item in prepared),
        },
    )


class PngPatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        source_format = document.source.format if document.source is not None else None
        if source_format != "png":
            return False
        extension = (target.extension or "").lower()
        return target.format.lower() == "png" or extension == ".png"

    def write(
        self,
        document: DocumentIR,
        output: BinaryIO,
        target: TargetInfo,
        **kwargs: Any,
    ) -> WriterResult:
        source_stream = kwargs.pop("source_stream", None)
        edits = kwargs.pop("edits", None)
        limits = kwargs.pop("limits", None)
        if source_stream is None or edits is None:
            raise TypeError("PngPatchWriter.write requires source_stream= and edits=")
        if kwargs:
            raise TypeError(f"unexpected PNG writer options: {sorted(kwargs)}")
        return patch_png(
            document,
            source_stream,
            output,
            edits=tuple(edits),
            limits=limits,
        )
