# MarkItDown 2Ways Phase H8 Recursive ZIP Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement conservative recursive two-way editing for ordinary ZIP containers by routing edits to existing inner format adapters while preserving archive structure, untouched member content, and exact zero-edit bytes.

**Architecture:** H8 owns ZIP container authority, recursive budgets, member classification, namespaced nested `DocumentIR` composition, and upward sparse-candidate propagation. Existing H1-H7 format readers/writers remain authoritative for inner semantics and typed mutation; H8 adds no arbitrary raw-member edit operation. Every mutation follows root source authority -> fresh recursive parse -> complete edit preflight -> fresh inner writer transactions -> sparse archive propagation -> full recursive candidate verification -> caller output.

**Tech Stack:** Python stdlib `zipfile`, `hashlib`, `io`, `os.path`, `posixpath`; existing `DocumentIR`, capability and edit contracts; existing H1-H7 readers/writers; pytest; GitHub Actions package/OCR matrices on Python 3.10-3.13.

**Spec:** `docs/superpowers/specs/2026-09-13-markitdown-2ways-phase-h8-recursive-zip-preservation-design.md`

## Global Constraints

- H8 starts from exact-green H7 completion head `dbb016db4797c5646e863735764243d0e5c5b2a7`.
- H7 completion authority is immutable; do not add commits to `phase-h7-epub-package-preservation`.
- Do not modify `packages/markitdown/src/markitdown/converters/_zip_converter.py`.
- Do not change one-way converter registration or dispatch order.
- Do not add `replace_zip_member`, `write_zip_member`, or another arbitrary member-bytes mutation operation.
- ZIP structural nodes remain read-only in H8 tranche one.
- Specific package adapters outrank generic ZIP recursion: EPUB, DOCX, PPTX, XLSX, future strong package adapters, then ordinary ZIP.
- Filename extension is only a hint and cannot establish strong ZIP-based package authority by itself.
- Only `ZIP_STORED` and `ZIP_DEFLATED` are supported in H8 tranche one.
- No encrypted members, symlink members, unsafe paths, duplicate names, archive repair, filesystem extraction, network access, subprocesses, TAR/7z/RAR support, or remote writeback.
- Recursive limits are shared across the whole tree; nested archives must not reset global member or expanded-byte counters.
- Initial `ZipRecursiveLimits` defaults: `max_depth=4`, `max_members_per_archive=10_000`, `max_global_members=10_000`, `max_member_uncompressed_bytes=64 * 1024 * 1024`, `max_archive_uncompressed_bytes=512 * 1024 * 1024`, `max_global_expanded_bytes=512 * 1024 * 1024`, `max_compression_ratio=200.0`.
- Zero-edit output is byte-for-byte identical to the root source ZIP.
- Mutated archives preserve ordered inventory, archive comments, directory members, compression method and supported entry metadata; untouched immediate-member uncompressed content is byte-identical.
- Identity Markdown is inspection-only for ZIP-backed nested content in H8 tranche one.
- Production behavior is added only after its corresponding test-only head has been observed RED for the intended missing behavior.
- Caller output remains empty on every preflight, routing, inner writer, package construction, or verification failure.
- H8 completion requires exact final-head 9/9 GREEN: pre-commit + package 3.10/3.11/3.12/3.13 + OCR 3.10/3.11/3.12/3.13.

## File Structure

Production lives under one new format package:

```text
packages/markitdown/src/markitdown/twoways/formats/zip/
    __init__.py          public H8 format facade only
    limits.py            immutable recursive limits + validation
    model.py             immutable ZIP/archive/classification evidence + ZipParseError
    package.py           safe one-archive snapshot/read/sparse-candidate authority
    registry.py          explicit two-way member adapter registry and strong-format priority
    parser.py            recursive parse/classification tree under shared budget state
    reader.py            recursive tree -> namespaced outer DocumentIR
    routing.py           fresh member-chain resolution and inner edit reconstruction
    verification.py      recursive final candidate preservation/routing checks
    writer.py            transactional H8 patch orchestration
    writer_adapter.py    DocumentWriter adapter
```

Tests remain isolated under `packages/markitdown/tests/twoways/`:

```text
_zip_fixtures.py
test_zip_package.py
test_zip_registry.py
test_zip_parser.py
test_zip_reader.py
test_zip_routing.py
test_zip_verification.py
test_zip_writer.py
test_zip_public_imports.py
test_zip_markdown.py
test_zip_oneway_regression.py
```

Do not modify H1-H7 adapters unless a focused RED test proves a minimal shared compatibility defect; any such change requires its own regression test and explicit scope note.

---

### Task 1: Freeze deterministic ZIP fixtures and package-safety RED contracts

**Files:**
- Create: `packages/markitdown/tests/twoways/_zip_fixtures.py`
- Create: `packages/markitdown/tests/twoways/test_zip_package.py`

**Interfaces:**
- Consumes: Python `zipfile.ZipFile`, `ZipInfo`, `ZIP_STORED`, `ZIP_DEFLATED`.
- Produces test fixture: `make_zip(*, members: Mapping[str, bytes] | None = None, compression: int = ZIP_DEFLATED, archive_comment: bytes = b"", per_member_compression: Mapping[str, int] | None = None) -> bytes`.
- Produces production contracts for Task 2: `ZipRecursiveLimits`, `ZipPackageSnapshot`, `snapshot_zip_package`, `read_zip_member`, `build_zip_candidate`, `ZipParseError`.

- [ ] **Step 1: Add deterministic in-memory ZIP fixture builder.**

```python
from collections.abc import Mapping
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def make_zip(
    *,
    members: Mapping[str, bytes] | None = None,
    compression: int = ZIP_DEFLATED,
    archive_comment: bytes = b"",
    per_member_compression: Mapping[str, int] | None = None,
) -> bytes:
    members = members or {"docs/readme.txt": b"hello\n", "data/config.json": b'{"name":"Ada"}\n'}
    per_member_compression = per_member_compression or {}
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.comment = archive_comment
        for name, payload in members.items():
            info = ZipInfo(name, date_time=(2026, 1, 2, 3, 4, 6))
            info.compress_type = per_member_compression.get(name, compression)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
    return output.getvalue()
```

- [ ] **Step 2: Add package RED test for ordered inventory and exact source/member evidence.**

```python
def test_zip_snapshot_records_ordered_inventory_and_member_digests() -> None:
    source = make_zip(archive_comment=b"h8")
    snapshot = snapshot_zip_package(source)
    assert snapshot.source_sha256 == sha256(source).hexdigest()
    assert snapshot.source_size == len(source)
    assert snapshot.archive_comment == b"h8"
    assert tuple(entry.name for entry in snapshot.entries) == (
        "docs/readme.txt",
        "data/config.json",
    )
    assert snapshot.entry_by_name["docs/readme.txt"].uncompressed_sha256 == sha256(b"hello\n").hexdigest()
```

- [ ] **Step 3: Add fail-closed package RED matrix.**

```python
@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/drive", "dir\\evil", "a/../evil"])
def test_zip_unsafe_member_paths_fail_closed(name: str) -> None:
    with pytest.raises(ZipParseError):
        snapshot_zip_package(make_zip(members={name: b"x"}))


def test_zip_bzip2_member_fails_closed() -> None:
    source = make_zip(per_member_compression={"docs/readme.txt": ZIP_BZIP2})
    with pytest.raises(ZipParseError, match="compression"):
        snapshot_zip_package(source)
```

Add explicit tests in the same file for duplicate names, symlink mode, encryption flag, member-count limit, per-member size, archive total size, compression ratio, and malformed ZIP bytes. Each assertion must require `ZipParseError` and a stable `reason` prefix under `zip.package.*`.

- [ ] **Step 4: Add zero-edit/sparse candidate RED contracts.**

```python
def test_zip_candidate_zero_replacements_returns_exact_source_bytes() -> None:
    source = make_zip()
    snapshot = snapshot_zip_package(source)
    assert build_zip_candidate(snapshot, source, replacements={}) == source


def test_zip_candidate_replaces_only_known_regular_member() -> None:
    source = make_zip()
    snapshot = snapshot_zip_package(source)
    candidate = build_zip_candidate(snapshot, source, replacements={"docs/readme.txt": b"updated\n"})
    with ZipFile(BytesIO(candidate), "r") as archive:
        assert archive.read("docs/readme.txt") == b"updated\n"
        assert archive.read("data/config.json") == b'{"name":"Ada"}\n'
        assert archive.namelist() == ["docs/readme.txt", "data/config.json"]
```

- [ ] **Step 5: Commit test-only RED head.**

```bash
git add packages/markitdown/tests/twoways/_zip_fixtures.py packages/markitdown/tests/twoways/test_zip_package.py
git commit -m "test: define H8 ZIP package contracts"
```

- [ ] **Step 6: Run focused test and record intended RED.**

Run:
```bash
cd packages/markitdown
hatch test -py=3.11 tests/twoways/test_zip_package.py -q
```
Expected: collection fails because `markitdown.twoways.formats.zip` / package APIs do not exist. Do not add production until this exact test-only head is observed RED in CI or equivalent fresh execution.

---

### Task 2: Implement safe one-archive package authority and sparse candidate builder

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/zip/limits.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/zip/model.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/zip/package.py`

**Interfaces:**
- `ZipRecursiveLimits` frozen dataclass with the exact defaults in Global Constraints.
- `ZipPackageEntry(name, uncompressed_sha256, uncompressed_size, compressed_size, compression_method, crc, flag_bits, date_time, comment, extra, create_system, create_version, extract_version, internal_attr, external_attr, is_directory)`.
- `ZipPackageSnapshot(source_sha256, source_size, entries, archive_comment)` with deterministic `entry_by_name` mapping property.
- `ZipParseError(message: str, *, reason: str, details: Mapping[str, object] | None = None)`.
- `snapshot_zip_package(source: bytes, *, limits: ZipRecursiveLimits | None = None) -> ZipPackageSnapshot` validates one archive only; recursion is Task 3.
- `read_zip_member(source: bytes, member_name: str) -> bytes`.
- `build_zip_candidate(snapshot: ZipPackageSnapshot, source: bytes, *, replacements: Mapping[str, bytes], limits: ZipRecursiveLimits | None = None) -> bytes`.

- [ ] **Step 1: Implement immutable limits with constructor validation.**

```python
@dataclass(frozen=True)
class ZipRecursiveLimits:
    max_depth: int = 4
    max_members_per_archive: int = 10_000
    max_global_members: int = 10_000
    max_member_uncompressed_bytes: int = 64 * 1024 * 1024
    max_archive_uncompressed_bytes: int = 512 * 1024 * 1024
    max_global_expanded_bytes: int = 512 * 1024 * 1024
    max_compression_ratio: float = 200.0

    def __post_init__(self) -> None:
        for name in (
            "max_depth",
            "max_members_per_archive",
            "max_global_members",
            "max_member_uncompressed_bytes",
            "max_archive_uncompressed_bytes",
            "max_global_expanded_bytes",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")
        if self.max_compression_ratio <= 0:
            raise ValueError("max_compression_ratio must be > 0")
```

- [ ] **Step 2: Implement package snapshot validation before reading member content.**

Use `zipfile.ZipFile(BytesIO(source), "r")`. Reject unsafe path names, duplicates, encrypted flag `0x1`, Unix symlink mode, unsupported compression, per-member/total/ratio limit violations before storing evidence. Only then read each member and hash uncompressed bytes. Directory entries remain in ordered evidence but cannot be replacement targets.

- [ ] **Step 3: Implement sparse candidate construction.**

Clone `ZipInfo` fields exactly as H7 does, reject source/snapshot mismatch, unknown replacement names, directory targets, non-bytes replacement payloads and output limit overflow. Preserve archive comment and member order. Re-run `snapshot_zip_package(candidate)` before return and require ordered inventory equality.

- [ ] **Step 4: Run focused package tests GREEN.**

```bash
cd packages/markitdown
hatch test -py=3.11 tests/twoways/test_zip_package.py -q
```
Expected: all H8 package tests pass.

- [ ] **Step 5: Commit package authority separately.**

```bash
git add packages/markitdown/src/markitdown/twoways/formats/zip/limits.py packages/markitdown/src/markitdown/twoways/formats/zip/model.py packages/markitdown/src/markitdown/twoways/formats/zip/package.py
git commit -m "feat: add safe H8 ZIP package authority"
```

---

### Task 3: Build explicit two-way adapter registry and recursive parser under shared budgets

**Files:**
- Create: `packages/markitdown/tests/twoways/test_zip_registry.py`
- Create: `packages/markitdown/tests/twoways/test_zip_parser.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/zip/registry.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/zip/parser.py`
- Extend: `packages/markitdown/src/markitdown/twoways/formats/zip/model.py`

**Interfaces:**
- `ZipMemberAdapter(key: str, extensions: frozenset[str], probe: Callable[[bytes, str], bool], read: Callable[[bytes, str], DocumentIR], patch: Callable[[DocumentIR, bytes, Sequence[EditOperation]], bytes], strong_package: bool = False)`.
- `default_zip_member_adapters() -> tuple[ZipMemberAdapter, ...]` returns deterministic priority order.
- Strong package keys first: `epub`, `docx`, `pptx`, `xlsx`; ordinary `zip` is fallback after all strong probes decline.
- `ZipBudgetState(global_members: int = 0, global_expanded_bytes: int = 0)` is mutable internal traversal state, never public API.
- `ZipMemberClassification(state: Literal["typed", "opaque", "ambiguous"], adapter_key: str | None, probes: tuple[str, ...], reason_code: str | None)`.
- `ZipMemberChain(parts: tuple[str, ...])` canonical tuple identity.
- `ZipParsedMember(entry, chain, classification, nested_archive: ParsedZipSource | None, inner_document: DocumentIR | None)`.
- `ParsedZipSource(snapshot, members, depth)`.
- `parse_zip_source(source: bytes, *, filename: str | None = None, limits: ZipRecursiveLimits | None = None, adapters: Sequence[ZipMemberAdapter] | None = None) -> ParsedZipSource`.

- [ ] **Step 1: Add test-only RED for strong package priority and ordinary ZIP fallback.**

```python
def test_epub_package_claims_before_generic_zip() -> None:
    outer = make_zip(members={"book.bin": make_epub()})
    parsed = parse_zip_source(outer)
    member = parsed.member_by_chain[("book.bin",)]
    assert member.classification.state == "typed"
    assert member.classification.adapter_key == "epub"


def test_nested_ordinary_zip_recurses_after_strong_probes_decline() -> None:
    nested = make_zip(members={"note.txt": b"nested\n"})
    parsed = parse_zip_source(make_zip(members={"nested.zip": nested}))
    member = parsed.member_by_chain[("nested.zip",)]
    assert member.classification.adapter_key == "zip"
    assert member.nested_archive is not None
```

- [ ] **Step 2: Add RED for extension/content disagreement and ambiguity.**

```python
def test_misleading_epub_extension_does_not_override_package_evidence() -> None:
    ordinary = make_zip(members={"plain.txt": b"x"})
    parsed = parse_zip_source(make_zip(members={"fake.epub": ordinary}))
    assert parsed.member_by_chain[("fake.epub",)].classification.adapter_key == "zip"


def test_two_non_equivalent_strong_claims_are_ambiguous() -> None:
    adapters = (
        fake_adapter("strong-a", claim=True, strong_package=True),
        fake_adapter("strong-b", claim=True, strong_package=True),
    )
    parsed = parse_zip_source(make_zip(members={"x.bin": b"payload"}), adapters=adapters)
    member = parsed.member_by_chain[("x.bin",)]
    assert member.classification.state == "ambiguous"
    assert member.classification.reason_code == "zip.member.ambiguous_format"
```

- [ ] **Step 3: Add RED for shared recursive budgets.**

```python
def test_global_member_budget_is_shared_across_nested_archives() -> None:
    nested_a = make_zip(members={"a.txt": b"a", "b.txt": b"b"})
    nested_b = make_zip(members={"c.txt": b"c", "d.txt": b"d"})
    source = make_zip(members={"a.zip": nested_a, "b.zip": nested_b})
    limits = ZipRecursiveLimits(max_global_members=4)
    parsed = parse_zip_source(source, limits=limits)
    assert any(d.code == "zip.recursion.member_budget_exceeded" for d in parsed.diagnostics)
```

Depth exhaustion should keep the affected nested member opaque/read-only, not make unrelated safe siblings disappear. Global byte/member budget exhaustion must be deterministic and must not recurse beyond the limit.

- [ ] **Step 4: Commit Task 3 RED tests and observe intended missing-module/API failure.**

```bash
git add packages/markitdown/tests/twoways/test_zip_registry.py packages/markitdown/tests/twoways/test_zip_parser.py
git commit -m "test: define H8 recursive classification contracts"
cd packages/markitdown && hatch test -py=3.11 tests/twoways/test_zip_registry.py tests/twoways/test_zip_parser.py -q
```
Expected: RED because `registry.py` / `parser.py` APIs are missing.

- [ ] **Step 5: Implement adapter registry without using the one-way converter registry.**

Build explicit entries around existing public two-way functions/classes from:
`formats.text`, `csv`, `json`, `xml`, `html`, `ipynb`, `epub`, `docx`, `pptx`, `xlsx`.
For strong package probes, use package-level evidence/readers, not extension alone. The `zip` fallback probe calls `snapshot_zip_package` only after strong probes decline.

- [ ] **Step 6: Implement recursive parser with shared budget object.**

At root create one `ZipBudgetState`; every descent receives the same object. Increment global member count for each encountered entry and global expanded bytes by every regular member's uncompressed size exactly once. Before recursing, enforce `depth < max_depth`. Unsupported non-ZIP files remain `opaque`; classification failure of one member does not invalidate independent safe siblings.

- [ ] **Step 7: Run classification/parser tests GREEN and commit production.**

```bash
cd packages/markitdown
hatch test -py=3.11 tests/twoways/test_zip_registry.py tests/twoways/test_zip_parser.py -q
git add packages/markitdown/src/markitdown/twoways/formats/zip/model.py packages/markitdown/src/markitdown/twoways/formats/zip/registry.py packages/markitdown/src/markitdown/twoways/formats/zip/parser.py
git commit -m "feat: add recursive H8 ZIP classification"
```

---

### Task 4: Build deterministic namespaced archive `DocumentIR` and capabilities

**Files:**
- Create: `packages/markitdown/tests/twoways/test_zip_reader.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/zip/reader.py`

**Interfaces:**
- `read_zip_ir(source: BinaryIO, *, filename: str | None = None, mimetype: str | None = None, limits: ZipRecursiveLimits | None = None) -> DocumentIR`.
- `ZipIRReader(DocumentIRReader)` accepts `.zip` and canonical `application/zip`; compatibility/probe paths must preserve stream position when probing.
- Root `SourceDescriptor(format="zip")`.
- Root `Canvas(kind="archive")`, semantic role `zip-archive`.
- Deterministic namespaced IDs: `sha256(canonical_json(["zip", member_chain, adapter_key, inner_canvas_or_node_id]))`-derived labels.
- Nested canvases preserve original `kind`, `name`, width/height/unit and root topology while getting new deterministic canvas IDs and H8 routing metadata.
- Imported nested nodes preserve payload/semantic role/native locator/provenance/capabilities, but all imported node/canvas/parent/child references are rewritten to namespaced IDs.

- [ ] **Step 1: Add RED for root/archive/member structure and deterministic IDs.**

```python
def test_zip_reader_builds_deterministic_archive_tree() -> None:
    source = make_zip()
    first = read_zip_ir(BytesIO(source), filename="bundle.zip")
    second = read_zip_ir(BytesIO(source), filename="bundle.zip")
    assert first == second
    assert first.source is not None and first.source.format == "zip"
    assert first.canvases[0].kind == "archive"
    assert first.nodes[first.root_node_ids[0]].semantic_role == "zip-archive"
```

- [ ] **Step 2: Add RED for nested multi-canvas preservation.**

Use a small XLSX fixture already available in two-way tests or construct one through the existing fixture helper. Assert each inner worksheet canvas becomes one namespaced outer canvas and its root node remains attached to that canvas; do not flatten all worksheet nodes into the archive canvas.

```python
assert [canvas.kind for canvas in document.canvases].count("worksheet") == inner_sheet_count
assert all(canvas.metadata["zip.member_chain"] == ("book.xlsx",) for canvas in document.canvases if canvas.kind == "worksheet")
```

- [ ] **Step 3: Add RED for capability propagation and ZIP structural read-only behavior.**

```python
def test_nested_json_writable_capability_survives_routing_boundary() -> None:
    source = make_zip(members={"data.json": b'{"name":"Ada"}'})
    document = read_zip_ir(BytesIO(source))
    target = next(node for node in document.nodes.values() if node.metadata.get("json.pointer") == "/name")
    decision = capabilities_for_node(target).for_operation("replace_json_scalar")
    assert decision.state is CapabilityState.WRITABLE
    assert target.metadata["zip.member_chain"] == ("data.json",)


def test_archive_and_member_structure_are_read_only() -> None:
    document = read_zip_ir(BytesIO(make_zip()))
    structure = [n for n in document.nodes.values() if n.semantic_role in {"zip-archive", "zip-member"}]
    assert structure
    assert all(not any(d.state is CapabilityState.WRITABLE for d in capabilities_for_node(n).decisions) for n in structure)
```

- [ ] **Step 4: Commit reader RED tests and observe missing `read_zip_ir` / `ZipIRReader`.**

```bash
git add packages/markitdown/tests/twoways/test_zip_reader.py
git commit -m "test: define H8 ZIP reader contracts"
cd packages/markitdown && hatch test -py=3.11 tests/twoways/test_zip_reader.py -q
```

- [ ] **Step 5: Implement namespaced import helpers and root reader.**

Create helpers `_namespace_canvas_id(chain, adapter_key, inner_canvas_id)`, `_namespace_node_id(...)`, `_import_inner_document(...)`. Preserve all inner node references by building complete old->new maps before materializing nodes/canvases. Add immutable routing metadata keys: `zip.member_chain`, `zip.adapter_key`, `zip.inner_document_id`, `zip.inner_node_id`, `zip.inner_source_sha256`, `zip.inner_source_size`, `zip.identity_markdown=False`.

- [ ] **Step 6: Implement `ZipIRReader` acceptance/probe without consuming stream position.**

Canonical `.zip` / `application/zip` can accept directly; any compatibility probe must save `tell()`, seek to 0, parse, and restore position in `finally`, matching H7's safe probe pattern.

- [ ] **Step 7: Run reader tests GREEN and commit.**

```bash
cd packages/markitdown
hatch test -py=3.11 tests/twoways/test_zip_reader.py -q
git add packages/markitdown/src/markitdown/twoways/formats/zip/reader.py
git commit -m "feat: add recursive H8 ZIP DocumentIR reader"
```

---

### Task 5: Implement fresh routing, transactional recursive writer, and final verifier

**Files:**
- Create: `packages/markitdown/tests/twoways/test_zip_routing.py`
- Create: `packages/markitdown/tests/twoways/test_zip_verification.py`
- Create: `packages/markitdown/tests/twoways/test_zip_writer.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/zip/routing.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/zip/verification.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/zip/writer.py`

**Interfaces:**
- `ZipRoutedEdit(operation: EditOperation, member_chain: tuple[str, ...], adapter_key: str, inner_operation: EditOperation)`.
- `resolve_zip_edit(document: DocumentIR, parsed: ParsedZipSource, edit: EditOperation) -> ZipRoutedEdit`.
- `verify_zip_candidate(original: ParsedZipSource, candidate: bytes, *, requested: Sequence[ZipRoutedEdit], touched_chains: Collection[tuple[str, ...]], limits: ZipRecursiveLimits | None = None) -> ParsedZipSource`.
- `patch_zip(document: DocumentIR, source_stream: BinaryIO, destination: BinaryIO, *, edits: Sequence[EditOperation], limits: ZipRecursiveLimits | None = None) -> WriterResult`.

- [ ] **Step 1: Add routing RED for stale/forged member chains and adapter drift.**

```python
def test_forged_member_chain_fails_before_output() -> None:
    source = make_zip(members={"data.json": b'{"name":"Ada"}'})
    document = read_zip_ir(BytesIO(source))
    target = next(node for node in document.nodes.values() if node.metadata.get("json.pointer") == "/name")
    forged = replace_node_metadata(document, target.node_id, {**target.metadata, "zip.member_chain": ("other.json",)})
    output = BytesIO()
    with pytest.raises(PatchPreconditionError):
        patch_zip(forged, BytesIO(source), output, edits=(replace_json_edit(target.node_id, "Nolane"),))
    assert output.getvalue() == b""
```

Add equivalent tests for stale root SHA/size, stale intermediate nested-member digest, adapter reclassification drift, unknown target, operation not advertised by the fresh inner node, duplicate logical target and contradictory edits.

- [ ] **Step 2: Add writer RED for one-level typed mutation and zero-edit exact identity.**

```python
def test_nested_json_edit_is_target_only_and_transactional() -> None:
    source = make_zip(members={"data.json": b'{"name":"Ada","count":1}\n', "note.txt": b"keep\n"})
    document = read_zip_ir(BytesIO(source))
    target = next(node for node in document.nodes.values() if node.metadata.get("json.pointer") == "/name")
    output = BytesIO()
    result = patch_zip(document, BytesIO(source), output, edits=(replace_json_edit(target.node_id, "Nolane"),))
    candidate = output.getvalue()
    with ZipFile(BytesIO(candidate), "r") as archive:
        assert archive.read("data.json") == b'{"name":"Nolane","count":1}\n'
        assert archive.read("note.txt") == b"keep\n"
    assert result.fidelity.tier == "high"


def test_zip_zero_edit_write_is_exact_source_bytes() -> None:
    source = make_zip()
    document = read_zip_ir(BytesIO(source))
    output = BytesIO()
    result = patch_zip(document, BytesIO(source), output, edits=())
    assert output.getvalue() == source
    assert result.fidelity.tier == "exact-preserve"
```

- [ ] **Step 3: Add recursive propagation RED.**

Create outer ZIP -> nested ZIP -> JSON. Edit JSON scalar and assert only the member-chain archives change while all sibling members at both levels preserve uncompressed SHA exactly. Add a second test with edits in two sibling branches to prove complete-set preflight and deterministic upward propagation.

- [ ] **Step 4: Add rollback RED.**

```python
def test_one_inner_failure_rolls_back_all_sibling_edits() -> None:
    source = two_editable_member_zip()
    document = read_zip_ir(BytesIO(source))
    good, stale = build_good_and_stale_edits(document)
    output = BytesIO()
    with pytest.raises(PatchPreconditionError):
        patch_zip(document, BytesIO(source), output, edits=(good, stale))
    assert output.getvalue() == b""
```

- [ ] **Step 5: Add final verifier RED for unauthorized sibling drift.**

Construct a candidate that contains the requested target edit but also changes an untouched sibling. `verify_zip_candidate` must reject it with `ZipParseError`/verification-specific error and never allow caller emission.

- [ ] **Step 6: Commit Task 5 RED tests and record intended missing-module/API failures.**

```bash
git add packages/markitdown/tests/twoways/test_zip_routing.py packages/markitdown/tests/twoways/test_zip_verification.py packages/markitdown/tests/twoways/test_zip_writer.py
git commit -m "test: define H8 recursive writer contracts"
cd packages/markitdown && hatch test -py=3.11 tests/twoways/test_zip_routing.py tests/twoways/test_zip_verification.py tests/twoways/test_zip_writer.py -q
```

- [ ] **Step 7: Implement fresh edit routing.**

`resolve_zip_edit` must compare the recorded outer document with a fresh recursive parse, walk the exact chain, verify every intermediate member SHA/size, reclassify the terminal bytes, fresh-read the inner document, resolve `zip.inner_node_id`, require matching operation capability, and construct a new inner `EditOperation` targeting the fresh inner node. Preserve operation-specific payload/precondition semantics; H8-only routing preconditions are validated at H8 and not incorrectly forwarded.

- [ ] **Step 8: Implement recursive grouped transaction.**

Group routed edits by terminal member chain. Invoke the selected existing inner patch function into `BytesIO`. For nested ordinary ZIP terminal members, recursion remains H8 and uses the same limit policy. Build a replacement map bottom-up: terminal bytes -> parent sparse candidate -> grandparent sparse candidate -> root candidate. Never write caller destination during this phase.

- [ ] **Step 9: Implement final recursive verifier.**

Fresh-parse candidate with the same limits and require exact root/nested ordered inventory, archive comments, directory entries, untouched member SHA/size and required ZIP metadata. For each requested terminal typed member, require same adapter key and fresh inner semantics. Treat any unauthorized changed chain as failure.

- [ ] **Step 10: Implement `WriterResult` fidelity.**

Zero edits: `exact-preserve`. Mutation: `high` with evidence names at minimum:
`zip.source_authority`, `zip.member_chain_authority`, `zip.inner_writer_verification`, `zip.ordered_inventory`, `zip.untouched_member_content`, `zip.recursive_candidate_reread`, `zip.global_budget_recheck`.

- [ ] **Step 11: Run routing/writer/verifier tests GREEN and commit production.**

```bash
cd packages/markitdown
hatch test -py=3.11 tests/twoways/test_zip_routing.py tests/twoways/test_zip_verification.py tests/twoways/test_zip_writer.py -q
git add packages/markitdown/src/markitdown/twoways/formats/zip/routing.py packages/markitdown/src/markitdown/twoways/formats/zip/verification.py packages/markitdown/src/markitdown/twoways/formats/zip/writer.py
git commit -m "feat: add transactional recursive H8 ZIP writer"
```

---

### Task 6: Public adapter, inspection-only Markdown, and one-way regression lock

**Files:**
- Create: `packages/markitdown/tests/twoways/test_zip_public_imports.py`
- Create: `packages/markitdown/tests/twoways/test_zip_markdown.py`
- Create: `packages/markitdown/tests/twoways/test_zip_oneway_regression.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/zip/writer_adapter.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/zip/__init__.py`
- Modify only if a RED test proves required: smallest existing identity Markdown projection surface; do not create ZIP Markdown importer mutations.
- Protected unchanged: `packages/markitdown/src/markitdown/converters/_zip_converter.py`.

**Interfaces:**
- `ZipPatchWriter(DocumentWriter)` mirrors `EpubPatchWriter`: accepts source format `zip` and target `.zip`/format `zip`; `write` requires `source_stream=` and `edits=`, optionally `limits=`.
- Public facade exports `ZipIRReader`, `ZipPatchWriter`, `ZipRecursiveLimits`, `ZipParseError`, `parse_zip_source`, `patch_zip`, `read_zip_ir`.

- [ ] **Step 1: Add test-only RED public surface.**

```python
def test_zip_public_format_surface() -> None:
    from markitdown.twoways.formats.zip import (
        ZipIRReader,
        ZipParseError,
        ZipPatchWriter,
        ZipRecursiveLimits,
        parse_zip_source,
        patch_zip,
        read_zip_ir,
    )
    assert ZipIRReader and ZipPatchWriter and ZipParseError and ZipRecursiveLimits
    assert parse_zip_source and patch_zip and read_zip_ir
```

- [ ] **Step 2: Add inspection-only Markdown contract.**

Project an H8 document using the existing identity projection path. Assert nested visible content may be rendered deterministically, but ZIP-backed imported nodes carry `zip.identity_markdown=False` and no Markdown importer round trip emits edits targeting nested ZIP content.

- [ ] **Step 3: Add one-way regression lock.**

Lock the protected converter source blob/digest at the H8 base and add a behavior test showing one-way `ZipConverter` still delegates members through normal MarkItDown conversion and skips unsupported member conversions. Do not import H8 two-way registry into `_zip_converter.py`.

- [ ] **Step 4: Commit RED tests and observe missing facade/adapter failure.**

```bash
git add packages/markitdown/tests/twoways/test_zip_public_imports.py packages/markitdown/tests/twoways/test_zip_markdown.py packages/markitdown/tests/twoways/test_zip_oneway_regression.py
git commit -m "test: define H8 public and one-way regression contracts"
cd packages/markitdown && hatch test -py=3.11 tests/twoways/test_zip_public_imports.py tests/twoways/test_zip_markdown.py tests/twoways/test_zip_oneway_regression.py -q
```

- [ ] **Step 5: Implement `ZipPatchWriter` and public facade.**

```python
class ZipPatchWriter(DocumentWriter):
    def accepts(self, document: DocumentIR, target: TargetInfo, **kwargs: Any) -> bool:
        del kwargs
        source_format = document.source.format if document.source is not None else None
        extension = (target.extension or "").lower()
        return source_format == "zip" and (target.format.lower() == "zip" or extension == ".zip")

    def write(self, document: DocumentIR, output: BinaryIO, target: TargetInfo, **kwargs: Any) -> WriterResult:
        del target
        source_stream = kwargs.pop("source_stream", None)
        edits = kwargs.pop("edits", None)
        limits = kwargs.pop("limits", None)
        if source_stream is None or edits is None:
            raise TypeError("ZipPatchWriter.write requires source_stream= and edits=")
        if kwargs:
            raise TypeError(f"unexpected ZIP writer options: {sorted(kwargs)}")
        return patch_zip(document, source_stream, output, edits=tuple(edits), limits=limits)
```

- [ ] **Step 6: Run public/Markdown/one-way tests GREEN and commit.**

```bash
cd packages/markitdown
hatch test -py=3.11 tests/twoways/test_zip_public_imports.py tests/twoways/test_zip_markdown.py tests/twoways/test_zip_oneway_regression.py -q
git add packages/markitdown/src/markitdown/twoways/formats/zip/__init__.py packages/markitdown/src/markitdown/twoways/formats/zip/writer_adapter.py
git commit -m "feat: expose H8 recursive ZIP adapter"
```

---

### Task 7: Security hardening, documentation closure, scope audit, and exact-head completion gate

**Files:**
- Extend only where gaps are proven: `packages/markitdown/tests/twoways/test_zip_package.py`, `test_zip_parser.py`, `test_zip_routing.py`, `test_zip_verification.py`, `test_zip_writer.py`.
- Modify: `TWOWAYS.md`.
- Modify: this implementation plan only before the final gate if execution status needs correction.
- Do not modify protected one-way ZIP converter.

**Interfaces:** No new public API. Task 7 only hardens the approved H8 contract and closes documentation/gates.

- [ ] **Step 1: Run the complete focused H8 suite before adding new hardening tests.**

```bash
cd packages/markitdown
hatch test -py=3.11 \
  tests/twoways/test_zip_package.py \
  tests/twoways/test_zip_registry.py \
  tests/twoways/test_zip_parser.py \
  tests/twoways/test_zip_reader.py \
  tests/twoways/test_zip_routing.py \
  tests/twoways/test_zip_verification.py \
  tests/twoways/test_zip_writer.py \
  tests/twoways/test_zip_public_imports.py \
  tests/twoways/test_zip_markdown.py \
  tests/twoways/test_zip_oneway_regression.py -q
```

- [ ] **Step 2: Audit every spec security boundary and add only missing adversarial tests.**

The audit checklist is exact: nested traversal, absolute/drive/backslash paths, duplicate names, symlink, encryption, BZIP2/LZMA rejection, malformed archive, member limit, per-member bytes, per-archive bytes, global members, global expanded bytes, compression ratio, depth exhaustion, nested bomb, stale chain digest, stale classification, forged routing metadata, duplicate/conflicting edit targets, unauthorized sibling drift, inner failure rollback, final verification rollback. For any uncovered item, first add one focused RED test and observe RED before modifying production.

- [ ] **Step 3: Add `TWOWAYS.md` H8 section before final CI.**

Document: recursive composition, typed inner operations, strong-package priority, global budgets, namespaced nested canvases/nodes, ZIP structure read-only, exact zero-edit identity, high-fidelity mutated archive preservation, inspection-only Markdown, unsupported formats/structural edits, and protected unchanged one-way ZipConverter. Update current capability matrix to include H8 ZIP.

- [ ] **Step 4: Perform exact H7→H8 scope audit.**

```bash
git diff --name-status dbb016db4797c5646e863735764243d0e5c5b2a7...HEAD
```
Expected production changes: only `twoways/formats/zip/*`; shared projection code only if a dedicated RED test forced the minimal change; docs/tests as planned. `_zip_converter.py`, H1-H7 production adapters, and unrelated CLI/registry files must be absent unless explicitly justified by an observed RED compatibility defect.

- [ ] **Step 5: Run fresh pre-commit and full package/OCR matrices on the candidate final head.**

GitHub Actions completion authority must show exactly:

```text
pre-commit: success
package tests 3.10: success
package tests 3.11: success
package tests 3.12: success
package tests 3.13: success
OCR tests 3.10: success
OCR tests 3.11: success
OCR tests 3.12: success
OCR tests 3.13: success
```

- [ ] **Step 6: Freeze exact H8 completion SHA.**

After 9/9 GREEN, do not commit source, tests, plan, or docs to H8. Update PR metadata only, recording exact completion SHA and workflow run IDs. Mark PR ready for review without changing branch SHA.

- [ ] **Step 7: Preserve next-tranche lineage.**

Any PDF/native-safe or later tranche must branch from the exact H8 completion SHA, not an earlier H8 commit and not a post-gate modification.

## Execution Order and Review Gates

1. Task 1 RED -> Task 2 package authority GREEN.
2. Review Task 2 diff and full existing regression signal before recursive work.
3. Task 3 RED -> registry/parser GREEN.
4. Task 4 RED -> reader/namespacing GREEN.
5. Task 5 RED -> routing/writer/verifier GREEN.
6. Task 6 RED -> public/projection/one-way regression GREEN.
7. Task 7 hardening/docs/scope -> exact final-head 9/9 gate.

At every task boundary, use fresh verification evidence and inspect the actual branch diff before claiming success. A prior GREEN run never substitutes for the current exact head.
