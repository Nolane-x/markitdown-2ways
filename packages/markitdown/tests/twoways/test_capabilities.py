from __future__ import annotations

import pytest

from markitdown.twoways.capabilities import (
    CAPABILITY_METADATA_KEY,
    CapabilityDecision,
    CapabilityState,
    capabilities_for_node,
    encode_capabilities,
)
from markitdown.twoways.ir.nodes import Node


def test_missing_capability_metadata_defaults_to_read_only() -> None:
    profile = capabilities_for_node(Node(node_id="n1", kind="text"))

    assert profile.node_id == "n1"
    assert profile.decisions == ()
    assert profile.default_state is CapabilityState.READ_ONLY


def test_capability_metadata_is_sorted_by_operation() -> None:
    node = Node(
        node_id="n1",
        kind="text",
        metadata={
            CAPABILITY_METADATA_KEY: [
                {
                    "operation": "set_text_style",
                    "state": "read-only",
                    "reason_code": "text.style.unsupported",
                },
                {"operation": "replace_text", "state": "writable"},
            ]
        },
    )

    profile = capabilities_for_node(node)

    assert [item.operation for item in profile.decisions] == [
        "replace_text",
        "set_text_style",
    ]
    assert profile.decisions[0].state is CapabilityState.WRITABLE
    assert profile.decisions[1].state is CapabilityState.READ_ONLY


def test_encode_capabilities_emits_deterministic_plain_wire_values() -> None:
    encoded = encode_capabilities(
        (
            CapabilityDecision(
                operation="set_alt_text",
                state=CapabilityState.READ_ONLY,
                reason_code="image.alt.unsupported",
                constraints={"preservation": "resource"},
            ),
            CapabilityDecision(
                operation="replace_text",
                state=CapabilityState.WRITABLE,
                constraints={"identity_markdown": True},
            ),
        )
    )

    assert encoded == (
        {
            "operation": "replace_text",
            "state": "writable",
            "constraints": {"identity_markdown": True},
        },
        {
            "operation": "set_alt_text",
            "state": "read-only",
            "reason_code": "image.alt.unsupported",
            "constraints": {"preservation": "resource"},
        },
    )


def test_duplicate_capability_operations_are_rejected() -> None:
    node = Node(
        node_id="n1",
        kind="text",
        metadata={
            CAPABILITY_METADATA_KEY: [
                {"operation": "replace_text", "state": "writable"},
                {
                    "operation": "replace_text",
                    "state": "read-only",
                    "reason_code": "duplicate",
                },
            ]
        },
    )

    with pytest.raises(ValueError, match="duplicate capability operation"):
        capabilities_for_node(node)


@pytest.mark.parametrize(
    ("wire_value", "message"),
    [
        ("replace_text", "sequence"),
        ([{"operation": "", "state": "writable"}], "operation"),
        ([{"operation": "replace_text", "state": "maybe"}], "state"),
        (
            [
                {
                    "operation": "replace_text",
                    "state": "read-only",
                    "reason_code": 3,
                }
            ],
            "reason_code",
        ),
        (
            [
                {
                    "operation": "replace_text",
                    "state": "writable",
                    "constraints": ["not", "a", "mapping"],
                }
            ],
            "constraints",
        ),
    ],
)
def test_malformed_capability_metadata_is_rejected(
    wire_value: object, message: str
) -> None:
    node = Node(
        node_id="n1",
        kind="text",
        metadata={CAPABILITY_METADATA_KEY: wire_value},
    )

    with pytest.raises(ValueError, match=message):
        capabilities_for_node(node)
