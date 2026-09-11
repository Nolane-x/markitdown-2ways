from __future__ import annotations

from hashlib import sha256

from ..ir.document import DocumentIR
from ..ir.serialization import canonical_json_digest, validate_document
from .identity import encode_block_marker, encode_projection_header
from .model import (
    MarkdownProjection,
    MarkdownProjectionMode,
    MarkdownProjectionOptions,
    ProjectionBlock,
    ProjectionDiagnostic,
    ProjectionManifest,
)
from .rendering import (
    native_locator_digest,
    normalize_markdown_block,
    render_node,
    source_semantic_digest,
)


def _projection_id(document_id: str, node_id: str, ordinal: int) -> str:
    material = f"{document_id}\0{node_id}\0{ordinal}".encode("utf-8")
    return "p_" + sha256(material).hexdigest()[:20]


def _rendered_digest(markdown: str) -> str:
    return sha256(normalize_markdown_block(markdown).encode("utf-8")).hexdigest()


def _normalize_document(parts: list[str]) -> str:
    normalized = [
        normalize_markdown_block(part)
        for part in parts
        if normalize_markdown_block(part)
    ]
    if not normalized:
        return ""
    return "\n\n".join(normalized).rstrip() + "\n"


def project_markdown(
    document: DocumentIR,
    *,
    options: MarkdownProjectionOptions | None = None,
) -> MarkdownProjection:
    validate_document(document)
    options = options or MarkdownProjectionOptions()
    source_digest = canonical_json_digest(document)
    diagnostics: list[ProjectionDiagnostic] = []
    blocks: list[ProjectionBlock] = []
    parts: list[str] = []
    visited: set[str] = set()
    ordinal = 0

    has_title_node = any(
        (node.semantic_role or "").lower() == "title"
        for node in document.nodes.values()
    )
    if options.mode is MarkdownProjectionMode.IDENTITY:
        parts.append(
            encode_projection_header(
                version="1",
                document_id=document.document_id,
                source_digest=source_digest,
            )
        )
        if (
            options.include_document_title
            and document.metadata.title
            and not has_title_node
        ):
            diagnostics.append(
                ProjectionDiagnostic(
                    code="markdown.projection.document_title_omitted",
                    severity="info",
                    message="Document metadata title was omitted in identity mode because it has no stable node identity.",
                )
            )
    elif (
        options.include_document_title
        and document.metadata.title
        and not has_title_node
    ):
        parts.append(f"# {document.metadata.title}")

    def visit(node_id: str) -> None:
        nonlocal ordinal
        if node_id in visited:
            return
        node = document.nodes[node_id]
        visited.add(node_id)
        if node.kind == "group":
            for child_id in node.children:
                visit(child_id)
            return
        rendered = render_node(node, options)
        if rendered is None:
            if node.kind == "unknown_native":
                diagnostics.append(
                    ProjectionDiagnostic(
                        code="markdown.projection.unknown_native_omitted",
                        severity="info",
                        message="Unknown native content was preserved in IR and omitted from Markdown.",
                        node_id=node.node_id,
                    )
                )
            for child_id in node.children:
                visit(child_id)
            return
        diagnostics.extend(rendered.diagnostics)
        pid = _projection_id(document.document_id, node.node_id, ordinal)
        semantic_digest = source_semantic_digest(node)
        block = ProjectionBlock(
            projection_id=pid,
            node_id=node.node_id,
            canvas_id=node.canvas_id,
            node_kind=node.kind,
            semantic_role=node.semantic_role,
            ordinal=ordinal,
            source_semantic_digest=semantic_digest,
            native_locator_digest=native_locator_digest(node),
            editable_capabilities=rendered.editable_capabilities,
            rendered_digest=_rendered_digest(rendered.markdown),
        )
        blocks.append(block)
        if options.mode is MarkdownProjectionMode.IDENTITY:
            parts.append(
                encode_block_marker(
                    projection_id=pid,
                    node_id=node.node_id,
                    kind=node.kind,
                    source_digest=semantic_digest,
                )
            )
        parts.append(rendered.markdown)
        ordinal += 1
        for child_id in node.children:
            visit(child_id)

    for canvas in sorted(document.canvases, key=lambda item: item.index):
        for root_id in canvas.root_node_ids:
            visit(root_id)
    for root_id in document.root_node_ids:
        if root_id not in visited:
            visit(root_id)
    for node_id in sorted(set(document.nodes) - visited):
        diagnostics.append(
            ProjectionDiagnostic(
                code="markdown.projection.orphan_node",
                severity="warning",
                message="Node was not reachable through explicit document/canvas order and was not projected.",
                node_id=node_id,
            )
        )

    markdown = _normalize_document(parts)
    manifest = ProjectionManifest(
        format_version="1",
        document_id=document.document_id,
        document_schema_version=document.schema_version,
        source_document_digest=source_digest,
        projection_mode=options.mode.value,
        blocks=tuple(blocks),
        diagnostics=tuple(diagnostics),
    )
    return MarkdownProjection(markdown=markdown, manifest=manifest)
