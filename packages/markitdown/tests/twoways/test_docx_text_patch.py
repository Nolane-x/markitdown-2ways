from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from markitdown.twoways._errors import UnsupportedEditError
from markitdown.twoways.ooxml import parse_xml_part

from ._docx_fixtures import build_docx_fixture


def _paragraph(index: int):
    data = build_docx_fixture()
    with ZipFile(BytesIO(data)) as archive:
        root = parse_xml_part(archive.read("word/document.xml"))
    return root.xpath(
        '/*[local-name()="document"]/*[local-name()="body"]/*[local-name()="p"]'
    )[index]


def _locator(index: int):
    from markitdown.twoways.formats.docx.locators import paragraph_locator

    return paragraph_locator(
        "/word/document.xml",
        paragraph_index=index,
        path=(
            "/*[local-name()='document']/*[local-name()='body']"
            f"/*[local-name()='p'][{index + 1}]"
        ),
    )


def test_extract_payload_preserves_runs_styles_and_hyperlink_context():
    from markitdown.twoways.formats.docx.text import extract_paragraph_payload

    first = extract_paragraph_payload(_paragraph(0), _locator(0))
    assert first.text == "Revenue 38%"
    assert len(first.paragraphs[0].runs) == 2
    assert first.paragraphs[0].runs[0].style.direct["bold"] is True
    assert first.paragraphs[0].runs[1].style.direct["italic"] is True

    linked = extract_paragraph_payload(_paragraph(1), _locator(1))
    assert linked.text == "Visit OpenAI today"
    contexts = [run.native_locator.attributes["hyperlink_relationship_id"] for run in linked.paragraphs[0].runs]
    assert contexts[0] is None
    assert contexts[1]
    assert contexts[2] is None


def test_patch_formatted_runs_changes_only_text_carrier():
    from lxml import etree

    from markitdown.twoways.formats.docx.text import patch_paragraph_text

    paragraph = _paragraph(0)
    before_rpr = [etree.tostring(item) for item in paragraph.xpath('./*[local-name()="r"]/*[local-name()="rPr"]')]
    patch_paragraph_text(paragraph, old_text="Revenue 38%", new_text="Revenue 42%")
    assert "".join(paragraph.xpath('.//*[local-name()="t"]/text()')) == "Revenue 42%"
    after_rpr = [etree.tostring(item) for item in paragraph.xpath('./*[local-name()="r"]/*[local-name()="rPr"]')]
    assert after_rpr == before_rpr


def test_patch_hyperlink_label_preserves_wrapper_and_relationship():
    from lxml import etree

    from markitdown.twoways.formats.docx.text import patch_paragraph_text

    paragraph = _paragraph(1)
    hyperlink = paragraph.xpath('./*[local-name()="hyperlink"]')[0]
    before = etree.tostring(hyperlink).replace(b"OpenAI", b"")
    relationship_id = hyperlink.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
    patch_paragraph_text(paragraph, old_text="Visit OpenAI today", new_text="Visit OpenUI today")
    hyperlink = paragraph.xpath('./*[local-name()="hyperlink"]')[0]
    assert hyperlink.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id") == relationship_id
    assert "".join(hyperlink.xpath('.//*[local-name()="t"]/text()')) == "OpenUI"
    assert etree.tostring(hyperlink).replace(b"OpenUI", b"") == before


def test_patch_rejects_cross_context_edit():
    from markitdown.twoways.formats.docx.text import patch_paragraph_text

    paragraph = _paragraph(1)
    with pytest.raises(UnsupportedEditError) as exc:
        patch_paragraph_text(paragraph, old_text="Visit OpenAI today", new_text="Visit tomorrow")
    assert exc.value.details["reason"] == "hyperlink_context_boundary"


def test_patch_rejects_field_structure():
    from markitdown.twoways.formats.docx.text import patch_paragraph_text

    paragraph = parse_xml_part(
        b'<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b'<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:t>X</w:t></w:r></w:p>'
    )
    with pytest.raises(UnsupportedEditError):
        patch_paragraph_text(paragraph, old_text="X", new_text="Y")


def test_patch_empty_paragraph_rejects_insert_without_style_context():
    from markitdown.twoways.formats.docx.text import patch_paragraph_text

    paragraph = parse_xml_part(
        b'<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
    )
    with pytest.raises(UnsupportedEditError) as exc:
        patch_paragraph_text(paragraph, old_text="", new_text="new")
    assert exc.value.details["reason"] == "no_style_context"
