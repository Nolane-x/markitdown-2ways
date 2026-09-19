from __future__ import annotations

import importlib

from markitdown.twoways.formats.xlsx.reader import read_xlsx_ir
from markitdown.twoways.formats.xlsx.writer import patch_xlsx


def test_h29_symbols_are_public_without_writer_exports() -> None:
    module = importlib.import_module("markitdown.twoways.readers.xlsx_converter")
    readers = importlib.import_module("markitdown.twoways.readers")
    tw = importlib.import_module("markitdown.twoways")

    expected = (
        "XlsxSheetMarkdownSnapshot",
        "XlsxConverterSnapshot",
        "XlsxDerivedLimits",
        "read_xlsx_converter_snapshot_ir",
    )
    for namespace in (module, readers, tw):
        for symbol in expected:
            assert hasattr(namespace, symbol)

    for symbol in expected:
        assert symbol in module.__all__
        assert symbol in readers.__all__
        assert symbol in tw.__all__

    for forbidden in (
        "patch_xlsx_converter_snapshot",
        "write_xlsx_converter_snapshot",
        "XlsxConverterDerivedWriter",
    ):
        assert not hasattr(module, forbidden)
        assert not hasattr(readers, forbidden)
        assert not hasattr(tw, forbidden)


def test_native_xlsx_authority_remains_separate_and_importable() -> None:
    assert callable(read_xlsx_ir)
    assert callable(patch_xlsx)
