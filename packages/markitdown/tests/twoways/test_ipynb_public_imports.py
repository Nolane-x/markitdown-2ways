from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways.formats.ipynb import (
    IpynbIRReader,
    IpynbPatchWriter,
    patch_ipynb,
    read_ipynb_ir,
)
from markitdown.twoways.formats.json.reader import read_json_ir
from markitdown.twoways.writers.base import TargetInfo


def _source():
    return b'{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":5}'


def test_ipynb_public_imports_are_stable() -> None:
    assert IpynbIRReader.__name__ == "IpynbIRReader"
    assert IpynbPatchWriter.__name__ == "IpynbPatchWriter"
    assert callable(read_ipynb_ir)
    assert callable(patch_ipynb)


def test_ipynb_patch_writer_accepts_only_ipynb_backed_targets() -> None:
    writer = IpynbPatchWriter()
    document = read_ipynb_ir(BytesIO(_source()), filename="book.ipynb")
    json_document = read_json_ir(BytesIO(b"{}"), filename="data.json")

    assert writer.accepts(document, TargetInfo(format="ipynb"))
    assert writer.accepts(document, TargetInfo(format="native", extension=".IPYNB"))
    assert not writer.accepts(document, TargetInfo(format="json", extension=".json"))
    assert not writer.accepts(
        json_document,
        TargetInfo(format="ipynb", extension=".ipynb"),
    )


def test_ipynb_patch_writer_requires_source_stream_and_edits() -> None:
    writer = IpynbPatchWriter()
    document = read_ipynb_ir(BytesIO(_source()), filename="book.ipynb")

    with pytest.raises(TypeError, match="source_stream=.*edits="):
        writer.write(document, BytesIO(), TargetInfo(format="ipynb"))


def test_ipynb_patch_writer_rejects_unknown_options() -> None:
    writer = IpynbPatchWriter()
    source = _source()
    document = read_ipynb_ir(BytesIO(source), filename="book.ipynb")

    with pytest.raises(TypeError, match="unexpected IPYNB writer options"):
        writer.write(
            document,
            BytesIO(),
            TargetInfo(format="ipynb"),
            source_stream=BytesIO(source),
            edits=(),
            surprise=True,
        )
