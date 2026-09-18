from __future__ import annotations

import importlib


def test_h27_symbols_are_public_without_writer_exports() -> None:
    module = importlib.import_module("markitdown.twoways.readers.pdf_converter")
    readers = importlib.import_module("markitdown.twoways.readers")
    tw = importlib.import_module("markitdown.twoways")

    for namespace in (module, readers, tw):
        assert hasattr(namespace, "PdfConverterExtractionSnapshot")
        assert hasattr(namespace, "PdfDerivedLimits")
        assert hasattr(namespace, "read_pdf_converter_snapshot_ir")

    assert "PdfConverterExtractionSnapshot" in module.__all__
    assert "PdfDerivedLimits" in module.__all__
    assert "read_pdf_converter_snapshot_ir" in module.__all__

    for namespace in (readers, tw):
        assert "PdfConverterExtractionSnapshot" in namespace.__all__
        assert "PdfDerivedLimits" in namespace.__all__
        assert "read_pdf_converter_snapshot_ir" in namespace.__all__

    for forbidden in (
        "patch_pdf_converter_snapshot",
        "write_pdf_converter_snapshot",
        "PdfConverterDerivedWriter",
    ):
        assert not hasattr(module, forbidden)
        assert not hasattr(readers, forbidden)
        assert not hasattr(tw, forbidden)
