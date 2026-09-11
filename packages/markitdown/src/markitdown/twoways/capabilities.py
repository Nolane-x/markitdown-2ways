from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from .ir.document import DocumentIR
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


@dataclass(frozen=True)
class CapabilityReasonSummary:
    reason_code: str
    count: int

    def __post_init__(self) -> None:
        if not self.reason_code:
            raise ValueError("reason_code must be non-empty")
        if self.count < 1:
            raise ValueError("reason summary count must be positive")


@dataclass(frozen=True)
class CapabilityReport:
    total_nodes: int
    writable_nodes: int
    read_only_nodes: int
    derived_nodes: int
    writable_by_operation: Mapping[str, int] = field(default_factory=dict)
    reason_counts: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        counts = (
            self.total_nodes,
            self.writable_nodes,
            self.read_only_nodes,
            self.derived_nodes,
        )
        if any(value < 0 for value in counts):
            raise ValueError("capability report counts must be non-negative")
        if self.writable_nodes + self.read_only_nodes + self.derived_nodes != self.total_nodes:
            raise ValueError("capability report node counts must sum to total_nodes")
        object.__setattr__(
            self,
            "writable_by_operation",
            MappingProxyType(dict(sorted(self.writable_by_operation.items()))),
        )
        object.__setattr__(
            self,
            "reason_counts",
            MappingProxyType(dict(sorted(self.reason_counts.items()))),
        )

    @property
    def reasons(self) -> tuple[CapabilityReasonSummary, ...]:
        return tuple(
            CapabilityReasonSummary(reason_code=code, count=count)
            for code, count in self.reason_counts.items()
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


def build_capability_report(document: DocumentIR) -> CapabilityReport:
    writable_nodes = 0
    read_only_nodes = 0
    derived_nodes = 0
    writable_by_operation: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()

    for node_id in sorted(document.nodes):
        profile = capabilities_for_node(document.nodes[node_id])
        decisions = profile.decisions

        if not decisions:
            read_only_nodes += 1
            reason_counts["capability.unspecified"] += 1
            continue

        states = {decision.state for decision in decisions}
        if CapabilityState.WRITABLE in states:
            writable_nodes += 1
        elif CapabilityState.DERIVED in states:
            derived_nodes += 1
        else:
            read_only_nodes += 1

        for decision in decisions:
            if decision.state is CapabilityState.WRITABLE:
                writable_by_operation[decision.operation] += 1
            if decision.reason_code is not None:
                reason_counts[decision.reason_code] += 1

    return CapabilityReport(
        total_nodes=len(document.nodes),
        writable_nodes=writable_nodes,
        read_only_nodes=read_only_nodes,
        derived_nodes=derived_nodes,
        writable_by_operation=dict(writable_by_operation),
        reason_counts=dict(reason_counts),
    )
