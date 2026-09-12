from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from typing import Any, BinaryIO, Sequence
from zipfile import ZipFile

from ..._errors import (
    PatchPreconditionError,
    UnsupportedEditError,
)
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus, WriterResult
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.geometry_edits import validate_move_resize
from ...ir.nodes import ImagePayload, TablePayload, TextPayload
from ...ir.semantics import node_semantic_text
from ...ir.serialization import validate_document
from ...ir.style_edits import validate_text_style_update
from ...ooxml import parse_xml_part, serialize_xml_part, snapshot_package, write_package
from ...ooxml.package import read_binary_stream, validate_source_authority
from ...writers.base import DocumentWriter, TargetInfo
from .geometry import patch_shape_geometry, verify_geometry_readback
from .locators import resolve_shape_element
from .model import PptxPatchOptions
from .patch import patch_picture_alt_text, validate_edit_preconditions
from .style import patch_text_run_style, verify_text_style_readback
from .table import patch_pptx_table_cells
from .text import patch_text_shape
from .verify import verify_pptx_output


def _archive_name(part_uri: str) -> str:
    return part_uri.lstrip("/")


def _apply_edit(
    root: Any, document: DocumentIR, edit: EditOperation, *, part_uri: str
) -> None:
    if edit.target_node_id is None or edit.target_node_id not in document.nodes:
        raise PatchPreconditionError(
            "PPTX edit target node does not exist in the source IR.",
            details={"reason": "missing_target", "target_node_id": edit.target_node_id},
        )
    node = document.nodes[edit.target_node_id]
    if node.native_locator is None:
        raise PatchPreconditionError(
            "PPTX edit target has no native locator.",
            details={
                "reason": "missing_native_locator",
                "target_node_id": node.node_id,
            },
        )
    validate_edit_preconditions(document, node, edit)
    shape_element = resolve_shape_element(
        root,
        node.native_locator,
        part_uri=part_uri,
        strict=True,
    )

    if edit.type == "replace_text":
        if not isinstance(node.payload, TextPayload):
            raise UnsupportedEditError(
                "replace_text requires a text node.",
                details={"reason": "wrong_node_kind", "target_node_id": node.node_id},
            )
        if node.metadata.get("pptx:patch_text_compatible") is not True:
            raise UnsupportedEditError(
                "PPTX text node is not patch-compatible in Phase C v1.",
                details={
                    "reason": "unsupported_text_structure",
                    "target_node_id": node.node_id,
                },
            )
        new_text = edit.payload.get("text")
        if not isinstance(new_text, str):
            raise UnsupportedEditError(
                "replace_text requires a string text payload.",
                details={"reason": "invalid_edit_payload"},
            )
        patch_text_shape(
            shape_element,
            old_text=node_semantic_text(node),
            new_text=new_text,
        )
        return

    if edit.type == "set_text_style":
        if not isinstance(node.payload, TextPayload):
            raise UnsupportedEditError(
                "set_text_style requires a PPTX text node.",
                details={"reason": "wrong_node_kind", "target_node_id": node.node_id},
            )
        if node.metadata.get("pptx:patch_text_compatible") is not True:
            raise UnsupportedEditError(
                "PPTX text node is not structurally safe for direct style editing.",
                details={
                    "reason": "unsupported_text_structure",
                    "target_node_id": node.node_id,
                },
            )
        run_index, source_style, target_style = validate_text_style_update(
            node.payload,
            edit.payload,
        )
        patch_text_run_style(
            shape_element,
            run_index=run_index,
            old_style=source_style,
            new_style=target_style,
        )
        return

    if edit.type == "move_resize":
        if node.geometry is None:
            raise UnsupportedEditError(
                "move_resize requires source geometry.",
                details={"reason": "missing_geometry", "target_node_id": node.node_id},
            )
        if node.kind == "group" or node.parent_id is not None:
            raise UnsupportedEditError(
                "PPTX group and group-child geometry requires group-coordinate editing.",
                details={
                    "reason": "pptx.geometry.group_coordinate_space",
                    "target_node_id": node.node_id,
                },
            )
        if not part_uri.startswith("/ppt/slides/"):
            raise UnsupportedEditError(
                "PPTX move_resize is limited to slide shapes in this tranche.",
                details={"reason": "pptx.geometry.unsupported_part", "part_uri": part_uri},
            )
        target_geometry = validate_move_resize(node.geometry, edit.payload)
        patch_shape_geometry(
            shape_element,
            current=node.geometry,
            target=target_geometry,
        )
        return

    if edit.type == "set_alt_text":
        if not isinstance(node.payload, ImagePayload):
            raise UnsupportedEditError(
                "set_alt_text requires an image node.",
                details={"reason": "wrong_node_kind", "target_node_id": node.node_id},
            )
        new_alt = edit.payload.get("alt_text")
        if not isinstance(new_alt, str):
            raise UnsupportedEditError(
                "set_alt_text requires a string alt_text payload.",
                details={"reason": "invalid_edit_payload"},
            )
        patch_picture_alt_text(shape_element, new_alt_text=new_alt)
        return

    if edit.type == "update_table_cells":
        if not isinstance(node.payload, TablePayload):
            raise UnsupportedEditError(
                "update_table_cells requires a PPTX table node.",
                details={"reason": "wrong_node_kind", "target_node_id": node.node_id},
            )
        capabilities = node.metadata.get("pptx:patch_capabilities", ())
        if (
            not isinstance(capabilities, (tuple, list, set, frozenset))
            or "update_table_cells" not in capabilities
        ):
            raise UnsupportedEditError(
                "PPTX table structure is read-only in Phase E.",
                details={
                    "reason": "unsupported_table_structure",
                    "target_node_id": node.node_id,
                },
            )
        patch_pptx_table_cells(
            shape_element,
            node.payload,
            edit.payload.get("cells"),
        )
        return

    raise UnsupportedEditError(
        "PPTX patch writer does not support this edit type.",
        details={"reason": "unsupported_edit_type", "edit_type": edit.type},
    )


def _verification_edits(
    document: DocumentIR,
    edits: tuple[EditOperation, ...],
) -> tuple[EditOperation, ...]:
    result: list[EditOperation] = []
    for edit in edits:
        if edit.type not in {"set_text_style", "move_resize"} or edit.target_node_id is None:
            result.append(edit)
            continue
        node = document.nodes[edit.target_node_id]
        result.append(
            EditOperation(
                operation_id=f"{edit.operation_id}:semantic-readback",
                type="replace_text",
                target_node_id=edit.target_node_id,
                precondition=edit.precondition,
                payload={"text": node_semantic_text(node)},
                source_label=edit.source_label,
            )
        )
    return tuple(result)


def patch_pptx(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation],
    options: PptxPatchOptions | None = None,
) -> WriterResult:
    options = options or PptxPatchOptions()
    validate_document(document)
    source_bytes = read_binary_stream(source_stream, stream_label="PPTX source")
    validate_source_authority(document, source_bytes, expected_format="pptx")
    snapshot = snapshot_package(source_bytes, limits=options.limits)
    edit_list = tuple(edits)

    if not edit_list:
        buffer = BytesIO()
        write_package(
            snapshot,
            source_bytes,
            buffer,
            replacements={},
            limits=options.limits,
        )
        output_bytes = buffer.getvalue()
        written = output.write(output_bytes)
        fidelity = FidelityReport(
            claimed_tier="exact-preserve",
            evidence=(
                FidelityEvidence(
                    check_code="archive.byte_identity",
                    status=FidelityStatus.PASSED,
                    description="No-op patch preserves the source PPTX byte-for-byte.",
                    expected=snapshot.source_sha256,
                    actual=sha256(output_bytes).hexdigest(),
                ),
            ),
        )
        return WriterResult(
            format="pptx",
            mode="patch",
            bytes_written=len(output_bytes) if written is None else written,
            fidelity=fidelity,
            metadata={"touched_parts": ()},
        )

    edits_by_part: dict[str, list[EditOperation]] = {}
    for edit in edit_list:
        if edit.target_node_id is None or edit.target_node_id not in document.nodes:
            raise PatchPreconditionError(
                "PPTX edit target node does not exist in the source IR.",
                details={
                    "reason": "missing_target",
                    "target_node_id": edit.target_node_id,
                },
            )
        node = document.nodes[edit.target_node_id]
        if node.native_locator is None or not node.native_locator.part_uri:
            raise PatchPreconditionError(
                "PPTX edit target is not bound to an OOXML part.",
                details={"reason": "missing_part_uri", "target_node_id": node.node_id},
            )
        part_uri = node.native_locator.part_uri
        allowed_part = (
            part_uri.startswith("/ppt/slides/")
            or part_uri.startswith("/ppt/notesSlides/")
        ) and part_uri.endswith(".xml")
        if not allowed_part:
            raise UnsupportedEditError(
                "PPTX patching supports only slide or notes-slide XML parts.",
                details={"reason": "unsupported_part", "part_uri": part_uri},
            )
        edits_by_part.setdefault(part_uri, []).append(edit)

    replacements: dict[str, bytes] = {}
    with ZipFile(BytesIO(source_bytes), "r") as archive:
        for part_uri in sorted(edits_by_part):
            archive_name = _archive_name(part_uri)
            try:
                original_part = archive.read(archive_name)
            except KeyError as exc:
                raise PatchPreconditionError(
                    "PPTX native locator references a missing slide part.",
                    details={"reason": "missing_part", "part_uri": part_uri},
                ) from exc
            root = parse_xml_part(original_part)
            for edit in edits_by_part[part_uri]:
                _apply_edit(root, document, edit, part_uri=part_uri)
            replacements[archive_name] = serialize_xml_part(root)

    buffer = BytesIO()
    write_package(
        snapshot,
        source_bytes,
        buffer,
        replacements=replacements,
        limits=options.limits,
    )
    output_bytes = buffer.getvalue()
    touched_parts = tuple(sorted(replacements))

    if options.verify_output:
        fidelity = verify_pptx_output(
            document,
            source_bytes,
            output_bytes,
            edits=_verification_edits(document, edit_list),
            touched_parts=touched_parts,
            limits=options.limits,
        )
        style_edits = tuple(edit for edit in edit_list if edit.type == "set_text_style")
        geometry_edits = tuple(edit for edit in edit_list if edit.type == "move_resize")
        if style_edits or geometry_edits:
            from .reader import read_pptx_ir

            output_document = read_pptx_ir(BytesIO(output_bytes))
            evidence = fidelity.evidence
            if style_edits:
                affected = verify_text_style_readback(
                    document,
                    output_document,
                    style_edits,
                )
                evidence += (
                    FidelityEvidence(
                        check_code="pptx.style.readback",
                        status=FidelityStatus.PASSED,
                        description=(
                            "Requested PPTX direct run styles read back exactly while "
                            "semantic text remains unchanged."
                        ),
                        affected_node_ids=affected,
                    ),
                )
            if geometry_edits:
                affected = verify_geometry_readback(
                    document,
                    output_document,
                    geometry_edits,
                )
                evidence += (
                    FidelityEvidence(
                        check_code="pptx.geometry.readback",
                        status=FidelityStatus.PASSED,
                        description=(
                            "Requested PPTX slide-shape geometry reads back exactly "
                            "with semantic content unchanged."
                        ),
                        affected_node_ids=affected,
                    ),
                )
            fidelity = FidelityReport(
                claimed_tier=fidelity.claimed_tier,
                evidence=evidence,
                unsupported_features=fidelity.unsupported_features,
                warnings=fidelity.warnings,
            )
    else:
        fidelity = FidelityReport(
            claimed_tier="unknown",
            warnings=("Round-trip verification was disabled by PptxPatchOptions.",),
        )

    written = output.write(output_bytes)
    return WriterResult(
        format="pptx",
        mode="patch",
        bytes_written=len(output_bytes) if written is None else written,
        fidelity=fidelity,
        metadata={"touched_parts": touched_parts},
    )


class PptxPatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        return (
            document.source is not None
            and document.source.format == "pptx"
            and (
                target.format.lower() == "pptx"
                or (target.extension or "").lower() == ".pptx"
            )
        )

    def write(
        self,
        document: DocumentIR,
        output: BinaryIO,
        target: TargetInfo,
        **kwargs: Any,
    ) -> WriterResult:
        source_stream = kwargs.pop("source_stream", None)
        edits = kwargs.pop("edits", None)
        if source_stream is None or edits is None:
            raise TypeError("PptxPatchWriter.write requires source_stream= and edits=")
        options = kwargs.pop("options", None)
        if kwargs:
            raise TypeError(f"unexpected PPTX writer options: {sorted(kwargs)}")
        return patch_pptx(
            document,
            source_stream,
            output,
            edits=tuple(edits),
            options=options,
        )
