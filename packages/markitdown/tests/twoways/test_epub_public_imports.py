from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways.formats.epub import (
    EpubIRReader,
    EpubPatchWriter,
    EpubParseError,
    parse_epub_source,
    patch_epub,
    read_epub_ir,
)
from markitdown.twoways.formats.json.reader import read_json_ir
from markitdown.twoways.writers.base import TargetInfo

from ._epub_fixtures import make_epub


def test_epub_public_imports_are_stable() -> None:
    assert EpubIRReader.__name__ == "EpubIRReader"
    assert EpubPatchWriter.__name__ == "EpubPatchWriter"
    assert EpubParseError.__name__ == "EpubParseError"
    assert callable(parse_epub_source)
    assert callable(read_epub_ir)
    assert callable(patch_epub)


def test_epub_patch_writer_accepts_only_epub_backed_targets() -> None:
    writer = EpubPatchWriter()
    document = read_epub_ir(BytesIO(make_epub()), filename="book.epub")
    json_document = read_json_ir(BytesIO(b"{}"), filename="data.json")

    assert writer.accepts(document, TargetInfo(format="epub"))
    assert writer.accepts(document, TargetInfo(format="native", extension=".EPUB"))
    assert not writer.accepts(document, TargetInfo(format="zip", extension=".zip"))
    assert not writer.accepts(
        json_document,
        TargetInfo(format="epub", extension=".epub"),
    )


def test_epub_patch_writer_requires_source_stream_and_edits() -> None:
    writer = EpubPatchWriter()
    document = read_epub_ir(BytesIO(make_epub()), filename="book.epub")

    with pytest.raises(TypeError, match="source_stream=.*edits="):
        writer.write(document, BytesIO(), TargetInfo(format="epub"))


def test_epub_patch_writer_rejects_unknown_options() -> None:
    writer = EpubPatchWriter()
    source = make_epub()
    document = read_epub_ir(BytesIO(source), filename="book.epub")

    with pytest.raises(TypeError, match="unexpected EPUB writer options"):
        writer.write(
            document,
            BytesIO(),
            TargetInfo(format="epub"),
            source_stream=BytesIO(source),
            edits=(),
            surprise=True,
        )
