from __future__ import annotations

import codecs
from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError, UnsupportedEditError
from markitdown.twoways.formats.xml import writer as xml_writer
from markitdown.twoways.formats.xml.reader import read_xml_ir
from markitdown.twoways.formats.xml.writer import patch_xml
from markitdown.twoways.ir.edits import EditOperation


def _node(document, path):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("xml.path") == path
    )


def _edit(document, path, value) -> EditOperation:
    node = _node(document, path)
    return EditOperation(
        operation_id="edit-1",
        type=(
            "replace_xml_attribute"
            if node.metadata.get("xml.kind") == "attribute"
            else "replace_xml_text"
        ),
        target_node_id=node.node_id,
        payload={"value": value},
    )


def test_utf8_bom_is_preserved_by_target_only_patch() -> None:
    source = (
        codecs.BOM_UTF8
        + '<?xml version="1.0" encoding="UTF-8"?><r a="keep"><name>Ada</name></r>\r\n'.encode(
            "utf-8"
        )
    )
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    patch_xml(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "/r[1]/name[1]/#text[1]", "Grace"),),
    )

    assert output.getvalue() == (
        codecs.BOM_UTF8
        + '<?xml version="1.0" encoding="UTF-8"?><r a="keep"><name>Grace</name></r>\r\n'.encode(
            "utf-8"
        )
    )


@pytest.mark.parametrize(
    ("bom", "encoding"),
    [
        (codecs.BOM_UTF16_LE, "utf-16-le"),
        (codecs.BOM_UTF16_BE, "utf-16-be"),
    ],
)
def test_utf16_bom_and_endianness_are_preserved(bom, encoding) -> None:
    text = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<r a="keep"><name>André</name><keep>東京</keep></r>\r\n'
    )
    source = bom + text.encode(encoding)
    document = read_xml_ir(BytesIO(source), filename="data.xml")
    output = BytesIO()

    patch_xml(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "/r[1]/name[1]/#text[1]", "Grace"),),
    )

    expected_text = text.replace("André", "Grace")
    assert output.getvalue() == bom + expected_text.encode(encoding)


def test_reversible_legacy_encoding_and_declaration_are_preserved() -> None:
    text = (
        '<?xml version="1.0" encoding="windows-1252"?>'
        '<r city="Paris"><name>André</name></r>\r\n'
    )
    source = text.encode("cp1252")
    document = read_xml_ir(
        BytesIO(source),
        filename="data.xml",
        encoding="cp1252",
    )
    output = BytesIO()

    patch_xml(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "/r[1]/@city", "Lyon"),),
    )

    assert output.getvalue() == text.replace("Paris", "Lyon").encode("cp1252")


def test_unencodable_replacement_fails_before_destination_output() -> None:
    text = (
        '<?xml version="1.0" encoding="windows-1252"?>'
        '<r city="Paris"><name>André</name></r>\n'
    )
    source = text.encode("cp1252")
    document = read_xml_ir(
        BytesIO(source),
        filename="data.xml",
        encoding="cp1252",
    )
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="source encoding"):
        patch_xml(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "/r[1]/@city", "東京"),),
        )

    assert output.getvalue() == b""


def test_encoder_leakage_outside_authorized_span_is_rejected(monkeypatch) -> None:
    text = (
        '<?xml version="1.0" encoding="iso-2022-jp"?>'
        "<r><name>A</name><keep>東京</keep></r>\n"
    )
    source = text.encode("iso2022_jp")
    document = read_xml_ir(
        BytesIO(source),
        filename="data.xml",
        encoding="iso2022_jp",
    )
    output = BytesIO()
    real_encode = xml_writer.encode_text_source

    def leaking_encode(candidate_text, representation):
        encoded = real_encode(candidate_text, representation)
        corrupted = bytearray(encoded)
        corrupted[0] = ord("[")
        return bytes(corrupted)

    monkeypatch.setattr(xml_writer, "encode_text_source", leaking_encode)

    with pytest.raises(RoundTripVerificationError, match="outside authorized target"):
        patch_xml(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "/r[1]/name[1]/#text[1]", "日本"),),
        )

    assert output.getvalue() == b""
