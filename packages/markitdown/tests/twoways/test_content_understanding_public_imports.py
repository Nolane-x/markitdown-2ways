from __future__ import annotations

import importlib


def test_h23_symbols_are_public_without_writer_exports() -> None:
    module = importlib.import_module("markitdown.twoways.readers.content_understanding")
    readers = importlib.import_module("markitdown.twoways.readers")
    tw = importlib.import_module("markitdown.twoways")

    for namespace in (module, readers, tw):
        assert hasattr(namespace, "ContentUnderstandingAnalysisSnapshot")
        assert hasattr(namespace, "ContentUnderstandingDerivedLimits")
        assert hasattr(namespace, "read_content_understanding_analysis_ir")

    assert "ContentUnderstandingAnalysisSnapshot" in module.__all__
    assert "ContentUnderstandingDerivedLimits" in module.__all__
    assert "read_content_understanding_analysis_ir" in module.__all__

    for namespace in (readers, tw):
        assert "ContentUnderstandingAnalysisSnapshot" in namespace.__all__
        assert "ContentUnderstandingDerivedLimits" in namespace.__all__
        assert "read_content_understanding_analysis_ir" in namespace.__all__

    for forbidden in (
        "patch_content_understanding",
        "write_content_understanding",
        "ContentUnderstandingWriter",
        "AzureContentUnderstandingWriter",
    ):
        assert not hasattr(module, forbidden)
        assert not hasattr(readers, forbidden)
        assert not hasattr(tw, forbidden)
