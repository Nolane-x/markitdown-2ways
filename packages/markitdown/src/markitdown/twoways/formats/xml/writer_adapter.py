from __future__ import annotations

from typing import Any, BinaryIO

from ..._results import WriterResult
from ...ir.document import DocumentIR
from ...writers.base import DocumentWriter, TargetInfo
from .writer import patch_xml


class XmlPatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        del kwargs
        source_format = document.source.format if document.source is not None else None
        return source_format == "xml" and (
            target.format.lower() == "xml" or (target.extension or "").lower() == ".xml"
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
        if source_stream is None or edits is None:
            raise TypeError("XmlPatchWriter.write requires source_stream= and edits=")
        if kwargs:
            raise TypeError(f"unexpected XML writer options: {sorted(kwargs)}")
        return patch_xml(
            document,
            source_stream,
            output,
            edits=tuple(edits),
        )
