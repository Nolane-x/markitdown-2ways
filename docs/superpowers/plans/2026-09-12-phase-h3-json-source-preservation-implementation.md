# Phase H3 JSON Source Preservation Implementation Plan

> Execute with TDD. H3 starts from exact-head-green H2 `1824ec26945af2aa924b8fe9699d70ae711187ee` and remains stacked until H2 integration is resolved.

**Goal:** Replace existing strict-JSON scalar values by exact lexical source spans while preserving all unrelated source bytes, hierarchy and representation.

**Spec:** `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h3-json-source-preservation-design.md`

**Status:** Tasks 1-7 are functionally complete and matrix-green. Task 8 documentation and scope review are complete; final exact-head CI verification remains the completion gate.

## Global constraints

- Existing one-way `PlainTextConverter` JSON behavior stays unchanged.
- No whole-document serializer or pretty printer.
- No JSONL/NDJSON.
- No object/array/key structural edits.
- Duplicate keys and JSON extensions fail closed.
- Identity Markdown remains read-only.
- Destination emission occurs only after source proof, untouched-byte proof and candidate re-read verification.
- Exact-head pre-commit + package/OCR Python 3.10-3.13 are required before completion.

## Task 1 - Strict lexical parser

- [x] RED tests for nested object/array spans, scalar kinds, raw digests and RFC 6901 pointer escaping.
- [x] RED strict syntax tests: string escapes/control characters, number grammar, comments, trailing commas, extra root data, NaN/Infinity.
- [x] RED duplicate-key ambiguity test.
- [x] Implement immutable lexical model and recursive-descent parser.
- [x] Cross-check complete-document acceptance with strict stdlib JSON decoding and duplicate-key hook.
- [x] Focused lexical suite GREEN.

## Task 2 - Deterministic JSON IR and capabilities

- [x] RED tests for source SHA/size, one JSON canvas, deterministic hierarchy/node IDs and canonical digest.
- [x] RED metadata/locator/span/raw-digest tests.
- [x] RED capability tests: scalars writable, containers structural-read-only, non-roundtrippable encoding read-only.
- [x] RED `JsonIRReader.accepts` limited to `.json`, `application/json`, `text/json`.
- [x] Implement reader on H1 reversible representation plus H3 lexical parser.
- [x] Register `replace_json_scalar` edit type only after RED.
- [x] Focused reader suite GREEN.

## Task 3 - Writer source authority and preflight

- [x] RED zero-edit byte identity and source SHA/size mismatch tests.
- [x] RED wrong type/target/payload/container/list/dict/non-finite-number/no-op tests.
- [x] RED stale semantic/native-locator/source-span/raw-digest tests.
- [x] Re-parse actual source and prove pointer/topology/span/raw evidence against IR before candidate construction.
- [x] Focused writer preflight GREEN.

## Task 4 - Target-only scalar rendering

- [x] RED string escape, integer, finite float, boolean, null and scalar-type-change tests.
- [x] RED multi-target span-offset test.
- [x] RED semantic no-op numeric equivalence test (`1e2` vs requested `100`).
- [x] Render only one scalar token at a time; standard serializer is forbidden for objects/arrays/whole source.
- [x] Apply exact spans without regenerating whitespace, punctuation, keys or container source.
- [x] Focused target rendering GREEN.

## Task 5 - Encoded untouched-byte proof

- [x] RED UTF-8 BOM, UTF-16 LE/BE and reversible encoding tests.
- [x] RED stateful-encoding leakage test.
- [x] Prove incremental character-byte boundaries equal strict whole-text encoding.
- [x] Compare all untouched source/candidate encoded segments and BOM exactly.
- [x] Focused preservation suite GREEN.

## Task 6 - Candidate re-read verification

- [x] RED unrequested scalar drift, raw lexical drift, topology drift and representation drift tests.
- [x] Re-read candidate with recorded encoding.
- [x] Verify path set/hierarchy, requested target semantics, unrequested semantic payload/raw digest and encoding/BOM.
- [x] Focused verification suite GREEN.

## Task 7 - Public imports, Markdown boundary, one-way regression

- [x] RED public import tests for reader/writer functions/classes.
- [x] Prove identity projection never advertises editable JSON capabilities.
- [x] Regression-test existing one-way PlainTextConverter `.json` output unchanged.
- [x] Add only the minimum public JSON adapter surface.

## Task 8 - Docs and exact-head gate

- [x] Document H3 in `TWOWAYS.md` after implementation is functionally green.
- [x] Review diff for no H1/H2/one-way/XML/HTML scope creep.
- [ ] Pre-commit green on exact final head.
- [ ] Package tests 3.10-3.13 green on exact final head.
- [ ] OCR tests 3.10-3.13 green on exact final head.

## Completion gate

H3 is complete only when the exact final branch head is green across all required checks. Do not create a documentation-only commit after observing green status; final documentation must already be part of the verified head.

After H3, proceed to H4 XML source preservation on a new stacked branch from the verified H3 head.
