from __future__ import annotations

import json
from pathlib import Path

import pytest

from markitdown.twoways import (
    CapabilityDecision,
    CapabilityState,
    DocumentIR,
    Node,
    NodeCapabilityProfile,
    build_capability_report,
    capabilities_for_node,
)
from markitdown.twoways.capabilities import CAPABILITY_METADATA_KEY


_REPO_ROOT = Path(__file__).resolve().parents[4]
_CONTRACT_PATH = _REPO_ROOT / "docs" / "twoways-v1-contract.json"

_STRUCTURAL_MUTATIONS = {
    "add_node",
    "remove_node",
    "replace_resource",
}


def _contract() -> dict[str, object]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def test_capability_constraints_are_detached_and_immutable() -> None:
    source = {"max_bytes": 64}
    decision = CapabilityDecision(
        operation="replace_text",
        state=CapabilityState.WRITABLE,
        constraints=source,
    )

    source["max_bytes"] = 128
    assert decision.constraints["max_bytes"] == 64

    with pytest.raises(TypeError):
        decision.constraints["max_bytes"] = 256  # type: ignore[index]


@pytest.mark.parametrize(
    "default_state",
    ["write", "WRITABLE", "", object()],
)
def test_profile_rejects_unknown_default_states(default_state: object) -> None:
    with pytest.raises(ValueError, match="default_state"):
        NodeCapabilityProfile(
            node_id="node-1",
            default_state=default_state,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "wire_value",
    [
        "writable",
        b"writable",
        bytearray(b"writable"),
        {"operation": "replace_text", "state": "writable"},
        [None],
        [{"operation": "", "state": "writable"}],
        [{"operation": "replace_text", "state": "write"}],
        [{"operation": "replace_text", "state": "writable", "constraints": []}],
    ],
)
def test_malformed_capability_wire_fails_closed(wire_value: object) -> None:
    node = Node(
        node_id="node-1",
        kind="text",
        metadata={CAPABILITY_METADATA_KEY: wire_value},
    )
    with pytest.raises(ValueError):
        capabilities_for_node(node)


def test_duplicate_wire_operations_fail_closed() -> None:
    node = Node(
        node_id="node-1",
        kind="text",
        metadata={
            CAPABILITY_METADATA_KEY: [
                {"operation": "replace_text", "state": "writable"},
                {"operation": "replace_text", "state": "read-only"},
            ]
        },
    )
    with pytest.raises(ValueError, match="duplicate"):
        capabilities_for_node(node)


def test_unspecified_operation_never_inherits_writable_authority() -> None:
    profile = NodeCapabilityProfile(
        node_id="node-1",
        decisions=(
            CapabilityDecision(
                operation="replace_text",
                state=CapabilityState.WRITABLE,
            ),
        ),
    )

    fallback = profile.for_operation("remove_node")
    assert fallback.state is CapabilityState.READ_ONLY
    assert fallback.reason_code == "capability.unspecified"


def test_empty_capability_metadata_reports_read_only() -> None:
    document = DocumentIR(
        document_id="doc-1",
        nodes={"node-1": Node(node_id="node-1", kind="text")},
    )

    report = build_capability_report(document)
    assert report.total_nodes == 1
    assert report.writable_nodes == 0
    assert report.read_only_nodes == 1
    assert report.derived_nodes == 0
    assert report.reason_counts["capability.unspecified"] == 1


def test_v1_contract_never_grants_direct_structural_mutation() -> None:
    contract = _contract()
    rows = contract["native_support"]
    assert isinstance(rows, list)

    operations = {
        operation for row in rows for operation in row["direct_operations"]
    }
    assert operations.isdisjoint(_STRUCTURAL_MUTATIONS)


def test_v1_derived_surfaces_are_uniformly_non_writeback() -> None:
    contract = _contract()
    rows = contract["derived_support"]
    assert isinstance(rows, list)
    assert rows

    assert {(row["state"], row["native_writeback"]) for row in rows} == {
        ("derived", False)
    }
