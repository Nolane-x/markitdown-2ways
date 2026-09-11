from __future__ import annotations

from dataclasses import dataclass

from ..ir.document import DocumentIR
from ..ir.serialization import canonical_json_digest, validate_document
from .identity import ParsedMarker
from .model import MarkdownImportDiagnostic, ProjectionBlock, ProjectionManifest
from ._import_helpers import raise_identity, raise_import, scan_markers


@dataclass(frozen=True)
class IdentityEnvelope:
    lines: list[str]
    diagnostics: tuple[MarkdownImportDiagnostic, ...]
    block_by_pid: dict[str, ProjectionBlock]
    parsed_blocks: tuple[tuple[int, ParsedMarker], ...]


def validate_identity_input(
    edited_markdown: str,
    *,
    original_document: DocumentIR,
    manifest: ProjectionManifest,
    strict: bool,
) -> IdentityEnvelope:
    if manifest.projection_mode != "identity":
        raise_identity(
            "markdown.header.missing",
            "Only identity-mode projections can be re-imported.",
            projection_mode=manifest.projection_mode,
        )
    validate_document(original_document)
    actual_source_digest = canonical_json_digest(original_document)
    if manifest.document_id != original_document.document_id:
        raise_identity(
            "markdown.header.document_mismatch",
            "Projection manifest belongs to a different document.",
            manifest_document_id=manifest.document_id,
            document_id=original_document.document_id,
        )
    if manifest.source_document_digest != actual_source_digest:
        raise_identity(
            "markdown.header.source_digest_mismatch",
            "Projection manifest source digest does not match the supplied original document.",
            expected=manifest.source_document_digest,
            actual=actual_source_digest,
        )

    lines, markers = scan_markers(edited_markdown, strict=strict)
    diagnostics: list[MarkdownImportDiagnostic] = []
    if not strict:
        for _, marker in markers:
            if marker.unknown_keys:
                diagnostics.append(
                    MarkdownImportDiagnostic(
                        code="markdown.marker.unknown_key",
                        severity="warning",
                        message="Unknown identity marker keys were preserved in permissive mode.",
                        projection_id=marker.attributes.get("pid"),
                        details={"keys": marker.unknown_keys},
                    )
                )

    headers = [
        (index, marker)
        for index, marker in markers
        if marker.marker_type == "projection"
    ]
    if len(headers) != 1:
        raise_identity(
            "markdown.header.missing" if not headers else "markdown.marker.malformed",
            "Identity Markdown must contain exactly one projection header.",
            header_count=len(headers),
        )
    header_index, header = headers[0]
    attrs = header.attributes
    if attrs["v"] != manifest.format_version:
        raise_identity(
            "markdown.marker.metadata_mismatch",
            "Projection header format version does not match manifest.",
            expected=manifest.format_version,
            actual=attrs["v"],
        )
    if attrs["doc"] != original_document.document_id:
        raise_identity(
            "markdown.header.document_mismatch",
            "Projection header belongs to a different document.",
            expected=original_document.document_id,
            actual=attrs["doc"],
        )
    if attrs["base"] != f"sha256:{actual_source_digest}":
        raise_identity(
            "markdown.header.source_digest_mismatch",
            "Projection header source digest does not match original document.",
            expected=f"sha256:{actual_source_digest}",
            actual=attrs["base"],
        )

    block_by_pid = {block.projection_id: block for block in manifest.blocks}
    parsed_blocks = [
        (index, marker) for index, marker in markers if marker.marker_type == "block"
    ]
    seen_pids: set[str] = set()
    seen_nodes: set[str] = set()
    for _, marker in parsed_blocks:
        pid = marker.attributes["pid"]
        node_id = marker.attributes["node"]
        if pid in seen_pids:
            raise_identity(
                "markdown.marker.duplicate_projection_id",
                "Projection id occurs more than once.",
                projection_id=pid,
            )
        seen_pids.add(pid)
        if node_id in seen_nodes:
            raise_identity(
                "markdown.marker.duplicate_node",
                "Node identity occurs in more than one block marker.",
                node_id=node_id,
            )
        seen_nodes.add(node_id)
        if pid not in block_by_pid:
            raise_identity(
                "markdown.marker.unknown_projection_id",
                "Block marker is not present in the supplied manifest.",
                projection_id=pid,
            )
        expected = block_by_pid[pid]
        if (
            marker.attributes["node"] != expected.node_id
            or marker.attributes["kind"] != expected.node_kind
            or marker.attributes["src"] != f"sha256:{expected.source_semantic_digest}"
        ):
            raise_identity(
                "markdown.marker.metadata_mismatch",
                "Block marker identity metadata does not match the manifest.",
                projection_id=pid,
            )

    missing = [
        block.projection_id
        for block in manifest.blocks
        if block.projection_id not in seen_pids
    ]
    if missing:
        raise_identity(
            "markdown.block.missing",
            "One or more projected blocks are missing their identity markers.",
            missing_projection_ids=missing,
        )

    first_block_index = min((index for index, _ in parsed_blocks), default=len(lines))
    unanchored_before = [
        line for line in lines[header_index + 1 : first_block_index] if line.strip()
    ]
    unanchored_prefix = [line for line in lines[:header_index] if line.strip()]
    if unanchored_before or unanchored_prefix:
        raise_import(
            "markdown.block.unanchored_content",
            "Substantive content exists outside a marked identity block.",
            content=unanchored_prefix + unanchored_before,
        )

    parsed_blocks.sort(key=lambda item: item[0])
    return IdentityEnvelope(
        lines=lines,
        diagnostics=tuple(diagnostics),
        block_by_pid=block_by_pid,
        parsed_blocks=tuple(parsed_blocks),
    )
