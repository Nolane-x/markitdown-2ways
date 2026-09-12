from __future__ import annotations

import pytest

from markitdown.twoways import PatchPreconditionError, UnsupportedEditError
from markitdown.twoways.ir.nodes import Paragraph, TextPayload, TextRun
from markitdown.twoways.ir.style import Style


def _validate(payload: TextPayload, raw: object):
    try:
        from markitdown.twoways.ir.style_edits import validate_text_style_update
    except ModuleNotFoundError:
        pytest.fail("style_edits module is not implemented yet")
    return validate_text_style_update(payload, raw)


def _payload() -> TextPayload:
    return TextPayload(
        text="Revenue 38%",
        paragraphs=(
            Paragraph(
                runs=(
                    TextRun(
                        text="Revenue ",
                        style=Style(
                            direct={
                                "bold": True,
                                "font_family": "Aptos",
                                "font_size_pt": 12.0,
                                "color": "#112233",
                            }
                        ),
                    ),
                    TextRun(text="38%", style=Style(direct={"italic": True})),
                )
            ),
        ),
    )


def test_validate_text_style_update_returns_canonical_final_style():
    run_index, old_style, new_style = _validate(
        _payload(),
        {
            "run_index": 0,
            "old_style": {
                "bold": True,
                "font_family": "Aptos",
                "font_size_pt": 12,
                "color": "#112233",
            },
            "style": {
                "bold": False,
                "italic": True,
                "font_size_pt": 14,
                "color": "#AABBCC",
            },
        },
    )

    assert run_index == 0
    assert old_style == {
        "bold": True,
        "font_family": "Aptos",
        "font_size_pt": 12.0,
        "color": "#112233",
    }
    assert new_style == {
        "bold": False,
        "italic": True,
        "font_family": "Aptos",
        "font_size_pt": 14.0,
        "color": "#AABBCC",
    }


def test_validate_text_style_update_can_clear_direct_property():
    _, _, new_style = _validate(
        _payload(),
        {
            "run_index": 1,
            "old_style": {"italic": True},
            "style": {"italic": None},
        },
    )
    assert new_style == {}


def test_validate_text_style_update_flattens_runs_deterministically():
    payload = TextPayload(
        text="AB",
        paragraphs=(
            Paragraph(runs=(TextRun(text="A"),)),
            Paragraph(runs=(TextRun(text="B", style=Style(direct={"bold": True})),)),
        ),
    )
    run_index, old_style, new_style = _validate(
        payload,
        {"run_index": 1, "old_style": {"bold": True}, "style": {"bold": False}},
    )
    assert (run_index, old_style, new_style) == (1, {"bold": True}, {"bold": False})


@pytest.mark.parametrize("run_index", [True, False, -1, 2, 1.0, "1"])
def test_validate_text_style_update_rejects_invalid_run_index(run_index: object):
    with pytest.raises(UnsupportedEditError) as exc:
        _validate(
            _payload(),
            {"run_index": run_index, "old_style": {}, "style": {"bold": True}},
        )
    assert exc.value.details["reason"] in {"invalid_edit_payload", "run_out_of_range"}


def test_validate_text_style_update_rejects_unknown_style_field():
    with pytest.raises(UnsupportedEditError) as exc:
        _validate(
            _payload(),
            {
                "run_index": 0,
                "old_style": {
                    "bold": True,
                    "font_family": "Aptos",
                    "font_size_pt": 12.0,
                    "color": "#112233",
                },
                "style": {"shadow": True},
            },
        )
    assert exc.value.details["reason"] == "unsupported_style_field"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bold", 1),
        ("italic", "true"),
        ("font_size_pt", 0),
        ("font_size_pt", -2),
        ("font_size_pt", float("inf")),
        ("font_family", ""),
        ("font_family", "   "),
        ("color", "112233"),
        ("color", "#12345G"),
        ("underline", "wavyHeavy"),
    ],
)
def test_validate_text_style_update_rejects_invalid_style_values(
    field: str, value: object
):
    with pytest.raises(UnsupportedEditError) as exc:
        _validate(
            _payload(),
            {
                "run_index": 0,
                "old_style": {
                    "bold": True,
                    "font_family": "Aptos",
                    "font_size_pt": 12.0,
                    "color": "#112233",
                },
                "style": {field: value},
            },
        )
    assert exc.value.details["reason"] == "invalid_style_value"


def test_validate_text_style_update_accepts_portable_underline_values():
    payload = TextPayload(
        text="X",
        paragraphs=(
            Paragraph(
                runs=(TextRun(text="X", style=Style(direct={"underline": "single"})),)
            ),
        ),
    )
    _, _, new_style = _validate(
        payload,
        {
            "run_index": 0,
            "old_style": {"underline": "single"},
            "style": {"underline": "double"},
        },
    )
    assert new_style == {"underline": "double"}


def test_validate_text_style_update_rejects_stale_old_style():
    with pytest.raises(PatchPreconditionError) as exc:
        _validate(
            _payload(),
            {
                "run_index": 0,
                "old_style": {"bold": False},
                "style": {"bold": True},
            },
        )
    assert exc.value.details["reason"] == "run_style_mismatch"


def test_validate_text_style_update_rejects_no_op_update():
    with pytest.raises(UnsupportedEditError) as exc:
        _validate(
            _payload(),
            {
                "run_index": 1,
                "old_style": {"italic": True},
                "style": {"italic": True},
            },
        )
    assert exc.value.details["reason"] == "no_op_style_update"
