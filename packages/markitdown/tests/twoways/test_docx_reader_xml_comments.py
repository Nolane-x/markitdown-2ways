from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile, ZipInfo

from markitdown.twoways.ooxml import parse_xml_part, serialize_xml_part

from ._docx_fixtures import build_docx_fixture


def _with_xml_comments(source: bytes) -> bytes:
    from lxml import etree

    output = BytesIO()
    with ZipFile(BytesIO(source), "r") as original, ZipFile(output, "w") as target:
        for info in original.infolist():
            data = original.read(info)
            if info.filename in {
                "[Content_Types].xml",
                "docProps/core.xml",
                "word/document.xml",
            }:
                root = parse_xml_part(data)
                comment = etree.Comment("markitdown-2ways compatibility comment")
                if info.filename == "word/document.xml":
                    body = root.xpath('./*[local-name()="body"]')[0]
                    body.insert(0, comment)
                else:
                    root.insert(0, comment)
                data = serialize_xml_part(root)
            clone = ZipInfo(info.filename, info.date_time)
            clone.compress_type = info.compress_type
            clone.external_attr = info.external_attr
            clone.internal_attr = info.internal_attr
            clone.extra = info.extra
            clone.comment = info.comment
            target.writestr(clone, data)
    return output.getvalue()


def test_docx_reader_accepts_xml_comments_in_metadata_and_body():
    from markitdown.twoways.formats.docx import read_docx_ir

    document = read_docx_ir(BytesIO(_with_xml_comments(build_docx_fixture())))

    assert document.metadata.title == "MarkItDown 2Ways DOCX Fixture"
    body = document.canvases[0]
    first = document.nodes[body.root_node_ids[0]]
    assert first.payload.text == "Revenue 38%"
