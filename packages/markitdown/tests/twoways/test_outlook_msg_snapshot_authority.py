from __future__ import annotations

from io import BytesIO

import pytest

from markitdown.twoways import (
    OutlookMsgConverterSnapshot,
    OutlookMsgDerivedLimits,
    read_outlook_msg_snapshot_ir,
)

from .test_outlook_msg_snapshot_reader import INFO, SNAPSHOT, SOURCE


class _BoundedReadProbe(BytesIO):
    def __init__(self, data: bytes, *, maximum_request: int) -> None:
        super().__init__(data)
        self.maximum_request = maximum_request
        self.requests: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.requests.append(size)
        if size < 0 or size > self.maximum_request:
            raise AssertionError(f"unbounded read request: {size}")
        return super().read(size)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("sender", 7),
        ("recipients", b"bytes"),
        ("subject", 9.5),
        ("body", object()),
    ),
)
def test_semantic_fields_are_string_or_none(field: str, value: object) -> None:
    with pytest.raises(TypeError, match=field):
        OutlookMsgConverterSnapshot(provider="fixture", **{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("provider", ""),
        ("provider", "   "),
        ("materialization_id", ""),
        ("message_encoding", " "),
        ("internet_encoding", ""),
    ),
)
def test_authority_descriptors_reject_blank_values(
    field: str,
    value: str,
) -> None:
    kwargs = {"provider": "fixture", field: value}
    with pytest.raises(ValueError, match=field):
        OutlookMsgConverterSnapshot(**kwargs)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_source_bytes", 0),
        ("max_snapshot_utf8_bytes", 0),
        ("max_markdown_utf8_bytes", 0),
        ("max_source_bytes", True),
        ("max_snapshot_utf8_bytes", False),
        ("max_markdown_utf8_bytes", 1.5),
    ),
)
def test_limits_fail_closed(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        OutlookMsgDerivedLimits(**{field: value})


def test_source_limit_accepts_exact_boundary_and_reads_bounded() -> None:
    probe = _BoundedReadProbe(SOURCE, maximum_request=64 * 1024)
    exact = read_outlook_msg_snapshot_ir(
        probe,
        stream_info=INFO,
        snapshot=SNAPSHOT,
        limits=OutlookMsgDerivedLimits(max_source_bytes=len(SOURCE)),
    )
    assert exact.source is not None
    assert exact.source.size_bytes == len(SOURCE)
    assert probe.requests
    assert all(0 <= size <= 64 * 1024 for size in probe.requests)

    with pytest.raises(ValueError, match="max_source_bytes"):
        read_outlook_msg_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=INFO,
            snapshot=SNAPSHOT,
            limits=OutlookMsgDerivedLimits(max_source_bytes=len(SOURCE) - 1),
        )


def test_snapshot_and_markdown_limits_have_exact_boundaries() -> None:
    values = (
        SNAPSHOT.sender,
        SNAPSHOT.recipients,
        SNAPSHOT.subject,
        SNAPSHOT.body,
    )
    snapshot_size = sum(
        len(value.encode("utf-8")) for value in values if value is not None
    )
    markdown = (
        "# Email Message\n\n"
        "**From:** alice@example.com\n"
        "**To:** bob@example.com\n"
        "**Subject:** Quarterly update\n"
        "\n## Content\n\n"
        "Hello Bob,\n\nThe report is attached."
    )
    markdown_size = len(markdown.encode("utf-8"))

    exact = read_outlook_msg_snapshot_ir(
        BytesIO(SOURCE),
        stream_info=INFO,
        snapshot=SNAPSHOT,
        limits=OutlookMsgDerivedLimits(
            max_snapshot_utf8_bytes=snapshot_size,
            max_markdown_utf8_bytes=markdown_size,
        ),
    )
    assert exact.root_node_ids

    with pytest.raises(ValueError, match="max_snapshot_utf8_bytes"):
        read_outlook_msg_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=INFO,
            snapshot=SNAPSHOT,
            limits=OutlookMsgDerivedLimits(max_snapshot_utf8_bytes=snapshot_size - 1),
        )

    with pytest.raises(ValueError, match="max_markdown_utf8_bytes"):
        read_outlook_msg_snapshot_ir(
            BytesIO(SOURCE),
            stream_info=INFO,
            snapshot=SNAPSHOT,
            limits=OutlookMsgDerivedLimits(max_markdown_utf8_bytes=markdown_size - 1),
        )
