# Phase H6 IPYNB Source Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add conservative source-preserving two-way Jupyter Notebook editing for existing markdown/code/raw cell source text while preserving all unrelated notebook JSON bytes and leaving the one-way IPYNB converter unchanged.

**Architecture:** H6 is a notebook-semantic layer over the exact-green H3 JSON engine. H6 owns notebook validation, deterministic IR, capability/precondition checks, logical source repartition and notebook-semantic candidate verification; H3 `patch_json` remains the lower layer that performs exact scalar lexical patches, source encoding, untouched-byte proof and strict JSON candidate re-read. H6 never serializes an entire notebook and never writes caller output until both H3 and H6 verification pass.

**Tech Stack:** Python 3.10+, existing MarkItDown 2Ways IR/capability/readers/writers framework, H1 reversible text codec, H3 strict JSON lexical reader/writer, stdlib `json`, `BytesIO`, pytest, pre-commit/Black 23.7.0, GitHub Actions Python 3.10-3.13 package/OCR matrices.

**Spec:** `docs/superpowers/specs/2026-09-13-markitdown-2ways-phase-h6-ipynb-source-preservation-design.md`

## Global Constraints

- H6 starts from exact-green H5 `f1b7076ba66aa0d15710f262ea1effd3b3192b38` and stays isolated on `phase-h6-ipynb-source-preservation`.
- Existing one-way `packages/markitdown/src/markitdown/converters/_ipynb_converter.py`, converter registry, CLI and one-way public API remain unchanged.
- H3 JSON production code remains unchanged unless a test proves an H3 bug independent of H6; H6 should compose H3 rather than refactor it.
- No whole-notebook serializer is a production write path.
- No notebook execution, kernel launch, JavaScript execution, network access or subprocess path.
- H6 writable scope is only existing markdown/code/raw cell source text.
- Cell structure, cell type/id/metadata, outputs, execution counts, attachments, notebook metadata and nbformat fields remain read-only.
- Empty `source: []` arrays remain read-only because populating them requires structural mutation.
- Identity Markdown is inspection-only for H6 native-source text.
- Destination emission occurs only after source authority, fresh notebook evidence, H3 JSON proof and H6 notebook-semantic candidate verification all pass.
- Exact final head must pass standard pre-commit plus package and OCR tests on Python 3.10, 3.11, 3.12 and 3.13.

---

### Task 1: Strict notebook model, parser and deterministic IR

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/ipynb/__init__.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/ipynb/model.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/ipynb/parser.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/ipynb/reader.py`
- Test: `packages/markitdown/tests/twoways/test_ipynb_reader.py`
- Test: `packages/markitdown/tests/twoways/test_ipynb_parser.py`

**Interfaces:**
- Consumes `decode_text_source`, H3 `scan_json_text`, `stable_digest`, `DocumentIR`, capability metadata contracts.
- Produces `IpynbParseError`, immutable `IpynbCellEvidence` / `ParsedIpynbSource`, `parse_ipynb_source(source: bytes, *, encoding: str | None = None) -> ParsedIpynbSource`, `read_ipynb_ir(...) -> DocumentIR` and `IpynbIRReader`.

- [ ] **Step 1: Write RED strict parser/model tests**

Create parser tests covering one string-source markdown cell, one list-source code cell, raw cell, cell id, outputs/execution count/attachments/metadata preservation evidence, exact RFC6901 source pointers and exact source lexical spans.

Representative test:

```python
def test_parses_nbformat4_source_evidence_without_normalizing_json() -> None:
    source = (
        b'{"cells":[{"cell_type":"code","execution_count":7,'
        b'"metadata":{"tag":"x"},"outputs":[{"output_type":"stream","text":["ok\\n"]}],' 
        b'"source":["print(1)\\n","print(2)"]}],"metadata":{"title":"N"},'
        b'"nbformat":4,"nbformat_minor":5}'
    )
    parsed = parse_ipynb_source(source)
    cell = parsed.cells[0]
    assert parsed.nbformat == 4
    assert parsed.nbformat_minor == 5
    assert cell.cell_type == "code"
    assert cell.source_pointer == "/cells/0/source"
    assert cell.source_representation == "string-array"
    assert cell.source_segment_pointers == (
        "/cells/0/source/0",
        "/cells/0/source/1",
    )
    assert cell.logical_source == "print(1)\nprint(2)"
```

- [ ] **Step 2: Write RED malformed/notebook-version tests**

Reject malformed nbformat-4 shapes: non-object root, bool/incompatible `nbformat`, missing/non-array `cells`, non-object cell, non-string `cell_type`, source neither string nor array, source array containing non-string. Confirm duplicate JSON object keys already fail through H3 lexical parsing.

A syntactically valid notebook with `nbformat != 4` must parse enough to report `writable_version=False` and deterministic reason `ipynb.nbformat.unsupported_version`, not invent cell write locators.

- [ ] **Step 3: Write RED deterministic reader tests**

Assert:

- `SourceDescriptor(format="ipynb")`, SHA-256, byte size and preserved source ref;
- one `Canvas(kind="notebook")`;
- root `group` role `ipynb-notebook`;
- ordered cell `group` nodes;
- one source `text` child per valid cell;
- `TextPayload.text` equals logical joined source;
- source node native locator backend `ipynb`, object `cell-source`, exact path;
- deterministic node ids and canonical document digest;
- `text.native_source=True`;
- cell/non-source/top-level evidence metadata.

For unsupported nbformat, assert exactly one document-level `unknown_native` read-only root and no fine-grained cell/source nodes.

- [ ] **Step 4: Write RED capability boundary tests**

Supported markdown/code/raw non-empty string/string-array sources are writable for `replace_ipynb_cell_source` only when byte-roundtrippable. Unknown cell type, empty source array and non-roundtrippable source are read-only with exact reason codes from the spec. Root/cell structure is read-only.

- [ ] **Step 5: Write RED reader acceptance/probe tests**

`IpynbIRReader.accepts` must:

- accept `.ipynb` case-insensitively;
- accept `application/x-ipynb+json`;
- accept `application/json` only when a non-destructive probe sees a valid notebook object containing integer `nbformat`, integer `nbformat_minor` and array `cells`;
- reject ordinary JSON;
- restore the source stream position after probing.

- [ ] **Step 6: Commit the tests alone and observe CI RED**

Expected failure is collection/import failure because `markitdown.twoways.formats.ipynb` production modules do not yet exist. Do not write production before this RED is observed.

- [ ] **Step 7: Implement immutable notebook evidence and strict parser**

Use H1 `decode_text_source` and H3 `scan_json_text`; map lexical nodes by RFC6901 pointer. Decode notebook semantics with strict stdlib JSON only after H3 lexical validation. Compute deterministic top-level non-cells and per-cell non-source digests using `stable_digest`; never rely on dictionary serialization for output.

- [ ] **Step 8: Implement deterministic IR and reader acceptance**

Fine-grained nbformat-4 IR follows the spec exactly. Unsupported nbformat emits only a read-only document root. Malformed nbformat-4 input raises `IpynbParseError`. The reader's application/json probe reads/restores the stream and never mutates it.

- [ ] **Step 9: Run focused Task 1 suites GREEN and one full package Python job**

Run the focused parser/reader tests, then obtain one complete package CI success before Task 2.

- [ ] **Step 10: Commit Task 1 production**

Commit only after focused tests and at least one full package job are green.

---

### Task 2: Edit registration, source authority, preflight and shadow-JSON lowering

**Files:**
- Modify: `packages/markitdown/src/markitdown/twoways/ir/edits.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/ipynb/lowering.py`
- Create: `packages/markitdown/src/markitdown/twoways/formats/ipynb/writer.py`
- Test: `packages/markitdown/tests/twoways/test_ipynb_writer.py`
- Test: `packages/markitdown/tests/twoways/test_ipynb_lowering.py`

**Interfaces:**
- Consumes Task 1 `read_ipynb_ir` / parsed evidence, H3 `read_json_ir` / `patch_json`, standard `EditOperation` / `EditPrecondition`.
- Produces edit type `replace_ipynb_cell_source`, `repartition_cell_source(value: str, segment_count: int) -> tuple[str, ...]`, internal lowering helpers, and `patch_ipynb(...) -> WriterResult` up through preflight/lowering.

- [ ] **Step 1: Write RED edit-registration and zero-edit/source-authority tests**

Assert the new edit type can be constructed/serialized under the shared registry, zero edits write byte-identical source, and SHA/size/source-format mismatch fails before caller output.

- [ ] **Step 2: Write RED forged native-evidence tests**

Independently forge root/cell/source index, type, id, non-source digest, source pointer, source representation, segment pointers, segment raw digests, source span, parent/children and native locator. Each must fail before H3 candidate construction.

- [ ] **Step 3: Write RED edit-preflight tests**

Reject:

- wrong edit type;
- missing/unknown target;
- root/cell rather than source target;
- read-only unknown cell / empty source array / non-roundtrip target;
- payload keys other than exactly `value`;
- non-string value;
- duplicate logical targets;
- semantic no-op;
- stale expected semantic digest;
- stale native-locator digest;
- stale expected old value.

Assert caller destination remains empty for every failure.

- [ ] **Step 4: Write RED deterministic repartition tests**

For `segment_count=3`, cover fewer/equal/more physical lines and empty requested text. Assert exact cardinality and join invariant.

Representative checks:

```python
assert repartition_cell_source("a\nb\n", 3) == ("a\n", "b\n", "")
assert repartition_cell_source("a\nb\nc\nd", 2) == ("a\n", "b\nc\nd")
assert repartition_cell_source("", 2) == ("", "")
```

Reject `segment_count < 1`.

- [ ] **Step 5: Write RED shadow-lowering tests**

For a single-string source, one H6 edit lowers to one H3 `replace_json_scalar` target. For list-source, lower only changed existing string segments while preserving array cardinality. Multi-cell H6 edits lower deterministically in cell/segment order.

- [ ] **Step 6: Observe RED before registration/writer/lowering production**

Expected failures include absent edit registry name and missing `ipynb.lowering` / `ipynb.writer`.

- [ ] **Step 7: Register exactly one H6 edit name**

Add only `replace_ipynb_cell_source` to `INITIAL_EDIT_TYPES`.

- [ ] **Step 8: Implement source authority and fresh H6 native-evidence validation**

Re-read the exact source bytes through `read_ipynb_ir` under the recorded encoding and compare public H6 IR evidence against the fresh model before accepting edits.

- [ ] **Step 9: Implement all-edit preflight and deterministic repartition**

Validate full edit set before any H3 call. Return a canonical requested map keyed by cell index/source path. No caller output occurs yet.

- [ ] **Step 10: Implement shadow JSON lowering**

Build `read_json_ir(BytesIO(source), ...)` from the exact bytes and resolve each segment pointer to its shadow JSON string node. Lower only scalar string changes to internal `replace_json_scalar` operations. H6 caller preconditions are not copied into shadow edits; H3 independently validates the freshly constructed shadow IR against the same source.

- [ ] **Step 11: Run Task 2 focused suites GREEN and commit**

Do not yet write caller output for mutating edits until Task 3 verification is integrated.

---

### Task 3: Transactional H3 composition, notebook candidate verifier and preservation proof

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/ipynb/verification.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/ipynb/writer.py`
- Test: `packages/markitdown/tests/twoways/test_ipynb_verification.py`
- Test: `packages/markitdown/tests/twoways/test_ipynb_preservation.py`

**Interfaces:**
- Consumes Task 2 lowered H3 edits and H3 `patch_json`.
- Produces `verify_ipynb_candidate(...)` and final transactional `patch_ipynb` that writes caller output only after H3 + H6 verification.

- [ ] **Step 1: Write RED requested-source and structural-drift verifier tests**

Fault-inject candidate changes and require `RoundTripVerificationError` for:

- wrong requested logical source;
- changed nbformat/minor;
- top-level metadata drift;
- cell count/order drift;
- cell type/id drift;
- execution count drift;
- outputs drift;
- cell metadata drift;
- attachments drift;
- source representation string <-> array drift;
- source-array cardinality drift.

- [ ] **Step 2: Write RED unrequested-source raw-preservation tests**

For unrequested cells require identical logical source and identical ordered source-segment raw digests. Demonstrate that character-reference/escape spelling in an unrequested JSON string cannot drift.

- [ ] **Step 3: Write RED target-only preservation integration tests**

Patch markdown/code/raw source cells and assert:

- candidate parses as strict notebook JSON;
- requested logical source is exact;
- notebook metadata, outputs, execution count, attachments and unrelated cells remain byte/token-preserved through H3 proof;
- list-source array cardinality stays constant;
- multiple requested cells can be changed atomically;
- an unencodable requested replacement fails with empty caller output.

- [ ] **Step 4: Write RED H3 fault-propagation/transaction test**

Monkeypatch or fault-inject the H3 call/candidate verifier to fail after lowering and assert H6 caller output is still empty. H3 must write only to internal `BytesIO`.

- [ ] **Step 5: Observe RED because H6 verifier/final transaction is absent**

- [ ] **Step 6: Implement notebook candidate verifier**

Re-read candidate through `read_ipynb_ir` under the source encoding, compare immutable notebook/cell evidence and requested/unrequested source contracts exactly as specified.

- [ ] **Step 7: Integrate H3 transactional composition**

Call H3 `patch_json` with an internal `BytesIO`. If H3 succeeds, run H6 verifier. Only after verifier success call caller `output.write(candidate)`.

- [ ] **Step 8: Emit H6 fidelity evidence**

Zero-edit: `ipynb.source_authority`, `ipynb.zero_edit_identity` with exact-preserve tier.

Mutation: `ipynb.source_authority`, `ipynb.native_evidence`, `ipynb.json_scalar_lowering`, `ipynb.untouched_bytes`, `ipynb.candidate_reread` with high tier.

- [ ] **Step 9: Run focused preservation/verifier suites plus full package regression GREEN; commit**

---

### Task 4: Public adapter, identity-Markdown boundary and one-way regression

**Files:**
- Create: `packages/markitdown/src/markitdown/twoways/formats/ipynb/writer_adapter.py`
- Modify: `packages/markitdown/src/markitdown/twoways/formats/ipynb/__init__.py`
- Test: `packages/markitdown/tests/twoways/test_ipynb_public_imports.py`
- Test: `packages/markitdown/tests/twoways/test_ipynb_markdown_bridge.py`
- Test: `packages/markitdown/tests/twoways/test_ipynb_oneway_regression.py`

**Interfaces:**
- Produces stable public `IpynbIRReader`, `IpynbPatchWriter`, `read_ipynb_ir`, `patch_ipynb` surface.

- [ ] **Step 1: Write RED public-import/writer-adapter tests**

Verify imports and adapter acceptance only for IPYNB-backed documents plus target `ipynb` / `.ipynb`. `write` requires both `source_stream=` and `edits=` and rejects unknown kwargs with deterministic error text.

- [ ] **Step 2: Write identity-Markdown inspection-only tests**

Project a notebook containing markdown/code/raw cells in identity mode. Assert source text appears, all source blocks have `editable_capabilities == ()`, and unchanged identity import emits no edits.

- [ ] **Step 3: Write current one-way regression tests**

Lock current `IpynbConverter` behavior for `.ipynb`, JSON MIME notebook probe, markdown/code/raw rendering and metadata-title precedence. Assert protected one-way file is not changed by H6 diff.

- [ ] **Step 4: Observe RED for absent public adapter/exports**

- [ ] **Step 5: Implement minimal adapter and exports only**

Do not modify `_ipynb_converter.py`, one-way registry or CLI.

- [ ] **Step 6: Run public/Markdown/one-way focused suites and package/OCR regression GREEN; commit**

---

### Task 5: Documentation, scope audit, formatter cleanup and exact-head completion gate

**Files:**
- Modify: `TWOWAYS.md`
- Modify only before final gate: H6 code/tests if Black 23.7.0 requires formatting.

**Interfaces:**
- Produces the exact-green H6 IPYNB completion point ready for the later EPUB tranche.

- [ ] **Step 1: Update `TWOWAYS.md` with proven H6 boundary**

Document direct typed cell-source editing, string/list-source behavior, empty-array/structure read-only boundaries, H3 lowering proof, notebook candidate verification, identity Markdown inspection-only and unchanged one-way behavior.

- [ ] **Step 2: Audit H5..H6 diff for scope creep**

Require:

- only H6 docs/code/tests plus exactly one shared edit registry entry;
- no `_ipynb_converter.py` change;
- no H3 JSON production change;
- no one-way registry/API/CLI change;
- no EPUB/ZIP work mixed into H6;
- no notebook execution/network/subprocess path.

- [ ] **Step 3: Run standard pre-commit on proposed final head**

If Black modifies files, capture the exact Black 23.7.0 output, commit only formatter changes, and ensure any temporary diagnostic mechanism is fully restored before final verification.

- [ ] **Step 4: Run package tests Python 3.10-3.13 on the same exact head**

All four package jobs must be success.

- [ ] **Step 5: Run OCR tests Python 3.10-3.13 on the same exact head**

All four OCR jobs must be success.

- [ ] **Step 6: Record H6 completion only after exact-head 9/9 GREEN**

One successful standard pre-commit job plus all eight package/OCR jobs must belong to the same exact branch head SHA. Add no commit after that green head.

## Completion gate

H6 is complete only when the exact final branch head is green across all nine required checks, with standard pre-commit configuration present and H5 unchanged. The next EPUB tranche starts from that exact H6 completion point on a new branch; recursive ZIP follows on another branch.