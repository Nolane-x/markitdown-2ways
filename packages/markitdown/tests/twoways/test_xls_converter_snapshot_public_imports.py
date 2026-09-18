from __future__ import annotations

import importlib


def test_h28_symbols_are_public_without_writer_exports() -> None:
    module = importlib.import_module("markitdown.twoways.readers.xls_converter")
    readers = importlib.import_module("markitdown.twoways.readers")
    tw = importlib.import_module("markitdown.twoways")

    expected = (
        "XlsSheetMarkdownSnapshot",
        "XlsConverterSnapshot",
        "XlsDerivedLimits",
        "read_xls_converter_snapshot_ir",
    )
    for namespace in (module, readers, tw):
        for symbol in expected:
            assert hasattr(namespace, symbol)

    for symbol in expected:
        assert symbol in module.__all__
        assert symbol in readers.__all__
        assert symbol in tw.__all__

    for forbidden in (
        "patch_xls_converter_snapshot",
        "write_xls_converter_snapshot",
        "XlsConverterDerivedWriter",
    ):
        assert not hasattr(module, forbidden)
        assert not hasattr(readers, forbidden)
        assert not hasattr(tw, forbidden)
