from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways.formats.json.reader import read_json_ir
from markitdown.twoways.formats.zip import (
    ZipIRReader,
    ZipParseError,
    ZipPatchWriter,
    ZipRecursiveLimits,
    parse_zip_source,
    patch_zip,
    read_zip_ir,
)
from markitdown.twoways.writers.base import TargetInfo

from ._zip_fixtures import make_zip


def test_zip_public_format_surface() -> None:
    assert ZipIRReader.__name__ == "ZipIRReader"
    assert ZipPatchWriter.__name__ == "ZipPatchWriter"
    assert ZipParseError.__name__ == "ZipParseError"
    assert ZipRecursiveLimits.__name__ == "ZipRecursiveLimits"
    assert callable(parse_zip_source)
    assert callable(patch_zip)
    assert callable(read_zip_ir)


def test_zip_patch_writer_accepts_only_zip_backed_targets() -> None:
    writer = ZipPatchWriter()
    document = read_zip_ir(BytesIO(make_zip()), filename="bundle.zip")
    json_document = read_json_ir(BytesIO(b"{}"), filename="data.json")

    assert writer.accepts(document, TargetInfo(format="zip"))
    assert writer.accepts(document, TargetInfo(format="native", extension=".ZIP"))
    assert not writer.accepts(document, TargetInfo(format="epub", extension=".epub"))
    assert not writer.accepts(
        json_document,
        TargetInfo(format="zip", extension=".zip"),
    )


def test_zip_patch_writer_requires_source_stream_and_edits() -> None:
    writer = ZipPatchWriter()
    document = read_zip_ir(BytesIO(make_zip()), filename="bundle.zip")

    with pytest.raises(TypeError, match="source_stream=.*edits="):
        writer.write(document, BytesIO(), TargetInfo(format="zip"))


def test_zip_patch_writer_rejects_unknown_options() -> None:
    writer = ZipPatchWriter()
    source = make_zip()
    document = read_zip_ir(BytesIO(source), filename="bundle.zip")

    with pytest.raises(TypeError, match="unexpected ZIP writer options"):
        writer.write(
            document,
            BytesIO(),
            TargetInfo(format="zip"),
            source_stream=BytesIO(source),
            edits=(),
            surprise=True,
        )
