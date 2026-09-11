from __future__ import annotations

import pytest

from markitdown.twoways._errors import UnsupportedEditError
from markitdown.twoways.ooxml import parse_xml_part

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


@pytest.mark.parametrize(
    "xml",
    [
        (f'<w:p xmlns:w="{_W_NS}">' "<w:pPr/><w:pPr/>" "<w:r><w:t>X</w:t></w:r></w:p>"),
        (f'<w:p xmlns:w="{_W_NS}">' "<w:r><w:rPr/><w:rPr/><w:t>X</w:t></w:r></w:p>"),
    ],
)
def test_patch_rejects_duplicate_property_containers(xml: str):
    from markitdown.twoways.formats.docx.text import patch_paragraph_text

    paragraph = parse_xml_part(xml.encode("utf-8"))
    with pytest.raises(UnsupportedEditError) as exc:
        patch_paragraph_text(paragraph, old_text="X", new_text="Y")

    assert exc.value.details["reason"] == "unsupported_text_structure"
