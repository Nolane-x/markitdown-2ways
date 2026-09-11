from __future__ import annotations

import pytest

from markitdown.twoways.ooxml import parse_xml_part

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


@pytest.mark.parametrize(
    "xml",
    [
        (f'<w:p xmlns:w="{_W_NS}"><!--keep-->' "<w:r><w:t>X</w:t></w:r></w:p>"),
        (f'<w:p xmlns:w="{_W_NS}"><w:r><!--keep-->' "<w:t>X</w:t></w:r></w:p>"),
        (
            f'<w:p xmlns:w="{_W_NS}" xmlns:r="{_R_NS}">'
            '<w:hyperlink r:id="rId1"><!--keep-->'
            "<w:r><w:t>X</w:t></w:r></w:hyperlink></w:p>"
        ),
    ],
)
def test_patch_ignores_xml_comments_inside_text_carriers(xml: str):
    from lxml import etree

    from markitdown.twoways.formats.docx.text import patch_paragraph_text

    paragraph = parse_xml_part(xml.encode("utf-8"))
    patch_paragraph_text(paragraph, old_text="X", new_text="Y")

    assert "".join(paragraph.xpath('.//*[local-name()="t"]/text()')) == "Y"
    assert b"<!--keep-->" in etree.tostring(paragraph)
