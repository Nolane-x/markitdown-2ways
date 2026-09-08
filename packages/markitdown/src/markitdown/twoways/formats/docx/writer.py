from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from typing import Any, BinaryIO, Sequence
from zipfile import ZipFile

from ..._errors import PatchPreconditionError, UnsupportedEditError
from ..._results import FidelityEvidence, FidelityReport, FidelityStatus, WriterResult
from ...ir.document import DocumentIR
from ...ir.edits import EditOperation
from ...ir.serialization import validate_document
from ...ooxml import parse_xml_part, serialize_xml_part, snapshot_package, write_package
from ...ooxml.package import read_binary_stream, validate_source_authority
from ...writers.base import DocumentWriter, TargetInfo
from ._writer_apply import _apply_edit
from .model import DocxPatchOptions
from .verify import verify_docx_output


def patch_docx(
    document: DocumentIR,
    source_stream: BinaryIO,
    output: BinaryIO,
    *,
    edits: Sequence[EditOperation],
    options: DocxPatchOptions | None = None,
) -> WriterResult:
    options = options or DocxPatchOptions()
    validate_document(document)
    source_bytes = read_binary_stream(source_stream, stream_label="DOCX source")
    validate_source_authority(document, source_bytes, expected_format="docx")
    snapshot = snapshot_package(source_bytes, limits=options.limits)
    edit_list = tuple(edits)

    if not edit_list:
        written = output.write(source_bytes)
        return WriterResult(
            format="docx",
            mode="patch",
            bytes_written=len(source_bytes) if written is None else written,
            fidelity=FidelityReport(
                claimed_tier="exact-preserve",
                evidence=(
                    FidelityEvidence(
                        check_code="docx.archive.byte_identity",
                        status=FidelityStatus.PASSED,
                        description="No-op patch preserves source DOCX byte-for-byte.",
                        expected=snapshot.source_sha256,
                        actual=sha256(source_bytes).hexdigest(),
                    ),
                ),
            ),
            metadata={"touched_parts": ()},
        )

    allowed_parts = {
        canvas.native_locator.part_uri
        for canvas in document.canvases
        if canvas.native_locator is not None and canvas.native_locator.part_uri
    }
    edits_by_part: dict[str, list[EditOperation]] = {}
    for edit in edit_list:
        if edit.target_node_id is None or edit.target_node_id not in document.nodes:
            raise PatchPreconditionError(
                "DOCX edit target node does not exist in the source IR.",
                details={
                    "reason": "missing_target",
                    "target_node_id": edit.target_node_id,
                },
            )
        node = document.nodes[edit.target_node_id]
        if node.native_locator is None or not node.native_locator.part_uri:
            raise PatchPreconditionError(
                "DOCX edit target is not bound to an OOXML part.",
                details={"reason": "missing_part_uri", "target_node_id": node.node_id},
            )
        part_uri = node.native_locator.part_uri
        if part_uri not in allowed_parts or not part_uri.endswith(".xml"):
            raise UnsupportedEditError(
                "Phase D v1 patches only discovered body/header/footer XML parts.",
                details={"reason": "unsupported_part", "part_uri": part_uri},
            )
        edits_by_part.setdefault(part_uri, []).append(edit)

    replacements: dict[str, bytes] = {}
    with ZipFile(BytesIO(source_bytes), "r") as archive:
        for part_uri in sorted(edits_by_part):
            archive_name = part_uri.lstrip("/")
            try:
                original_part = archive.read(archive_name)
            except KeyError as exc:
                raise PatchPreconditionError(
                    "DOCX native locator references a missing XML part.",
                    details={"reason": "missing_part", "part_uri": part_uri},
                ) from exc
            root = parse_xml_part(original_part)
            for edit in edits_by_part[part_uri]:
                _apply_edit(root, document, edit, part_uri=part_uri)
            replacements[archive_name] = serialize_xml_part(root)

    buffer = BytesIO()
    write_package(snapshot, source_bytes, buffer, replacements=replacements)
    output_bytes = buffer.getvalue()
    touched_parts = tuple(sorted(replacements))
    if options.verify_output:
        fidelity = verify_docx_output(
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
            warnings=("Round-trip verification was disabled by DocxPatchOptions.",),
        )
    written = output.write(output_bytes)
    return WriterResult(
        format="docx",
        mode="patch",
        bytes_written=len(output_bytes) if written is None else written,
        fidelity=fidelity,
        metadata={"touched_parts": touched_parts},
    )


class DocxPatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        return (
            document.source is not None
            and document.source.format == "docx"
            and (
                target.format.lower() == "docx"
                or (target.extension or "").lower() == ".docx"
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
            raise TypeError("DocxPatchWriter.write requires source_stream= and edits=")
        options = kwargs.pop("options", None)
        if kwargs:
            raise TypeError(f"unexpected DOCX writer options: {sorted(kwargs)}")
        return patch_docx(
            document,
            source_stream,
            output,
            edits=tuple(edits),
            options=options,
        )
