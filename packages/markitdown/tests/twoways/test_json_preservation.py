from __future__ import annotations

import codecs
from io import BytesIO

import pytest

from markitdown.twoways._errors import RoundTripVerificationError, UnsupportedEditError
from markitdown.twoways.formats.json import writer as json_writer
from markitdown.twoways.formats.json.reader import read_json_ir
from markitdown.twoways.formats.json.writer import patch_json
from markitdown.twoways.ir.edits import EditOperation


def _node(document, pointer):
    return next(
        node
        for node in document.nodes.values()
        if node.metadata.get("json.pointer") == pointer
    )


def _edit(document, pointer, value) -> EditOperation:
    return EditOperation(
        operation_id="edit-1",
        type="replace_json_scalar",
        target_node_id=_node(document, pointer).node_id,
        payload={"value": value},
    )


def test_utf8_bom_is_preserved_by_target_only_patch() -> None:
    source = codecs.BOM_UTF8 + b'{"name":"Ada", "keep":1}\r\n'
    document = read_json_ir(BytesIO(source), filename="data.json")
    output = BytesIO()

    patch_json(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "/name", "Grace"),),
    )

    assert output.getvalue() == codecs.BOM_UTF8 + b'{"name":"Grace", "keep":1}\r\n'


@pytest.mark.parametrize(
    ("bom", "encoding"),
    [
        (codecs.BOM_UTF16_LE, "utf-16-le"),
        (codecs.BOM_UTF16_BE, "utf-16-be"),
    ],
)
def test_utf16_bom_and_endianness_are_preserved(bom, encoding) -> None:
    source = bom + '{"name":"André", "keep":[1,2]}\r\n'.encode(encoding)
    document = read_json_ir(BytesIO(source), filename="data.json")
    output = BytesIO()

    patch_json(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "/name", "Grace"),),
    )

    expected = bom + '{"name":"Grace", "keep":[1,2]}\r\n'.encode(encoding)
    assert output.getvalue() == expected


def test_reversible_legacy_encoding_is_preserved() -> None:
    source = '{"name":"André", "city":"Paris"}\r\n'.encode("cp1252")
    document = read_json_ir(
        BytesIO(source),
        filename="data.json",
        encoding="cp1252",
    )
    output = BytesIO()

    patch_json(
        document,
        BytesIO(source),
        output,
        edits=(_edit(document, "/city", "Lyon"),),
    )

    assert output.getvalue() == '{"name":"André", "city":"Lyon"}\r\n'.encode("cp1252")


def test_unencodable_replacement_fails_before_destination_output() -> None:
    source = '{"name":"André", "city":"Paris"}\n'.encode("cp1252")
    document = read_json_ir(
        BytesIO(source),
        filename="data.json",
        encoding="cp1252",
    )
    output = BytesIO()

    with pytest.raises(UnsupportedEditError, match="source encoding"):
        patch_json(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "/city", "東京"),),
        )

    assert output.getvalue() == b""


def test_encoder_leakage_outside_authorized_span_is_rejected(monkeypatch) -> None:
    source = '{"name":"A", "keep":"東京"}\n'.encode("iso2022_jp")
    document = read_json_ir(
        BytesIO(source),
        filename="data.json",
        encoding="iso2022_jp",
    )
    output = BytesIO()
    real_encode = json_writer.encode_text_source
    calls = 0

    def leaking_encode(text, representation):
        nonlocal calls
        calls += 1
        encoded = real_encode(text, representation)
        if calls == 2:
            corrupted = bytearray(encoded)
            corrupted[0] = ord("[")
            return bytes(corrupted)
        return encoded

    monkeypatch.setattr(json_writer, "encode_text_source", leaking_encode)

    with pytest.raises(RoundTripVerificationError, match="outside authorized target"):
        patch_json(
            document,
            BytesIO(source),
            output,
            edits=(_edit(document, "/name", "日本"),),
        )

    assert output.getvalue() == b""
