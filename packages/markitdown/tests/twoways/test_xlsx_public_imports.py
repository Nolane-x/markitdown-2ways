from __future__ import annotations


def test_xlsx_public_surface_exposes_reader_writer_and_options() -> None:
    from markitdown.twoways.formats.xlsx import (
        XlsxIRReader,
        XlsxPatchOptions,
        XlsxPatchWriter,
        patch_xlsx,
        read_xlsx_ir,
    )

    assert XlsxPatchOptions().verify_output is True
    assert XlsxIRReader.__name__ == "XlsxIRReader"
    assert XlsxPatchWriter.__name__ == "XlsxPatchWriter"
    assert callable(read_xlsx_ir)
    assert callable(patch_xlsx)
