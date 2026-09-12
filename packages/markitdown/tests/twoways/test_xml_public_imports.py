from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways.formats.json.reader import read_json_ir
from markitdown.twoways.formats.xml import (
    XmlIRReader,
    XmlPatchWriter,
    patch_xml,
    read_xml_ir,
)
from markitdown.twoways.writers.base import TargetInfo


def test_xml_adapter_public_imports_are_stable() -> None:
    assert XmlIRReader.__name__ == "XmlIRReader"
    assert XmlPatchWriter.__name__ == "XmlPatchWriter"
    assert callable(read_xml_ir)
    assert callable(patch_xml)


def test_xml_patch_writer_accepts_only_xml_backed_xml_targets() -> None:
    writer = XmlPatchWriter()
    xml_document = read_xml_ir(BytesIO(b"<r/>"), filename="data.xml")
    json_document = read_json_ir(BytesIO(b"{}"), filename="data.json")

    assert writer.accepts(xml_document, TargetInfo(format="xml"))
    assert writer.accepts(
        xml_document,
        TargetInfo(format="native", extension=".XML"),
    )
    assert not writer.accepts(
        xml_document, TargetInfo(format="json", extension=".json")
    )
    assert not writer.accepts(json_document, TargetInfo(format="xml", extension=".xml"))


def test_xml_patch_writer_requires_source_stream_and_edits() -> None:
    writer = XmlPatchWriter()
    document = read_xml_ir(BytesIO(b"<r/>"), filename="data.xml")
    target = TargetInfo(format="xml")

    with pytest.raises(TypeError, match="source_stream=.*edits="):
        writer.write(document, BytesIO(), target)


def test_xml_patch_writer_rejects_unknown_options() -> None:
    writer = XmlPatchWriter()
    document = read_xml_ir(BytesIO(b"<r/>"), filename="data.xml")

    with pytest.raises(TypeError, match="unexpected XML writer options"):
        writer.write(
            document,
            BytesIO(),
            TargetInfo(format="xml"),
            source_stream=BytesIO(b"<r/>"),
            edits=(),
            surprise=True,
        )
