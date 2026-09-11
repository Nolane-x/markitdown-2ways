from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

from ._docx_fixtures import build_docx_fixture


def test_docx_fixture_is_real_office_package():
    data = build_docx_fixture()
    with ZipFile(BytesIO(data)) as archive:
        names = set(archive.namelist())
    assert "word/document.xml" in names
    assert "word/header1.xml" in names
    assert "word/footer1.xml" in names
    assert any(name.startswith("word/media/") for name in names)


def test_docx_public_surface_is_lazy_and_has_options():
    from markitdown.twoways.formats.docx import (
        DocxPatchOptions,
        DocxReadOptions,
        patch_docx,
        read_docx_ir,
    )

    assert DocxReadOptions().include_headers_footers is True
    assert DocxPatchOptions().verify_output is True
    assert callable(read_docx_ir)
    assert callable(patch_docx)


def test_root_import_does_not_eagerly_load_docx_or_lxml():
    import subprocess
    import sys

    code = (
        "import sys; import markitdown.twoways; "
        "print(int('docx' in sys.modules), int('lxml' in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": "packages/markitdown/src"},
    )
    assert result.stdout.strip() == "0 0"
