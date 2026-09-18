from __future__ import annotations

import importlib


def test_h22_symbols_are_public_without_writer_exports() -> None:
    module = importlib.import_module("markitdown.twoways.readers.document_intelligence")
    readers = importlib.import_module("markitdown.twoways.readers")
    tw = importlib.import_module("markitdown.twoways")

    for namespace in (module, readers, tw):
        assert hasattr(namespace, "DocumentIntelligenceAnalysisSnapshot")
        assert hasattr(namespace, "DocumentIntelligenceDerivedLimits")
        assert hasattr(namespace, "read_document_intelligence_analysis_ir")

    assert "DocumentIntelligenceAnalysisSnapshot" in module.__all__
    assert "DocumentIntelligenceDerivedLimits" in module.__all__
    assert "read_document_intelligence_analysis_ir" in module.__all__

    for namespace in (readers, tw):
        assert "DocumentIntelligenceAnalysisSnapshot" in namespace.__all__
        assert "DocumentIntelligenceDerivedLimits" in namespace.__all__
        assert "read_document_intelligence_analysis_ir" in namespace.__all__

    for forbidden in (
        "patch_document_intelligence",
        "write_document_intelligence",
        "DocumentIntelligenceWriter",
        "AzureDocumentIntelligenceWriter",
    ):
        assert not hasattr(module, forbidden)
        assert not hasattr(readers, forbidden)
        assert not hasattr(tw, forbidden)
