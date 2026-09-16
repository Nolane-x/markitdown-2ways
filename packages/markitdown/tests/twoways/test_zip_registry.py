from __future__ import annotations

from markitdown.twoways.formats.zip.registry import (
    ZipMemberAdapter,
    default_zip_member_adapters,
)


def _probe_false(payload: bytes, filename: str) -> bool:
    del payload, filename
    return False


def test_default_zip_member_adapter_priority_is_deterministic() -> None:
    adapters = default_zip_member_adapters()
    keys = tuple(adapter.key for adapter in adapters)

    assert keys[:4] == ("epub", "docx", "pptx", "xlsx")
    assert keys[-1] == "zip"
    assert len(keys) == len(set(keys))


def test_zip_member_adapter_requires_stable_identity_fields() -> None:
    adapter = ZipMemberAdapter(
        key="fake",
        extensions=frozenset({".fake"}),
        probe=_probe_false,
        read=None,
        patch=None,
        strong_package=False,
    )

    assert adapter.key == "fake"
    assert adapter.extensions == frozenset({".fake"})
    assert adapter.strong_package is False
