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
from ...ir.nodes import ImagePayload, TextPayload
from ...ir.semantics import node_semantic_text
from ...ir.serialization import validate_document
from ...ooxml import parse_xml_part, serialize_xml_part, snapshot_package, write_package
from ...ooxml.package import read_binary_stream, validate_source_authority
from ...writers.base import DocumentWriter, TargetInfo
from .locators import resolve_shape_element
from .model import PptxPatchOptions
from .patch import patch_picture_alt_text, validate_edit_preconditions
from .text import patch_text_shape
from .verify import verify_pptx_output


def _archive_name(part_uri: str) -> str:
    return part_uri.lstrip("/")


def _apply_edit(root: Any, document: DocumentIR, edit: EditOperation, *, part_uri: str) -> None:
    if edit.target_node_id is None or edit.target_node_id not in document.nodes:
        raise PatchPreconditionError(
            "PPTX edit target node does not exist in the source IR.",
            details={"reason": "missing_target", "target_node_id": edit.target_node_id},
        )
    node = document.nodes[edit.target_node_id]
    if node.native_locator is None:
        raise PatchPreconditionError(
            "PPTX edit target has no native locator.",
            details={"reason": "missing_native_locator", "target_node_id": node.node_id},
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
                details={"reason": "unsupported_text_structure", "target_node_id": node.node_id},
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

    raise UnsupportedEditError(
        "PPTX patch writer does not support this edit type in Phase C v1.",
        details={"reason": "unsupported_edit_type", "edit_type": edit.type},
    )


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
                details={"reason": "missing_target", "target_node_id": edit.target_node_id},
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
                "Phase C v1 patches only PPTX slide or notes-slide XML parts.",
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
            edits=edit_list,
            touched_parts=touched_parts,
            limits=options.limits,
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
