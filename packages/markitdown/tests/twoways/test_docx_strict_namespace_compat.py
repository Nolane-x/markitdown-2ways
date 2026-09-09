from __future__ import annotations

from markitdown.twoways.formats.docx.locators import paragraph_locator
from markitdown.twoways.formats.docx.structures import _picture_relationship_id
from markitdown.twoways.formats.docx.text import extract_paragraph_payload
from markitdown.twoways.ooxml import parse_xml_part

_STRICT_W_NS = "http://purl.oclc.org/ooxml/wordprocessingml/main"
_STRICT_R_NS = "http://purl.oclc.org/ooxml/officeDocument/relationships"


def _locator():
    return paragraph_locator(
        "/word/document.xml",
        paragraph_index=0,
        path="/*[local-name()='document']/*[local-name()='body']/*[local-name()='p'][1]",
    )


def test_strict_wordprocessingml_style_attributes_are_preserved():
    paragraph = parse_xml_part(
        (
            f'<w:p xmlns:w="{_STRICT_W_NS}">'
            '<w:r><w:rPr><w:b w:val="0"/><w:u w:val="double"/>'
            '<w:sz w:val="24"/></w:rPr><w:t>X</w:t></w:r></w:p>'
        ).encode("utf-8")
    )

    payload = extract_paragraph_payload(paragraph, _locator())
    style = payload.paragraphs[0].runs[0].style

    assert style is not None
    assert style.direct["bold"] is False
    assert style.direct["underline"] == "double"
    assert style.direct["font_size_pt"] == 12.0


def test_strict_hyperlink_relationship_id_is_preserved():
    paragraph = parse_xml_part(
        (
            f'<w:p xmlns:w="{_STRICT_W_NS}" xmlns:r="{_STRICT_R_NS}">'
            '<w:hyperlink r:id="rId5"><w:r><w:t>X</w:t></w:r></w:hyperlink>'
            "</w:p>"
        ).encode("utf-8")
    )

    payload = extract_paragraph_payload(paragraph, _locator())
    run = payload.paragraphs[0].runs[0]

    assert run.native_locator is not None
    assert run.native_locator.relationship_id == "rId5"


def test_strict_picture_relationship_id_is_preserved():
    inline = parse_xml_part(
        (
            '<wp:inline xmlns:wp="urn:wp" xmlns:a="urn:a" '
            f'xmlns:r="{_STRICT_R_NS}">'
            '<wp:docPr id="1"/><a:graphic><a:blip r:embed="rId9"/></a:graphic>'
            "</wp:inline>"
        ).encode("utf-8")
    )
    docpr = inline.xpath('.//*[local-name()="docPr"]')[0]

    assert _picture_relationship_id(docpr) == "rId9"
