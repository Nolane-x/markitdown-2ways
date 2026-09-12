from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
import re
from typing import Any

from .._errors import PatchPreconditionError, UnsupportedEditError
from .nodes import TextPayload, TextRun


SUPPORTED_TEXT_STYLE_FIELDS = frozenset(
    {
        "bold",
        "italic",
        "underline",
        "font_size_pt",
        "font_family",
        "color",
    }
)

_PORTABLE_UNDERLINE_VALUES = frozenset({"none", "single", "double"})
_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _fail_payload(message: str, *, reason: str = "invalid_edit_payload") -> None:
    raise UnsupportedEditError(message, details={"reason": reason})


def _canonical_style_value(field: str, value: object, *, allow_clear: bool) -> object:
    if value is None:
        if allow_clear:
            return None
        _fail_payload(
            "Text style source values cannot be null.",
            reason="invalid_style_value",
        )

    if field in {"bold", "italic"}:
        if type(value) is not bool:
            _fail_payload(
                f"Text style field {field} must be a boolean.",
                reason="invalid_style_value",
            )
        return value

    if field == "underline":
        if type(value) is bool:
            return "single" if value else "none"
        if not isinstance(value, str) or value not in _PORTABLE_UNDERLINE_VALUES:
            _fail_payload(
                "Text underline must be one of none, single, or double.",
                reason="invalid_style_value",
            )
        return value

    if field == "font_size_pt":
        if type(value) not in {int, float} or not isfinite(float(value)):
            _fail_payload(
                "Text font_size_pt must be a finite positive number.",
                reason="invalid_style_value",
            )
        canonical = float(value)
        if canonical <= 0:
            _fail_payload(
                "Text font_size_pt must be a finite positive number.",
                reason="invalid_style_value",
            )
        return canonical

    if field == "font_family":
        if not isinstance(value, str) or not value.strip():
            _fail_payload(
                "Text font_family must be a non-empty string.",
                reason="invalid_style_value",
            )
        return value.strip()

    if field == "color":
        if not isinstance(value, str) or _COLOR_RE.fullmatch(value) is None:
            _fail_payload(
                "Text color must use #RRGGBB syntax.",
                reason="invalid_style_value",
            )
        return value.upper()

    raise UnsupportedEditError(
        "Text style field is not supported by the portable style edit contract.",
        details={"reason": "unsupported_style_field", "field": field},
    )


def _canonical_style_mapping(
    raw: object,
    *,
    allow_clear: bool,
    require_non_empty: bool,
) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        _fail_payload("Text style data must be a mapping.")
    if require_non_empty and not raw:
        _fail_payload("Text style update must contain at least one field.")

    result: dict[str, object] = {}
    for field, value in raw.items():
        if not isinstance(field, str) or field not in SUPPORTED_TEXT_STYLE_FIELDS:
            raise UnsupportedEditError(
                "Text style field is not supported by the portable style edit contract.",
                details={"reason": "unsupported_style_field", "field": field},
            )
        result[field] = _canonical_style_value(
            field,
            value,
            allow_clear=allow_clear,
        )
    return result


def _flatten_runs(payload: TextPayload) -> tuple[TextRun, ...]:
    return tuple(run for paragraph in payload.paragraphs for run in paragraph.runs)


def _source_direct_style(run: TextRun) -> dict[str, object]:
    direct = {} if run.style is None else dict(run.style.direct)
    result: dict[str, object] = {}
    for field, value in direct.items():
        if field not in SUPPORTED_TEXT_STYLE_FIELDS:
            continue
        result[field] = _canonical_style_value(field, value, allow_clear=False)
    return result


def validate_text_style_update(
    payload: TextPayload,
    raw: Any,
) -> tuple[int, dict[str, object], dict[str, object]]:
    if not isinstance(payload, TextPayload):
        raise UnsupportedEditError(
            "set_text_style requires a text payload.",
            details={"reason": "wrong_node_kind"},
        )
    if not isinstance(raw, Mapping):
        _fail_payload("set_text_style requires a mapping payload.")

    run_index = raw.get("run_index")
    if type(run_index) is not int:
        _fail_payload("set_text_style run_index must be an integer.")

    runs = _flatten_runs(payload)
    if run_index < 0 or run_index >= len(runs):
        raise UnsupportedEditError(
            "set_text_style run_index is outside the source text runs.",
            details={"reason": "run_out_of_range", "run_index": run_index},
        )

    source_style = _source_direct_style(runs[run_index])
    old_style = _canonical_style_mapping(
        raw.get("old_style"),
        allow_clear=False,
        require_non_empty=False,
    )
    if old_style != source_style:
        raise PatchPreconditionError(
            "set_text_style old_style no longer matches the source IR.",
            details={
                "reason": "run_style_mismatch",
                "run_index": run_index,
                "expected": source_style,
                "actual": old_style,
            },
        )

    changes = _canonical_style_mapping(
        raw.get("style"),
        allow_clear=True,
        require_non_empty=True,
    )
    target_style = dict(source_style)
    for field, value in changes.items():
        if value is None:
            target_style.pop(field, None)
        else:
            target_style[field] = value

    if target_style == source_style:
        raise UnsupportedEditError(
            "set_text_style must change at least one direct style value.",
            details={"reason": "no_op_style_update", "run_index": run_index},
        )

    return run_index, source_style, target_style
