from __future__ import annotations

from typing import Any, BinaryIO

from ..._results import WriterResult
from ...ir.document import DocumentIR
from ...writers.base import DocumentWriter, TargetInfo
from .writer import patch_ipynb


class IpynbPatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        del kwargs
        source_format = document.source.format if document.source is not None else None
        extension = (target.extension or "").lower()
        return source_format == "ipynb" and (
            target.format.lower() == "ipynb" or extension == ".ipynb"
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
            raise TypeError("IpynbPatchWriter.write requires source_stream= and edits=")
        if kwargs:
            raise TypeError(f"unexpected IPYNB writer options: {sorted(kwargs)}")
        return patch_ipynb(
            document,
            source_stream,
            output,
            edits=tuple(edits),
        )
