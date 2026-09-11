import importlib
import sys


def test_public_namespace_exports_stable_core_contracts_without_registry_internals():
    tw = importlib.import_module("markitdown.twoways")
    public = {
        "DocumentIR",
        "Canvas",
        "Node",
        "TextPayload",
        "ImagePayload",
        "TablePayload",
        "ChartPayload",
        "UnknownNativePayload",
        "Geometry",
        "Style",
        "Provenance",
        "NativeLocator",
        "Resource",
        "Relationship",
        "NativePayload",
        "EditOperation",
        "DocumentIRReader",
        "DocumentWriter",
        "TargetInfo",
        "WriterResult",
        "FidelityReport",
        "FidelityEvidence",
        "TwoWayError",
        "IRValidationError",
        "validate_document",
        "canonical_json_bytes",
        "canonical_json_digest",
        "decode_document",
        "CapabilityState",
        "CapabilityDecision",
        "NodeCapabilityProfile",
        "CapabilityReasonSummary",
        "CapabilityReport",
        "capabilities_for_node",
        "build_capability_report",
    }
    for name in public:
        assert hasattr(tw, name), name
        assert name in tw.__all__, name
    assert not hasattr(tw, "PriorityRegistry")
    assert not hasattr(tw, "Registration")
    assert len(tw.__all__) == len(set(tw.__all__))


def test_twoways_import_does_not_load_python_pptx():
    sys.modules.pop("pptx", None)
    tw = importlib.import_module("markitdown.twoways")
    importlib.reload(tw)
    assert "pptx" not in sys.modules
