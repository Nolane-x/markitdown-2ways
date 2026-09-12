from __future__ import annotations

import pytest

from markitdown.twoways.formats.html.lexical import parse_html_source
from markitdown.twoways.formats.html.recovery import build_recovery_signature


def test_explicit_stable_html_has_recovery_signature() -> None:
    text = '<html><head><title>x</title></head><body><main><p class="a">one</p><p>two</p></main></body></html>'
    parsed = parse_html_source(text.encode("utf-8"))

    assert parsed.recovery_stable is True
    assert parsed.recovery_reason is None
    assert parsed.recovery_signature == build_recovery_signature(text)
    assert parsed.recovery_signature.entries


def test_recovery_signature_ignores_scalar_values_but_not_structure() -> None:
    first = '<html><body><p class="a">one</p></body></html>'
    second = '<html><body><p class="b">two</p></body></html>'
    structural = '<html><body><section class="a">one</section></body></html>'

    assert build_recovery_signature(first) == build_recovery_signature(second)
    assert build_recovery_signature(first) != build_recovery_signature(structural)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("<html><body><p>one<p>two</body></html>", "html.recovery.optional_end_tag"),
        ("<html><body><p><div>x</div></p></body></html>", "html.recovery.nested_p"),
        (
            "<html><body><ul><li>one<li>two</ul></body></html>",
            "html.recovery.optional_end_tag",
        ),
        (
            "<html><body><table><td>x</td></table></body></html>",
            "html.table.recovery_sensitive",
        ),
        (
            "<html><body><template><p>x</p></template></body></html>",
            "html.template.recovery_sensitive",
        ),
        (
            "<html><body><svg><text>x</text></svg></body></html>",
            "html.foreign_content.unsupported",
        ),
        (
            "<html><body><math><mi>x</mi></math></body></html>",
            "html.foreign_content.unsupported",
        ),
    ],
)
def test_recovery_sensitive_html_is_read_only(text: str, reason: str) -> None:
    parsed = parse_html_source(text.encode("utf-8"))

    assert parsed.recovery_stable is False
    assert parsed.recovery_reason == reason


def test_mismatched_or_unclosed_nonvoid_element_is_recovery_unstable() -> None:
    for text in (
        "<html><body><div><span>x</div></body></html>",
        "<html><body><div>x</body></html>",
    ):
        parsed = parse_html_source(text.encode("utf-8"))
        assert parsed.recovery_stable is False
        assert parsed.recovery_reason in {
            "html.recovery.mismatched_tag",
            "html.recovery.unclosed_tag",
            "html.recovery.unstable",
        }


def test_nonvoid_self_closing_and_void_end_tag_are_recovery_unstable() -> None:
    self_closing = parse_html_source(b"<html><body><div/></body></html>")
    void_end = parse_html_source(b"<html><body><br></br></body></html>")

    assert self_closing.recovery_stable is False
    assert self_closing.recovery_reason == "html.recovery.nonvoid_self_closing"
    assert void_end.recovery_stable is False
    assert void_end.recovery_reason == "html.recovery.void_end_tag"


def test_rcdata_owner_does_not_become_normal_text() -> None:
    parsed = parse_html_source(
        b"<html><head><title>A&amp;B</title></head><body><textarea>x&amp;y</textarea></body></html>"
    )

    assert parsed.recovery_stable is True
    rcdata = [node for node in parsed.lexical.nodes if node.kind == "rcdata"]
    assert len(rcdata) == 2
    assert [node.value for node in rcdata] == ["A&B", "x&y"]
