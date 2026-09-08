from __future__ import annotations

from typing import TYPE_CHECKING, Any, BinaryIO, Protocol, runtime_checkable

from ..ir.document import DocumentIR

if TYPE_CHECKING:
    from ..._stream_info import StreamInfo


@runtime_checkable
class DocumentIRReader(Protocol):
    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: "StreamInfo",
        **kwargs: Any,
    ) -> bool: ...

    def read(
        self,
        file_stream: BinaryIO,
        stream_info: "StreamInfo",
        **kwargs: Any,
    ) -> DocumentIR: ...
