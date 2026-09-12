from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


INITIAL_EDIT_TYPES = frozenset(
    {
        "replace_text",
        "set_text_style",
        "move_resize",
        "replace_resource",
        "set_alt_text",
        "update_table_cells",
        "update_sheet_cells",
        "update_csv_cells",
        "add_node",
        "remove_node",
    }
)


@dataclass(frozen=True)
class EditPrecondition:
    expected_semantic_digest: str | None = None
    expected_native_locator_digest: str | None = None
    expected_old_value: Any = None


@dataclass(frozen=True)
class EditOperation:
    operation_id: str
    type: str
    target_node_id: str | None = None
    precondition: EditPrecondition | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    source_label: str | None = None

    def __post_init__(self) -> None:
        if not self.operation_id:
            raise ValueError("operation_id must be non-empty")
        if not self.type:
            raise ValueError("type must be non-empty")
        object.__setattr__(self, "payload", dict(self.payload))
