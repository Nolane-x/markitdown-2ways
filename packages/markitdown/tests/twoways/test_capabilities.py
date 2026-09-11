import importlib

import pytest


def _public(name):
    tw = importlib.import_module("markitdown.twoways")
    value = getattr(tw, name, None)
    assert value is not None, f"missing public capability contract: {name}"
    return value


def test_edit_capability_is_public_and_copies_constraints():
    EditCapability = _public("EditCapability")
    source = {"native": {"mode": "bounded"}, "limit": 3}

    capability = EditCapability(
        operation="replace_text",
        fidelity="lossless",
        constraints=source,
        reason_code="text.compatible",
    )
    source["limit"] = 9

    assert capability.operation == "replace_text"
    assert capability.fidelity == "lossless"
    assert capability.constraints == {"native": {"mode": "bounded"}, "limit": 3}
    assert capability.reason_code == "text.compatible"


def test_edit_capability_rejects_empty_operation_and_unknown_fidelity():
    EditCapability = _public("EditCapability")

    with pytest.raises(ValueError, match="operation"):
        EditCapability(operation="   ")
    with pytest.raises(ValueError, match="fidelity"):
        EditCapability(operation="replace_text", fidelity="best-effort")


def test_node_stores_capabilities_as_an_immutable_tuple():
    EditCapability = _public("EditCapability")
    Node = _public("Node")
    capabilities = [EditCapability(operation="replace_text")]

    node = Node(node_id="n1", kind="text", capabilities=capabilities)
    capabilities.clear()

    assert isinstance(node.capabilities, tuple)
    assert tuple(item.operation for item in node.capabilities) == ("replace_text",)


def test_capability_coverage_is_deterministic_and_classifies_nodes():
    EditCapability = _public("EditCapability")
    DocumentIR = _public("DocumentIR")
    Node = _public("Node")
    capability_coverage = _public("capability_coverage")

    writable = Node(
        node_id="writable",
        kind="text",
        capabilities=(
            EditCapability(operation="replace_text", fidelity="lossless"),
            EditCapability(operation="set_text_style", fidelity="verified_rewrite"),
        ),
    )
    derived = Node(
        node_id="derived",
        kind="text",
        capabilities=(
            EditCapability(
                operation="replace_text",
                fidelity="derived_read_only",
                reason_code="ocr.derived",
            ),
        ),
    )
    native_read_only = Node(
        node_id="native-ro",
        kind="chart",
        capabilities=(
            EditCapability(
                operation="replace_text",
                fidelity="read_only",
                reason_code="chart.unsupported",
            ),
        ),
    )
    silent_read_only = Node(node_id="silent-ro", kind="unknown_native")

    forward = DocumentIR(
        document_id="doc",
        nodes={
            "writable": writable,
            "derived": derived,
            "native-ro": native_read_only,
            "silent-ro": silent_read_only,
        },
        root_node_ids=("writable", "derived", "native-ro", "silent-ro"),
    )
    reverse = DocumentIR(
        document_id="doc",
        nodes={
            "silent-ro": silent_read_only,
            "native-ro": native_read_only,
            "derived": derived,
            "writable": writable,
        },
        root_node_ids=("writable", "derived", "native-ro", "silent-ro"),
    )

    expected = {
        "total_nodes": 4,
        "writable_nodes": 1,
        "derived_nodes": 1,
        "read_only_nodes": 2,
        "operations": {"replace_text": 3, "set_text_style": 1},
        "reason_codes": {"chart.unsupported": 1, "ocr.derived": 1},
    }
    for document in (forward, reverse):
        report = capability_coverage(document)
        assert {
            "total_nodes": report.total_nodes,
            "writable_nodes": report.writable_nodes,
            "derived_nodes": report.derived_nodes,
            "read_only_nodes": report.read_only_nodes,
            "operations": dict(report.operations),
            "reason_codes": dict(report.reason_codes),
        } == expected


def test_capability_coverage_counts_one_operation_once_per_node():
    EditCapability = _public("EditCapability")
    DocumentIR = _public("DocumentIR")
    Node = _public("Node")
    capability_coverage = _public("capability_coverage")

    node = Node(
        node_id="n1",
        kind="text",
        capabilities=(
            EditCapability(operation="replace_text", fidelity="lossless"),
            EditCapability(
                operation="replace_text",
                fidelity="read_only",
                reason_code="secondary-boundary",
            ),
        ),
    )
    document = DocumentIR(document_id="doc", nodes={"n1": node}, root_node_ids=("n1",))

    report = capability_coverage(document)

    assert dict(report.operations) == {"replace_text": 1}
    assert dict(report.reason_codes) == {"secondary-boundary": 1}
