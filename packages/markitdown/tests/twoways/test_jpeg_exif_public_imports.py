from __future__ import annotations


def test_jpeg_public_reader_contract_imports() -> None:
    from markitdown.twoways.formats.jpeg import JpegIRReader, JpegLimits, read_jpeg_ir

    assert JpegIRReader is not None
    assert JpegLimits is not None
    assert callable(read_jpeg_ir)
