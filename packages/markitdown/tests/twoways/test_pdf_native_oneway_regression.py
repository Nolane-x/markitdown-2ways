from __future__ import annotations

from hashlib import sha1
from io import BytesIO
from pathlib import Path

from markitdown._stream_info import StreamInfo
from markitdown.converters._pdf_converter import (
    PdfConverter,
    _merge_partial_numbering_lines,
)


_PROTECTED_PDF_CONVERTER_BLOB = "ffbcbd990cfc40a577404c453ebe47bf477c4929"


def _git_blob_sha(payload: bytes) -> str:
    payload = payload.replace(b"\r\n", b"\n")
    header = f"blob {len(payload)}\0".encode("ascii")
    return sha1(header + payload).hexdigest()


def test_oneway_pdf_converter_blob_is_regression_locked() -> None:
    package_root = Path(__file__).resolve().parents[2]
    converter_path = package_root / "src/markitdown/converters/_pdf_converter.py"

    assert _git_blob_sha(converter_path.read_bytes()) == _PROTECTED_PDF_CONVERTER_BLOB


def test_oneway_pdf_converter_behavior_remains_independent_of_h9_writer() -> None:
    converter = PdfConverter()

    assert converter.accepts(
        BytesIO(b""),
        StreamInfo(filename="sample.pdf", extension=".pdf"),
    )
    assert converter.accepts(
        BytesIO(b""),
        StreamInfo(mimetype="application/pdf"),
    )
    assert not converter.accepts(
        BytesIO(b""),
        StreamInfo(filename="sample.txt", extension=".txt", mimetype="text/plain"),
    )
    assert (
        _merge_partial_numbering_lines(".1\nFirst item\n\n.2\nSecond item")
        == ".1 First item\n\n.2 Second item"
    )
