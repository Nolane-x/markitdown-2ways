from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .ir.nodes import Node


CAPABILITY_METADATA_KEY = "twoways.capabilities.v1"


class CapabilityState(str, Enum):
    WRITABLE = "writable"
    READ_ONLY = "read-only"
    DERIVED = "derived"


@dataclass(frozen=True)
class CapabilityDecision:
    operation: str
    state: CapabilityState | str
    reason_code: str | None = None
    constraints: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.operation, str) or not self.operation:
            raise ValueError("capability operation must be a non-empty string")
        try:
            state = (
                self.state
                if isinstance(self.state, CapabilityState)
                else CapabilityState(self.state)
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("capability state is invalid") from exc
        if self.reason_code is not None and not isinstance(self.reason_code, str):
            raise ValueError("capability reason_code must be a string or None")
        if not isinstance(self.constraints, Mapping):
            raise ValueError("capability constraints must be a mapping")
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "constraints", dict(self.constraints))


@dataclass(frozen=True)
class NodeCapabilityProfile:
    node_id: str
    decisions: tuple[CapabilityDecision, ...] = ()
    default_state: CapabilityState = CapabilityState.READ_ONLY

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("node_id must be non-empty")
        object.__setattr__(self, "decisions", tuple(self.decisions))

    def for_operation(self, operation: str) -> CapabilityDecision:
        for decision in self.decisions:
            if decision.operation == operation:
                return decision
        return CapabilityDecision(
            operation=operation,
            state=self.default_state,
            reason_code="capability.unspecified",
        )


def _wire_decision(value: object) -> CapabilityDecision:
    if not isinstance(value, Mapping):
        raise ValueError("capability entry must be a mapping")

    operation = value.get("operation")
    state = value.get("state")
    reason_code = value.get("reason_code")
    constraints = value.get("constraints", {})

    if not isinstance(operation, str) or not operation:
        raise ValueError("capability operation must be a non-empty string")
    if not isinstance(state, str):
        raise ValueError("capability state must be a string")
    if reason_code is not None and not isinstance(reason_code, str):
        raise ValueError("capability reason_code must be a string or None")
    if not isinstance(constraints, Mapping):
        raise ValueError("capability constraints must be a mapping")

    return CapabilityDecision(
        operation=operation,
        state=state,
        reason_code=reason_code,
        constraints=constraints,
    )


def capabilities_for_node(node: Node) -> NodeCapabilityProfile:
    raw = node.metadata.get(CAPABILITY_METADATA_KEY)
    if raw is None:
        return NodeCapabilityProfile(node_id=node.node_id)
    if isinstance(raw, (str, bytes, bytearray)) or not isinstance(raw, Sequence):
        raise ValueError("capability metadata must be a sequence of mappings")

    decisions = tuple(_wire_decision(item) for item in raw)
    operations = [decision.operation for decision in decisions]
    if len(operations) != len(set(operations)):
        raise ValueError("duplicate capability operation")

    return NodeCapabilityProfile(
        node_id=node.node_id,
        decisions=tuple(sorted(decisions, key=lambda item: item.operation)),
    )


def encode_capabilities(
    decisions: Sequence[CapabilityDecision],
) -> tuple[dict[str, Any], ...]:
    operations = [decision.operation for decision in decisions]
    if len(operations) != len(set(operations)):
        raise ValueError("duplicate capability operation")

    encoded: list[dict[str, Any]] = []
    for decision in sorted(decisions, key=lambda item: item.operation):
        item: dict[str, Any] = {
            "operation": decision.operation,
            "state": decision.state.value,
            "constraints": dict(decision.constraints),
        }
        if decision.reason_code is not None:
            item["reason_code"] = decision.reason_code
        encoded.append(item)
    return tuple(encoded)
