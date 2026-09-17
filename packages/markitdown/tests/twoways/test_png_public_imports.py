from __future__ import annotations


def test_png_public_contract_imports() -> None:
    from markitdown.twoways.formats.png import (
        PngIRReader,
        PngLimits,
        PngPatchWriter,
        patch_png,
        read_png_ir,
    )

    assert PngIRReader is not None
    assert PngLimits is not None
    assert PngPatchWriter is not None
    assert callable(patch_png)
    assert callable(read_png_ir)
