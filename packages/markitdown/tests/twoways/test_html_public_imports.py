from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways.formats.html import (
    HtmlIRReader,
    HtmlPatchWriter,
    patch_html,
    read_html_ir,
)
from markitdown.twoways.formats.json.reader import read_json_ir
from markitdown.twoways.writers.base import TargetInfo


def test_html_adapter_public_imports_are_stable() -> None:
    assert HtmlIRReader.__name__ == "HtmlIRReader"
    assert HtmlPatchWriter.__name__ == "HtmlPatchWriter"
    assert callable(read_html_ir)
    assert callable(patch_html)


def test_html_patch_writer_accepts_only_html_backed_html_targets() -> None:
    writer = HtmlPatchWriter()
    html_document = read_html_ir(
        BytesIO(b"<html><body>x</body></html>"), filename="page.html"
    )
    json_document = read_json_ir(BytesIO(b"{}"), filename="data.json")

    assert writer.accepts(html_document, TargetInfo(format="html"))
    assert writer.accepts(html_document, TargetInfo(format="native", extension=".HTML"))
    assert writer.accepts(html_document, TargetInfo(format="native", extension=".htm"))
    assert not writer.accepts(
        html_document,
        TargetInfo(format="xml", extension=".xml"),
    )
    assert not writer.accepts(
        json_document,
        TargetInfo(format="html", extension=".html"),
    )


def test_html_patch_writer_requires_source_stream_and_edits() -> None:
    writer = HtmlPatchWriter()
    document = read_html_ir(
        BytesIO(b"<html><body>x</body></html>"), filename="page.html"
    )

    with pytest.raises(TypeError, match="source_stream=.*edits="):
        writer.write(document, BytesIO(), TargetInfo(format="html"))


def test_html_patch_writer_rejects_unknown_options() -> None:
    writer = HtmlPatchWriter()
    source = b"<html><body>x</body></html>"
    document = read_html_ir(BytesIO(source), filename="page.html")

    with pytest.raises(TypeError, match="unexpected HTML writer options"):
        writer.write(
            document,
            BytesIO(),
            TargetInfo(format="html"),
            source_stream=BytesIO(source),
            edits=(),
            surprise=True,
        )
