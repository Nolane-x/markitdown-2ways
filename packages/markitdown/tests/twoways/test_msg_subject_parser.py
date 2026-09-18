from __future__ import annotations

import pytest

from markitdown.twoways.formats.msg import MsgFormatError, MsgLimits, parse_msg

from ._msg_fixtures import (
    PROPATTR_READABLE,
    STORE_UNICODE_OK,
    SUBJECT_TAG,
    make_cfb,
    make_msg_cfb,
    make_property_stream,
)


def test_parses_safe_unicode_subject_owner() -> None:
    fixture = make_msg_cfb(subject="Alpha")

    parsed = parse_msg(fixture.data)

    owner = parsed.subject_owner
    assert owner is not None
    assert owner.value == "Alpha"
    assert owner.property_tag == SUBJECT_TAG
    assert owner.property_type == 0x001F
    assert owner.property_id == 0x0037
    assert owner.declared_size == len(fixture.subject_bytes) + 2
    assert owner.stream.stream_size == len(fixture.subject_bytes)
    assert owner.stream.logical_bytes == fixture.subject_bytes
    assert owner.property_entry.index == 1
    assert owner.property_entry.logical_offset == 48
    assert sum(r.length for r in owner.property_entry.physical_ranges) == 16
    assert len(owner.property_entry.raw_sha256) == 64
    assert len(owner.stream.sha256) == 64
    assert parsed.store_support_mask & STORE_UNICODE_OK
    assert parsed.blockers == ()


@pytest.mark.parametrize(
    ("options", "reason"),
    (
        ({"include_subject": False}, "msg.subject.missing"),
        ({"duplicate_subject": True}, "msg.subject.duplicate_property"),
        ({"include_store_support": False}, "msg.subject.ansi_read_only"),
        ({"duplicate_store_support": True}, "msg.subject.ansi_read_only"),
        ({"unicode_ok": False}, "msg.subject.ansi_read_only"),
        ({"include_ansi_subject": True}, "msg.subject.ansi_read_only"),
        (
            {"subject_flags": PROPATTR_READABLE},
            "msg.subject.property_not_writable",
        ),
        ({"store_flags": 0}, "msg.subject.ansi_read_only"),
        (
            {"include_subject_prefix": True},
            "msg.subject.competing_semantics",
        ),
        (
            {"include_normalized_subject": True},
            "msg.subject.competing_semantics",
        ),
        ({"subject_size_adjust": 2}, "msg.subject.size_mismatch"),
    ),
)
def test_subject_authority_blockers_are_stable(
    options: dict[str, object],
    reason: str,
) -> None:
    parsed = parse_msg(make_msg_cfb(**options).data)

    assert reason in parsed.blockers


def test_duplicate_top_level_subject_stream_is_blocked() -> None:
    subject = "Alpha".encode("utf-16-le")
    properties = make_property_stream(subject)
    source = make_cfb(
        properties_bytes=properties,
        subject_bytes=subject,
        duplicate_subject_name=True,
    ).data

    parsed = parse_msg(source)

    assert parsed.subject_owner is None
    assert "msg.subject.duplicate_stream" in parsed.blockers


def test_invalid_utf16_subject_is_read_only() -> None:
    parsed = parse_msg(make_msg_cfb(subject_bytes=b"\x00\xD8").data)

    assert parsed.subject_owner is None
    assert "msg.subject.invalid_utf16" in parsed.blockers


def test_odd_length_subject_is_read_only() -> None:
    parsed = parse_msg(make_msg_cfb(subject_bytes=b"A").data)

    assert parsed.subject_owner is None
    assert "msg.subject.invalid_utf16" in parsed.blockers


def test_embedded_nul_subject_is_read_only() -> None:
    parsed = parse_msg(make_msg_cfb(subject="A\x00B").data)

    assert parsed.subject_owner is None
    assert "msg.subject.embedded_nul" in parsed.blockers


def test_property_stream_length_must_be_complete_entries() -> None:
    fixture = make_msg_cfb()
    malformed_properties = fixture.properties_bytes + b"X"
    source = make_cfb(
        properties_bytes=malformed_properties,
        subject_bytes=fixture.subject_bytes,
    ).data

    with pytest.raises(MsgFormatError, match="property stream.*length|16-byte"):
        parse_msg(source)


def test_property_entry_limit_fails_closed() -> None:
    source = make_msg_cfb().data

    with pytest.raises(MsgFormatError, match="property.*limit|resource"):
        parse_msg(source, limits=MsgLimits(max_property_entries=1))
