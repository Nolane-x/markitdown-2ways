from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from ...ir.document import Diagnostic
from .limits import ZipRecursiveLimits
from .model import (
    ParsedZipSource,
    ZipBudgetState,
    ZipMemberClassification,
    ZipParsedMember,
    ZipParseError,
)
from .package import snapshot_zip_package
from .registry import ZipMemberAdapter, default_zip_member_adapters


def _diagnostic(
    code: str,
    message: str,
    chain: tuple[str, ...],
    **details: object,
) -> Diagnostic:
    return Diagnostic(
        code=code,
        severity="warning",
        message=message,
        details={"member_chain": chain, **details},
    )


def _safe_probe(adapter: ZipMemberAdapter, payload: bytes, filename: str) -> bool:
    try:
        return bool(adapter.probe(payload, filename))
    except Exception:
        return False


def _classification(
    payload: bytes,
    filename: str,
    adapters: tuple[ZipMemberAdapter, ...],
) -> ZipMemberClassification:
    strong_claims = tuple(
        adapter.key
        for adapter in adapters
        if adapter.strong_package and _safe_probe(adapter, payload, filename)
    )
    if len(strong_claims) > 1:
        return ZipMemberClassification(
            state="ambiguous",
            probes=strong_claims,
            reason_code="zip.member.ambiguous_format",
        )
    if len(strong_claims) == 1:
        return ZipMemberClassification(
            state="typed",
            adapter_key=strong_claims[0],
            probes=strong_claims,
        )

    fallback_claims = tuple(
        adapter.key
        for adapter in adapters
        if not adapter.strong_package and _safe_probe(adapter, payload, filename)
    )
    if len(fallback_claims) > 1:
        return ZipMemberClassification(
            state="ambiguous",
            probes=fallback_claims,
            reason_code="zip.member.ambiguous_format",
        )
    if len(fallback_claims) == 1:
        return ZipMemberClassification(
            state="typed",
            adapter_key=fallback_claims[0],
            probes=fallback_claims,
        )
    return ZipMemberClassification(
        state="opaque",
        probes=(),
        reason_code="zip.member.unsupported_format",
    )


def _bounded_archive_limits(
    limits: ZipRecursiveLimits,
    state: ZipBudgetState,
) -> ZipRecursiveLimits:
    remaining_members = limits.max_global_members - state.global_members
    remaining_bytes = limits.max_global_expanded_bytes - state.global_expanded_bytes
    if remaining_members < 1:
        remaining_members = 1
    if remaining_bytes < 1:
        remaining_bytes = 1
    return replace(
        limits,
        max_members_per_archive=min(
            limits.max_members_per_archive,
            remaining_members,
        ),
        max_archive_uncompressed_bytes=min(
            limits.max_archive_uncompressed_bytes,
            remaining_bytes,
        ),
    )


def _parse_archive(
    source: bytes,
    *,
    depth: int,
    prefix: tuple[str, ...],
    limits: ZipRecursiveLimits,
    adapters: tuple[ZipMemberAdapter, ...],
    state: ZipBudgetState,
    root: bool,
) -> ParsedZipSource:
    archive_limits = _bounded_archive_limits(limits, state)
    try:
        snapshot = snapshot_zip_package(source, limits=archive_limits)
    except ZipParseError:
        if root:
            raise
        raise

    members: list[ZipParsedMember] = []
    diagnostics: list[Diagnostic] = []

    try:
        archive = ZipFile(BytesIO(source), "r")
    except (BadZipFile, ValueError) as exc:
        raise ZipParseError(
            "Unable to reopen recursive ZIP source.",
            reason="zip.recursion.source_reopen_failed",
        ) from exc

    with archive:
        for entry in snapshot.entries:
            chain = prefix + (entry.name,)
            if entry.is_directory:
                members.append(
                    ZipParsedMember(
                        entry=entry,
                        chain=chain,
                        classification=ZipMemberClassification(
                            state="opaque",
                            reason_code="zip.member.directory",
                        ),
                    )
                )
                continue

            if state.global_members >= limits.max_global_members:
                diagnostics.append(
                    _diagnostic(
                        "zip.recursion.member_budget_exceeded",
                        "Recursive ZIP member budget was exhausted.",
                        chain,
                        limit=limits.max_global_members,
                    )
                )
                members.append(
                    ZipParsedMember(
                        entry=entry,
                        chain=chain,
                        classification=ZipMemberClassification(
                            state="opaque",
                            reason_code="zip.recursion.member_budget_exceeded",
                        ),
                    )
                )
                continue

            state.global_members += 1
            expanded_after = state.global_expanded_bytes + entry.uncompressed_size
            if expanded_after > limits.max_global_expanded_bytes:
                diagnostics.append(
                    _diagnostic(
                        "zip.recursion.expanded_byte_budget_exceeded",
                        "Recursive ZIP expanded-byte budget was exhausted.",
                        chain,
                        limit=limits.max_global_expanded_bytes,
                    )
                )
                members.append(
                    ZipParsedMember(
                        entry=entry,
                        chain=chain,
                        classification=ZipMemberClassification(
                            state="opaque",
                            reason_code="zip.recursion.expanded_byte_budget_exceeded",
                        ),
                    )
                )
                continue
            state.global_expanded_bytes = expanded_after

            try:
                payload = archive.read(entry.name)
            except (BadZipFile, RuntimeError, ValueError) as exc:
                raise ZipParseError(
                    "Unable to read recursive ZIP member.",
                    reason="zip.recursion.member_read_failed",
                    details={"member_chain": chain},
                ) from exc

            classification = _classification(payload, entry.name, adapters)
            nested_archive = None

            if classification.state == "typed" and classification.adapter_key == "zip":
                if depth + 1 >= limits.max_depth:
                    classification = ZipMemberClassification(
                        state="opaque",
                        probes=classification.probes,
                        reason_code="zip.recursion.depth_exceeded",
                    )
                    diagnostics.append(
                        _diagnostic(
                            "zip.recursion.depth_exceeded",
                            "Recursive ZIP depth limit prevented descent.",
                            chain,
                            depth=depth + 1,
                            limit=limits.max_depth,
                        )
                    )
                elif state.global_members >= limits.max_global_members:
                    diagnostics.append(
                        _diagnostic(
                            "zip.recursion.member_budget_exceeded",
                            "Recursive ZIP member budget prevented descent.",
                            chain,
                            limit=limits.max_global_members,
                        )
                    )
                elif state.global_expanded_bytes >= limits.max_global_expanded_bytes:
                    diagnostics.append(
                        _diagnostic(
                            "zip.recursion.expanded_byte_budget_exceeded",
                            "Recursive ZIP expanded-byte budget prevented descent.",
                            chain,
                            limit=limits.max_global_expanded_bytes,
                        )
                    )
                else:
                    try:
                        nested_archive = _parse_archive(
                            payload,
                            depth=depth + 1,
                            prefix=chain,
                            limits=limits,
                            adapters=adapters,
                            state=state,
                            root=False,
                        )
                    except ZipParseError as exc:
                        remaining_members = (
                            limits.max_global_members - state.global_members
                        )
                        remaining_bytes = (
                            limits.max_global_expanded_bytes
                            - state.global_expanded_bytes
                        )
                        if (
                            exc.reason == "zip.package.too_many_members"
                            and remaining_members < limits.max_members_per_archive
                        ):
                            diagnostics.append(
                                _diagnostic(
                                    "zip.recursion.member_budget_exceeded",
                                    "Recursive ZIP member budget prevented descent.",
                                    chain,
                                    limit=limits.max_global_members,
                                )
                            )
                        elif (
                            exc.reason == "zip.package.archive_too_large"
                            and remaining_bytes < limits.max_archive_uncompressed_bytes
                        ):
                            diagnostics.append(
                                _diagnostic(
                                    "zip.recursion.expanded_byte_budget_exceeded",
                                    "Recursive ZIP expanded-byte budget prevented descent.",
                                    chain,
                                    limit=limits.max_global_expanded_bytes,
                                )
                            )
                        else:
                            diagnostics.append(
                                _diagnostic(
                                    "zip.recursion.nested_archive_rejected",
                                    "Nested ZIP package failed closed validation.",
                                    chain,
                                    reason=exc.reason,
                                )
                            )

            members.append(
                ZipParsedMember(
                    entry=entry,
                    chain=chain,
                    classification=classification,
                    nested_archive=nested_archive,
                    inner_document=None,
                )
            )
            if nested_archive is not None:
                diagnostics.extend(nested_archive.diagnostics)

    return ParsedZipSource(
        snapshot=snapshot,
        members=tuple(members),
        depth=depth,
        diagnostics=tuple(diagnostics),
    )


def parse_zip_source(
    source: bytes,
    *,
    filename: str | None = None,
    limits: ZipRecursiveLimits | None = None,
    adapters: Sequence[ZipMemberAdapter] | None = None,
) -> ParsedZipSource:
    del filename
    limits = limits or ZipRecursiveLimits()
    resolved_adapters = tuple(adapters or default_zip_member_adapters())
    keys = tuple(adapter.key for adapter in resolved_adapters)
    if len(keys) != len(set(keys)):
        raise ValueError("ZIP member adapter keys must be unique")
    return _parse_archive(
        source,
        depth=0,
        prefix=(),
        limits=limits,
        adapters=resolved_adapters,
        state=ZipBudgetState(),
        root=True,
    )
