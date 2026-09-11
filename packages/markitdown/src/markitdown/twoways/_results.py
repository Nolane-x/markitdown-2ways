from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class FidelityStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not-applicable"


FIDELITY_TIERS = frozenset(
    {
        "exact-preserve",
        "high",
        "semantic",
        "reconstructed",
        "unknown",
    }
)


@dataclass(frozen=True)
class FidelityEvidence:
    check_code: str
    status: FidelityStatus | str
    description: str
    expected: Any = None
    actual: Any = None
    affected_node_ids: tuple[str, ...] = ()
    required: bool = True

    def __post_init__(self) -> None:
        if not self.check_code:
            raise ValueError("check_code must be non-empty")
        status = (
            self.status
            if isinstance(self.status, FidelityStatus)
            else FidelityStatus(self.status)
        )
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "affected_node_ids", tuple(self.affected_node_ids))


@dataclass(frozen=True)
class FidelityReport:
    claimed_tier: str = "unknown"
    evidence: tuple[FidelityEvidence, ...] = ()
    unsupported_features: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.claimed_tier not in FIDELITY_TIERS:
            raise ValueError(f"unsupported fidelity tier: {self.claimed_tier}")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(
            self, "unsupported_features", tuple(self.unsupported_features)
        )
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if self.claimed_tier == "exact-preserve":
            failed_required = [
                item.check_code
                for item in self.evidence
                if item.required and item.status is FidelityStatus.FAILED
            ]
            if failed_required:
                raise ValueError(
                    "exact-preserve fidelity cannot be claimed with failed required evidence: "
                    + ", ".join(failed_required)
                )


@dataclass(frozen=True)
class WriterResult:
    format: str
    mode: str
    bytes_written: int
    fidelity: FidelityReport = field(default_factory=FidelityReport)
    warnings: tuple[str, ...] = ()
    unsupported_operations: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.format:
            raise ValueError("format must be non-empty")
        if not self.mode:
            raise ValueError("mode must be non-empty")
        if self.bytes_written < 0:
            raise ValueError("bytes_written must be non-negative")
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(
            self, "unsupported_operations", tuple(self.unsupported_operations)
        )
        object.__setattr__(self, "metadata", dict(self.metadata))
