from __future__ import annotations

from hashlib import sha1
from io import BytesIO
from pathlib import Path

from markitdown._base_converter import DocumentConverterResult
from markitdown._exceptions import FileConversionException, UnsupportedFormatException
from markitdown._stream_info import StreamInfo
from markitdown.converters._zip_converter import ZipConverter

from ._zip_fixtures import make_zip


_PROTECTED_ZIP_CONVERTER_BLOB = "a30a8bdc8d24f4f161b83e92ee6ebea03a956e67"


def _git_blob_sha(payload: bytes) -> str:
    payload = payload.replace(b"\r\n", b"\n")
    header = f"blob {len(payload)}\0".encode("ascii")
    return sha1(header + payload).hexdigest()


def test_oneway_zip_converter_blob_is_regression_locked() -> None:
    package_root = Path(__file__).resolve().parents[2]
    converter_path = package_root / "src/markitdown/converters/_zip_converter.py"

    assert _git_blob_sha(converter_path.read_bytes()) == _PROTECTED_ZIP_CONVERTER_BLOB


class _RecordingMarkItDown:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, str | None, bytes]] = []

    def convert_stream(self, *, stream, stream_info):
        payload = stream.read()
        self.calls.append((stream_info.filename, stream_info.extension, payload))
        if stream_info.filename == "skip.bin":
            raise UnsupportedFormatException("unsupported")
        if stream_info.filename == "broken.dat":
            raise FileConversionException("broken")
        return DocumentConverterResult(markdown=f"converted:{payload.decode('utf-8')}")


def test_oneway_zip_converter_behavior_remains_independent_of_h8_registry() -> None:
    markitdown = _RecordingMarkItDown()
    converter = ZipConverter(markitdown=markitdown)
    source = make_zip(
        members={
            "docs/readme.txt": b"hello",
            "skip.bin": b"skip",
            "broken.dat": b"broken",
        }
    )

    result = converter.convert(
        BytesIO(source),
        StreamInfo(filename="bundle.zip", extension=".zip"),
    )

    assert markitdown.calls == [
        ("readme.txt", ".txt", b"hello"),
        ("skip.bin", ".bin", b"skip"),
        ("broken.dat", ".dat", b"broken"),
    ]
    assert "Content from the zip file `bundle.zip`:" in result.markdown
    assert "## File: docs/readme.txt" in result.markdown
    assert "converted:hello" in result.markdown
    assert "## File: skip.bin" not in result.markdown
    assert "## File: broken.dat" not in result.markdown
