from __future__ import annotations

from typing import Any, BinaryIO

from ..._results import WriterResult
from ...ir.document import DocumentIR
from ...writers.base import DocumentWriter, TargetInfo
from .writer import patch_pdf


class PdfPatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        del kwargs
        source_format = document.source.format if document.source is not None else None
        extension = (target.extension or "").lower()
        return source_format == "pdf" and (
            target.format.lower() == "pdf" or extension == ".pdf"
        )

    def write(
        self,
        document: DocumentIR,
        output: BinaryIO,
        target: TargetInfo,
        **kwargs: Any,
    ) -> WriterResult:
        del target
        source_stream = kwargs.pop("source_stream", None)
        edits = kwargs.pop("edits", None)
        limits = kwargs.pop("limits", None)
        if source_stream is None or edits is None:
            raise TypeError("PdfPatchWriter.write requires source_stream= and edits=")
        if kwargs:
            raise TypeError(f"unexpected PDF writer options: {sorted(kwargs)}")
        return patch_pdf(
            document,
            source_stream,
            output,
            edits=tuple(edits),
            limits=limits,
        )
