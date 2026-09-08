from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Iterator, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class Registration(Generic[T]):
    implementation: T
    priority: float = 0.0
    name: str | None = None


class PriorityRegistry(Generic[T]):
    """Instance-owned registry matching MarkItDown converter priority semantics."""

    def __init__(self) -> None:
        self._registrations: list[tuple[int, Registration[T]]] = []
        self._sequence = 0

    @property
    def registrations(self) -> tuple[Registration[T], ...]:
        return tuple(registration for _, registration in self._registrations)

    def register(
        self,
        implementation: T,
        *,
        priority: float = 0.0,
        name: str | None = None,
    ) -> Registration[T]:
        registration = Registration(
            implementation=implementation,
            priority=float(priority),
            name=name,
        )
        self._sequence += 1
        self._registrations.append((self._sequence, registration))
        return registration

    def iter_candidates(self) -> Iterator[Registration[T]]:
        ordered = sorted(
            self._registrations,
            key=lambda item: (item[1].priority, -item[0]),
        )
        for _, registration in ordered:
            yield registration
