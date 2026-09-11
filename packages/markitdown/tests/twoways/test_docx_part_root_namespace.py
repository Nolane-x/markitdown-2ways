from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways.formats.docx._reader_parts import _build_part

_TRANSITIONAL_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_STRICT_W_NS = "http://purl.oclc.org/ooxml/wordprocessingml/main"


def _source(part_uri: str, xml: bytes) -> tuple[bytes, dict[str, bytes]]:
    member_name = part_uri.lstrip("/")
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr(member_name, xml)
    return output.getvalue(), {member_name: xml}


@pytest.mark.parametrize(
    ("kind", "part_uri", "root_name"),
    [
        ("document", "/word/document.xml", "document"),
        ("header", "/word/header1.xml", "hdr"),
        ("footer", "/word/footer1.xml", "ftr"),
    ],
)
def test_build_part_rejects_foreign_wordprocessing_root_namespace(
    kind: str,
    part_uri: str,
    root_name: str,
):
    body = "<x:body/>" if kind == "document" else ""
    xml = (f'<x:{root_name} xmlns:x="urn:not-word">{body}</x:{root_name}>').encode(
        "utf-8"
    )
    source_bytes, members = _source(part_uri, xml)

    with pytest.raises(ValueError, match="WordprocessingML root"):
        _build_part(
            source_bytes=source_bytes,
            members=members,
            part_uri=part_uri,
            kind=kind,
            canvas_index=0,
            ordinal=0,
            relationship_id=None,
        )


@pytest.mark.parametrize("namespace", [_TRANSITIONAL_W_NS, _STRICT_W_NS])
def test_build_part_accepts_known_wordprocessing_document_namespaces(
    namespace: str,
):
    xml = (f'<w:document xmlns:w="{namespace}"><w:body/></w:document>').encode("utf-8")
    source_bytes, members = _source("/word/document.xml", xml)

    canvas, nodes, resources, diagnostics = _build_part(
        source_bytes=source_bytes,
        members=members,
        part_uri="/word/document.xml",
        kind="document",
        canvas_index=0,
        ordinal=0,
        relationship_id=None,
    )

    assert canvas.kind == "document"
    assert nodes == {}
    assert resources == {}
    assert diagnostics == []


def test_build_part_rejects_foreign_document_body_namespace():
    xml = (
        f'<w:document xmlns:w="{_TRANSITIONAL_W_NS}" xmlns:x="urn:not-word">'
        "<x:body/>"
        "</w:document>"
    ).encode("utf-8")
    source_bytes, members = _source("/word/document.xml", xml)

    with pytest.raises(ValueError, match="body namespace"):
        _build_part(
            source_bytes=source_bytes,
            members=members,
            part_uri="/word/document.xml",
            kind="document",
            canvas_index=0,
            ordinal=0,
            relationship_id=None,
        )


def test_build_part_rejects_foreign_core_block_namespace():
    xml = (
        f'<w:document xmlns:w="{_TRANSITIONAL_W_NS}" xmlns:x="urn:not-word">'
        "<w:body><x:p/></w:body>"
        "</w:document>"
    ).encode("utf-8")
    source_bytes, members = _source("/word/document.xml", xml)

    with pytest.raises(ValueError, match="block namespace"):
        _build_part(
            source_bytes=source_bytes,
            members=members,
            part_uri="/word/document.xml",
            kind="document",
            canvas_index=0,
            ordinal=0,
            relationship_id=None,
        )


def test_build_part_ignores_foreign_non_core_extension_block():
    xml = (
        f'<w:document xmlns:w="{_TRANSITIONAL_W_NS}" xmlns:x="urn:not-word">'
        "<w:body><x:extension/></w:body>"
        "</w:document>"
    ).encode("utf-8")
    source_bytes, members = _source("/word/document.xml", xml)

    canvas, nodes, resources, diagnostics = _build_part(
        source_bytes=source_bytes,
        members=members,
        part_uri="/word/document.xml",
        kind="document",
        canvas_index=0,
        ordinal=0,
        relationship_id=None,
    )

    assert canvas.kind == "document"
    assert nodes == {}
    assert resources == {}
    assert diagnostics == []
