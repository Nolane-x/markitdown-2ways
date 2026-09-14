from __future__ import annotations

from zipfile import ZIP_STORED

from markitdown.twoways.formats.zip.limits import ZipRecursiveLimits
from markitdown.twoways.formats.zip.parser import parse_zip_source
from markitdown.twoways.formats.zip.registry import ZipMemberAdapter

from ._epub_fixtures import make_epub
from ._zip_fixtures import make_zip


def _fake_strong_adapter(key: str) -> ZipMemberAdapter:
    return ZipMemberAdapter(
        key=key,
        extensions=frozenset(),
        probe=lambda payload, filename: True,
        read=None,
        patch=None,
        strong_package=True,
    )


def test_epub_package_claims_before_generic_zip_without_extension_hint() -> None:
    source = make_zip(members={"book.bin": make_epub()})
    parsed = parse_zip_source(source)
    member = parsed.member_by_chain[("book.bin",)]

    assert member.classification.state == "typed"
    assert member.classification.adapter_key == "epub"
    assert member.nested_archive is None


def test_nested_ordinary_zip_recurses_after_strong_probes_decline() -> None:
    nested = make_zip(members={"note.txt": b"nested\n"})
    parsed = parse_zip_source(make_zip(members={"nested.zip": nested}))
    member = parsed.member_by_chain[("nested.zip",)]

    assert member.classification.state == "typed"
    assert member.classification.adapter_key == "zip"
    assert member.nested_archive is not None
    assert ("nested.zip", "note.txt") in parsed.member_by_chain


def test_misleading_epub_extension_does_not_override_package_evidence() -> None:
    ordinary = make_zip(members={"plain.txt": b"x"})
    parsed = parse_zip_source(make_zip(members={"fake.epub": ordinary}))
    member = parsed.member_by_chain[("fake.epub",)]

    assert member.classification.state == "typed"
    assert member.classification.adapter_key == "zip"
    assert member.nested_archive is not None


def test_two_non_equivalent_strong_claims_are_ambiguous() -> None:
    adapters = (
        _fake_strong_adapter("strong-a"),
        _fake_strong_adapter("strong-b"),
    )
    parsed = parse_zip_source(
        make_zip(members={"x.bin": b"payload"}),
        adapters=adapters,
    )
    member = parsed.member_by_chain[("x.bin",)]

    assert member.classification.state == "ambiguous"
    assert member.classification.adapter_key is None
    assert member.classification.reason_code == "zip.member.ambiguous_format"


def test_global_member_budget_is_shared_across_nested_archives() -> None:
    nested_a = make_zip(members={"a.txt": b"a", "b.txt": b"b"})
    nested_b = make_zip(members={"c.txt": b"c", "d.txt": b"d"})
    source = make_zip(members={"a.zip": nested_a, "b.zip": nested_b})
    parsed = parse_zip_source(
        source,
        limits=ZipRecursiveLimits(max_global_members=4),
    )

    assert any(
        diagnostic.code == "zip.recursion.member_budget_exceeded"
        for diagnostic in parsed.diagnostics
    )
    assert parsed.member_by_chain[("a.zip",)].classification.adapter_key == "zip"
    assert parsed.member_by_chain[("b.zip",)].classification.adapter_key == "zip"
    descendants = [chain for chain in parsed.member_by_chain if len(chain) > 1]
    assert len(descendants) <= 2


def test_global_expanded_byte_budget_is_shared_across_nested_archives() -> None:
    nested_a = make_zip(members={"a.txt": b"1234"}, compression=ZIP_STORED)
    nested_b = make_zip(members={"b.txt": b"5678"}, compression=ZIP_STORED)
    source = make_zip(
        members={"a.zip": nested_a, "b.zip": nested_b, "safe.txt": b"ok"},
        compression=ZIP_STORED,
    )
    root_expanded = len(nested_a) + len(nested_b) + len(b"ok")
    parsed = parse_zip_source(
        source,
        limits=ZipRecursiveLimits(
            max_archive_uncompressed_bytes=root_expanded + 16,
            max_global_expanded_bytes=root_expanded + 5,
        ),
    )

    assert any(
        diagnostic.code == "zip.recursion.expanded_byte_budget_exceeded"
        for diagnostic in parsed.diagnostics
    )
    assert parsed.member_by_chain[("safe.txt",)].entry.name == "safe.txt"
    descendants = [chain for chain in parsed.member_by_chain if len(chain) > 1]
    assert len(descendants) <= 1


def test_nested_zip_bomb_is_rejected_without_losing_safe_sibling() -> None:
    nested_bomb = make_zip(members={"bomb.txt": b"A" * 16_384})
    source = make_zip(
        members={"nested.zip": nested_bomb, "safe.txt": b"safe\n"},
        compression=ZIP_STORED,
    )
    parsed = parse_zip_source(
        source,
        limits=ZipRecursiveLimits(max_compression_ratio=2.0),
    )

    nested = parsed.member_by_chain[("nested.zip",)]
    sibling = parsed.member_by_chain[("safe.txt",)]
    rejected = [
        diagnostic
        for diagnostic in parsed.diagnostics
        if diagnostic.code == "zip.recursion.nested_archive_rejected"
    ]

    assert nested.classification.state == "typed"
    assert nested.classification.adapter_key == "zip"
    assert nested.nested_archive is None
    assert sibling.entry.name == "safe.txt"
    assert rejected
    assert rejected[0].details["reason"] == "zip.package.compression_ratio_too_high"


def test_depth_exhaustion_keeps_unrelated_sibling_represented() -> None:
    level_two = make_zip(members={"deep.txt": b"deep"})
    level_one = make_zip(members={"level-two.zip": level_two})
    source = make_zip(
        members={
            "nested.zip": level_one,
            "sibling.txt": b"safe\n",
        }
    )
    parsed = parse_zip_source(source, limits=ZipRecursiveLimits(max_depth=2))

    deep = parsed.member_by_chain[("nested.zip", "level-two.zip")]
    sibling = parsed.member_by_chain[("sibling.txt",)]
    assert deep.classification.state == "opaque"
    assert deep.classification.reason_code == "zip.recursion.depth_exceeded"
    assert sibling.entry.name == "sibling.txt"
