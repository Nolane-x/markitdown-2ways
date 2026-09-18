# Phase H18 — Wikipedia Remote-Derived Snapshot Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, read-only `DocumentIR` parity for already-materialized Wikipedia HTML snapshots while proving the derived Markdown has no native or remote writeback authority.

**Architecture:** H18 adds one small reader module under `markitdown.twoways.readers.remote`. It captures bounded snapshot bytes, validates that the supplied `StreamInfo.url` is owned by the existing `WikipediaConverter`, derives Markdown from a private `BytesIO`, and maps the result to one deterministic derived text node. The reader records versioned remote-snapshot evidence and explicit `CapabilityState.DERIVED`; it adds no writer, performs no network I/O, does not alter `DocumentIR` schema, and leaves the one-way Wikipedia converter byte-for-byte unchanged.

**Tech Stack:** Python stdlib (`dataclasses`, `hashlib`, `io`, `urllib.parse`) plus existing MarkItDown `StreamInfo`, `WikipediaConverter`, `DocumentIR`, capability kernel and canonical serialization APIs; pytest for tests.

**Spec:** `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h18-wikipedia-remote-derived-snapshot-parity-design.md`

## Global Constraints

- Base authority is `main@98d22412fdf99b87eaea33aa6413a5f0e408d4f8`.
- Existing one-way Wikipedia converter blob must remain `ba0c751092fa9e37fcf982f1fae9c4dcd774e049`.
- H18 performs no HTTP request, DNS lookup, socket operation, browser action or subprocess.
- H18 accepts only already-materialized snapshot bytes plus `StreamInfo`.
- H18 supports only current one-way Wikipedia ownership; it must not broaden accepted Wikipedia URL shapes.
- Root semantic text is derived, never native-writable.
- `replace_text` capability state is `DERIVED` with reason `remote.source.not_native_writable`.
- No native locator is emitted for canvas or root node.
- No writer, remote writeback API or writer-registry entry is added.
- No `DocumentIR` schema-version bump.
- Source bytes are bounded by `RemoteDerivedLimits.max_source_bytes`.
- Derived Markdown is bounded by UTF-8 byte size using `RemoteDerivedLimits.max_markdown_utf8_bytes`.
- Production implementation may invoke the existing `WikipediaConverter` on private bytes but never `MarkItDown.convert_uri()` or another network-capable path.
- Public parity tests use `MarkItDown().convert_stream(...)` as the semantic oracle.
- Final completion requires exact final-head pre-commit + package/OCR Python 3.10–3.13 = 9/9 GREEN, exact scope audit, synthetic merge-tree equality and guarded merge.

---

### Task 1: Limits and remote-derived evidence helpers

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/readers/remote.py`
- Test: `packages/markitdown/tests/twoways/test_remote_wikipedia_reader.py`

**Interfaces:**
- Produces: `RemoteDerivedLimits`
- Produces internal helpers: bounded source capture, URL ownership validation, deterministic evidence hashing.
- Later tasks consume `RemoteDerivedLimits` and `read_wikipedia_snapshot_ir`.

- [ ] **Step 1: Write RED tests for limit validation**

Add tests equivalent to:

```python
@pytest.mark.parametrize(
    "kwargs",
    (
        {"max_source_bytes": 0},
        {"max_source_bytes": -1},
        {"max_source_bytes": True},
        {"max_markdown_utf8_bytes": 0},
        {"max_markdown_utf8_bytes": False},
    ),
)
def test_remote_derived_limits_require_positive_non_bool_integers(kwargs):
    with pytest.raises((TypeError, ValueError)):
        RemoteDerivedLimits(**kwargs)
```

Also test defaults are exactly 32 MiB source and 16 MiB Markdown.

- [ ] **Step 2: Run RED**

Run:

```bash
pytest -q packages/markitdown/tests/twoways/test_remote_wikipedia_reader.py
```

Expected: collection/import failure because `markitdown.twoways.readers.remote` does not exist.

- [ ] **Step 3: Implement minimal immutable limits model**

Create:

```python
@dataclass(frozen=True)
class RemoteDerivedLimits:
    max_source_bytes: int = 32 * 1024 * 1024
    max_markdown_utf8_bytes: int = 16 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in ("max_source_bytes", "max_markdown_utf8_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
```

Do not add URL fetching or public exports yet.

- [ ] **Step 4: Run focused tests**

Run the Task 1 test subset. Expected: limit tests pass; reader tests not yet present.

- [ ] **Step 5: Commit**

Commit message:

```text
H18: add remote-derived reader limits
```

---

### Task 2: Wikipedia snapshot reader parity and deterministic IR

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/readers/remote.py`
- Test: `packages/markitdown/tests/twoways/test_remote_wikipedia_reader.py`
- Read-only oracle: `packages/markitdown/tests/test_files/test_wikipedia.html`

**Interfaces:**
- Produces:
  `read_wikipedia_snapshot_ir(source_stream: BinaryIO, *, stream_info: StreamInfo, limits: RemoteDerivedLimits | None = None) -> DocumentIR`
- Uses existing `WikipediaConverter.accepts()` and `WikipediaConverter.convert()` on private `BytesIO`.
- Emits one `Canvas(kind="remote-derived")` and one `Node(kind="text", semantic_role="derived_document")`.

- [ ] **Step 1: Write RED happy-path/parity tests**

Load `test_wikipedia.html`, use:

```python
info = StreamInfo(
    url="https://en.wikipedia.org/wiki/Microsoft",
    mimetype="text/html",
    extension=".html",
    filename="Microsoft.html",
    charset="utf-8",
)
```

Assert:

- one canvas, one root node;
- source format `remote-wikipedia-snapshot`;
- source URI is exact supplied URL;
- source SHA-256 and size match exact fixture bytes;
- root payload text equals public oracle:

```python
MarkItDown().convert_stream(BytesIO(snapshot), stream_info=info).markdown
```

- title matches one-way result title;
- repeated reads have identical canonical JSON bytes/digest.

- [ ] **Step 2: Write RED deterministic-evidence tests**

Assert `DocumentMetadata.custom["twoways.remote_snapshot.v1"]` contains exactly stable descriptive fields required by spec:

```python
{
    "kind": "wikipedia",
    "uri": info.url,
    "source_sha256": sha256(snapshot).hexdigest(),
    "source_size_bytes": len(snapshot),
    "converter": "WikipediaConverter",
    "converter_blob_sha": "ba0c751092fa9e37fcf982f1fae9c4dcd774e049",
    "markdown_sha256": sha256(markdown.encode("utf-8")).hexdigest(),
    "markdown_utf8_size_bytes": len(markdown.encode("utf-8")),
    "network_performed_by_twoways": False,
}
```

Optional source hints must be deterministic if included.

- [ ] **Step 3: Run RED**

Expected: reader function missing.

- [ ] **Step 4: Implement bounded source capture**

Read at most `max_source_bytes + 1`; if one byte over limit, raise a deterministic `ValueError` before constructing `DocumentIR`. Never retain or process unbounded input.

- [ ] **Step 5: Implement URL/ownership validation**

Use `urllib.parse.urlsplit` only for structural validation:

- URL is required;
- scheme exactly `http` or `https`;
- hostname non-empty;
- username/password absent.

Then instantiate `WikipediaConverter` and require:

```python
converter.accepts(BytesIO(snapshot), stream_info) is True
```

This call is the ownership authority; do not broaden the converter regex.

- [ ] **Step 6: Derive Markdown without network access**

Call:

```python
result = converter.convert(BytesIO(snapshot), stream_info)
```

Apply the same public one-way normalization used by `MarkItDown._convert`:

```python
markdown = "\n".join(line.rstrip() for line in re.split(r"\r?\n", result.markdown))
markdown = re.sub(r"\n{3,}", "\n\n", markdown)
```

Measure `markdown.encode("utf-8")` against output limit.

- [ ] **Step 7: Build deterministic IDs and IR**

Seed `DocumentIdFactory` with a stable string containing format, URI, source SHA, Markdown SHA and converter identity. Create:

- `SourceDescriptor(format="remote-wikipedia-snapshot", ...)`
- one `Canvas(kind="remote-derived")`
- one root `Node(kind="text", semantic_role="derived_document")`
- `TextPayload(text=markdown)`
- no native locator anywhere.

Create provenance:

```python
Provenance(
    source_format="remote-wikipedia-snapshot",
    extraction_method="WikipediaConverter",
    metadata={
        "uri": uri,
        "source_sha256": source_sha,
        "markdown_sha256": markdown_sha,
        "remote_writeback": False,
    },
)
```

- [ ] **Step 8: Run focused GREEN**

Run the reader test module. Expected: happy-path/evidence/determinism tests pass.

- [ ] **Step 9: Commit**

Commit message:

```text
H18: add deterministic Wikipedia snapshot reader
```

---

### Task 3: Derived capability, diagnostics and canonical serialization

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/readers/remote.py`
- Test: `packages/markitdown/tests/twoways/test_remote_wikipedia_reader.py`
- Create: `packages/markitdown/tests/twoways/test_remote_wikipedia_public_imports.py`

**Interfaces:**
- Root node capability metadata is generated internally via `encode_capabilities`.
- No caller-supplied capability input exists.
- Canonical JSON round trip must preserve the derived state and evidence.

- [ ] **Step 1: Write RED capability tests**

Assert root node:

```python
decision = capabilities_for_node(node).for_operation("replace_text")
assert decision.state is CapabilityState.DERIVED
assert decision.reason_code == "remote.source.not_native_writable"
assert decision.constraints == {
    "identity_markdown": False,
    "remote_writeback": False,
    "native_owner": False,
    "materialization": "explicit-local-only",
}
```

Assert capability report has one derived node, zero writable nodes and empty writable-by-operation map.

- [ ] **Step 2: Write RED diagnostic/provenance tests**

Assert one deterministic info diagnostic with code `remote.source.not_native_writable`. Assert canvas and node native locators are `None`. Assert provenance explicitly says `remote_writeback=False`.

- [ ] **Step 3: Write RED serialization test**

```python
encoded = canonical_json_bytes(document)
decoded = decode_document(encoded)
assert canonical_json_bytes(decoded) == encoded
assert build_capability_report(decoded) == build_capability_report(document)
```

Schema version must remain `0.1.0`.

- [ ] **Step 4: Implement capability + diagnostic generation**

Use existing capability kernel only; no enum/schema changes.

- [ ] **Step 5: Run focused GREEN**

Run reader test module and public-import test module.

- [ ] **Step 6: Commit**

Commit message:

```text
H18: lock derived capability and provenance semantics
```

---

### Task 4: Adversarial URL, budget and network-firewall court

**Files:**
- Modify: `packages/markitdown/tests/twoways/test_remote_wikipedia_reader.py`
- Modify only if RED proves a gap: `packages/markitdown/src/markitdown/twoways/readers/remote.py`

**Interfaces:**
- Reader must fail before producing an IR for unsupported provenance.
- No tests perform live network I/O.

- [ ] **Step 1: Add RED URL adversarial matrix**

Reject:

- missing URL;
- `file:`, `data:`, `ftp:`;
- `https://example.com/wiki/X`;
- `https://wikipedia.org.example.com/wiki/X`;
- `https://user:secret@en.wikipedia.org/wiki/X`;
- malformed/empty host;
- URL shapes rejected by existing `WikipediaConverter`.

Accept only current converter-owned two/three-letter language Wikipedia hosts.

- [ ] **Step 2: Add RED source-limit boundaries**

Test exact limit succeeds and one byte above fails.

Use a custom stream that records maximum bytes requested/read so bounded capture cannot accidentally call unrestricted `.read()`.

- [ ] **Step 3: Add RED Markdown-limit boundaries**

Use small synthetic Wikipedia HTML whose normalized derived Markdown size is measured exactly. Verify exact budget succeeds and one byte smaller than needed fails.

- [ ] **Step 4: Add structural network-firewall test**

Inspect `markitdown.twoways.readers.remote` source or AST and assert it imports none of:

- `requests`;
- `httpx`;
- `urllib.request`;
- `socket`;
- `subprocess`.

Also monkeypatch common network entry points during reader invocation where practical and assert no call occurs.

- [ ] **Step 5: Run RED and classify**

Any failure that shows unsupported URL/budget/network behavior is a production gap. Fix only the proven gap.

- [ ] **Step 6: Run GREEN**

Run full remote Wikipedia test module; require zero failures.

- [ ] **Step 7: Commit**

Commit message:

```text
H18 hardening: close remote provenance and budget gaps
```

---

### Task 5: Public exports, one-way invariance and documentation

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/readers/__init__.py`
- Modify: `packages/markitdown/src/markitdown/twoways/__init__.py`
- Modify: `packages/markitdown/tests/twoways/test_remote_wikipedia_public_imports.py`
- Modify: `TWOWAYS.md`

**Interfaces:**
- Public exports:
  - `RemoteDerivedLimits`
  - `read_wikipedia_snapshot_ir`
- No writer export or registry entry.

- [ ] **Step 1: Write RED public-import tests**

Assert both symbols are importable from `markitdown.twoways.readers.remote`, `markitdown.twoways.readers`, and top-level `markitdown.twoways` without loading optional heavy dependencies.

- [ ] **Step 2: Write RED one-way regression**

Use `test_wikipedia.html` and the existing one-way path. Assert one-way Markdown/title behavior remains unchanged. Record final blob equality for `_wikipedia_converter.py`.

- [ ] **Step 3: Add explicit no-writer assertions**

Assert no `patch_wikipedia`, `write_remote` or remote writer public symbol exists; derived node has no writable operations.

- [ ] **Step 4: Implement public exports**

Export only the two approved reader symbols.

- [ ] **Step 5: Update `TWOWAYS.md`**

Document:

- v0.9 H18 start;
- materialized Wikipedia snapshot only;
- derived root node;
- no network inside 2Ways;
- no remote/native writeback;
- source/result digests and URI provenance;
- future H19+ adapters reuse the evidence model without assuming identical provenance topology.

Do not claim Wikipedia editing support.

- [ ] **Step 6: Run focused GREEN**

Run remote reader/public tests and existing Wikipedia one-way tests.

- [ ] **Step 7: Commit**

Commit message:

```text
H18: expose and document Wikipedia derived snapshot parity
```

---

### Task 6: Final closure, exact court and guarded integration

**Files:**
- No new production scope.
- Update PR #34 body only after exact evidence exists.

**Interfaces:**
- Frozen final branch head and tree are the only merge authority.

- [ ] **Step 1: Scope audit**

PR changed files must be limited to:

- H18 spec;
- H18 plan;
- `readers/remote.py`;
- `readers/__init__.py`;
- top-level `twoways/__init__.py`;
- H18 tests;
- `TWOWAYS.md`.

No one-way converter, registry, HTTP layer, writer or schema file may change.

- [ ] **Step 2: Verify one-way converter blob**

Require exact blob:

```text
ba0c751092fa9e37fcf982f1fae9c4dcd774e049
```

for `packages/markitdown/src/markitdown/converters/_wikipedia_converter.py`.

- [ ] **Step 3: Run exact final-head court**

On the frozen final SHA require:

- pre-commit SUCCESS;
- package Python 3.10 SUCCESS;
- package Python 3.11 SUCCESS;
- package Python 3.12 SUCCESS;
- package Python 3.13 SUCCESS;
- OCR Python 3.10 SUCCESS;
- OCR Python 3.11 SUCCESS;
- OCR Python 3.12 SUCCESS;
- OCR Python 3.13 SUCCESS.

Result must be exact 9/9 GREEN.

Record Python 3.13 package pass/skip/warning totals and OCR total.

- [ ] **Step 4: Update PR provenance**

Record:

- base SHA/tree;
- final head SHA/tree;
- RED→GREEN checkpoints;
- adversarial/network-firewall evidence;
- one-way converter blob;
- changed-file audit;
- exact 9/9 run IDs and Python 3.13 totals.

- [ ] **Step 5: Synthetic merge proof**

Require PR synthetic merge parents equal current `main` plus exact final H18 head. Require synthetic merge tree SHA equal final branch tree SHA exactly.

- [ ] **Step 6: Mark ready and guarded merge**

Use merge-commit semantics and exact `expected_head_sha`.

- [ ] **Step 7: Post-merge verification**

Require:

- `main` points to returned merge commit;
- parents are previous main + exact H18 head;
- main tree equals H18 final tree;
- Wikipedia one-way converter blob remains unchanged.

Only then declare H18 integrated and select H19 from the v0.9 sequence.
