# Phase H1 Text Source Preservation Implementation Plan

> Execution tranche for v0.5.0. Use test-driven development and require exact-head CI evidence before merge.

**Goal:** Add deterministic, source-preserving two-way support for native plain-text and Markdown files while retaining exact source encoding, BOM and unambiguous newline convention.

**Architecture:** `markitdown.twoways.formats.text` represents one authoritative lexical source as one text canvas/node. Reader-side helpers prove reversible decoding and classify representation metadata. The native writer reuses `replace_text`, capability and precondition contracts, verifies source identity, performs complete preflight, encodes into the original representation, re-reads the candidate, and emits bytes only after verification succeeds.

**Important boundary discovered during implementation:** existing identity-Markdown text import is semantic-text oriented and may normalize whitespace or interpret Markdown syntax. Therefore native `.txt`/`.md` nodes are directly writable through typed IR edits, but advertise no editable identity-Markdown capability in H1. A raw-source identity protocol is deferred until it can prove lexical preservation.

**Spec:** `docs/superpowers/specs/2026-09-12-markitdown-2ways-phase-h1-text-source-preservation-design.md`

## Global constraints

- Keep the existing one-way `MarkItDown` API and CLI unchanged.
- No silent transcoding or newline selection.
- No CSV/JSON/XML/HTML mutation in H1.
- Source bytes must match `DocumentIR.source.sha256` and `size_bytes` before mutation.
- Unknown/unadvertised capabilities remain read-only.
- Mixed-newline sources remain readable but direct mutation is read-only.
- Zero-edit and semantic no-op writes are byte-identical.
- Native source identity-Markdown is inspection-only in H1.
- Destination bytes are emitted only after candidate re-read verification.
- Exact PR-head Python 3.10–3.13 tests, OCR tests and pre-commit must be green before merge.

## Task 1 — Reversible textual representation

Files:
- `packages/markitdown/src/markitdown/twoways/formats/text/model.py`
- `packages/markitdown/src/markitdown/twoways/formats/text/codec.py`
- `packages/markitdown/tests/twoways/test_text_codec.py`

- [x] Establish RED before production module existed.
- [x] Add strict BOM-aware decode/encode helpers.
- [x] Prefer exact UTF-8, permit explicit codecs, and permit charset detection only when exact re-encoding proves the original payload bytes.
- [x] Classify LF/CRLF/CR/none/mixed without universal-newline normalization.
- [x] Reject line-break invention for newline-free sources and mutation of mixed-newline sources.
- [x] Prove focused codec behavior including Unicode BOMs, legacy encoding and unencodable output.

## Task 2 — Deterministic native text IR

Files:
- `packages/markitdown/src/markitdown/twoways/formats/text/reader.py`
- `packages/markitdown/tests/twoways/test_text_reader.py`

- [x] Establish reader RED before implementation.
- [x] Build one deterministic `Canvas(kind="text")` and one authoritative `Node(kind="text")`.
- [x] Bind SHA-256, size, format, native locator and representation metadata to the IR.
- [x] Mark lexical source nodes with `text.native_source=true`.
- [x] Advertise direct `replace_text` only for reversible, non-mixed representations.
- [x] Restrict H1 detection to plain text and Markdown; structured formats remain follow-on tranches.

## Task 3 — Transactional native writer

Files:
- `packages/markitdown/src/markitdown/twoways/formats/text/writer.py`
- `packages/markitdown/tests/twoways/test_text_writer.py`

- [x] Establish writer RED before implementation.
- [x] Verify source digest and size before edit processing.
- [x] Require authoritative locator, writable capability, valid payload and existing edit preconditions.
- [x] Revalidate representation metadata against the actual source bytes.
- [x] Preserve source encoding/BOM/newline policy and reject unencodable replacements.
- [x] Keep zero-edit and semantic no-op output byte-identical.
- [x] Re-read candidate bytes and verify semantics + representation before `output.write()`.
- [x] Fail before destination output for stale source, stale old value, forged locator, malformed edit, duplicate replacement, mixed newline and unencodable replacement.

## Task 4 — Public surface

Files:
- `packages/markitdown/src/markitdown/twoways/formats/text/__init__.py`
- `packages/markitdown/tests/twoways/test_text_public_imports.py`

- [x] Export `TextRepresentation`, codec helpers, `TextIRReader`, `TextPatchWriter`, `read_text_ir`, and `patch_text`.
- [x] Keep public adapter independent of the one-way `MarkItDown` API.

## Task 5 — Identity-Markdown safety boundary

Files:
- `packages/markitdown/src/markitdown/twoways/markdown/_render_text.py`
- `packages/markitdown/tests/twoways/test_text_markdown_bridge.py`

- [x] Demonstrate that native lexical text must not inherit the generic semantic `replace_text` identity-Markdown path.
- [x] Preserve current editable behavior for Office-derived semantic text nodes.
- [x] Publish `editable_capabilities=()` for `text.native_source=true` blocks.
- [x] Prove unchanged native-source identity projection imports to zero edits.
- [x] Defer editable raw-source identity Markdown until exact lexical preservation can be demonstrated.

## Task 6 — Documentation and regression gate

Files:
- `TWOWAYS.md`
- this plan
- Phase H1 design spec

- [x] Document the direct native text/Markdown API and its preservation contract.
- [x] Document why native-source identity Markdown is read-only in H1.
- [x] Record stable read-only reasons (`text.encoding.not_roundtrippable`, `text.newline.mixed`).
- [ ] Exact final-head pre-commit passes without rewriting files.
- [ ] Exact final-head package tests pass on Python 3.10, 3.11, 3.12 and 3.13.
- [ ] Exact final-head OCR matrix passes.
- [ ] Final diff review finds no unintended one-way API/CLI changes or structured-format scope creep.

## Completion gate

H1 is mergeable only when all unchecked verification items above are green on the exact PR head. Older successful runs do not satisfy this gate. Until then PR #7 remains draft and Phase H2 must not reuse H1 as a proven substrate.

## Next roadmap tranche after H1 gate

**Phase H2 — CSV source-preserving cell mutation.** Reuse only the proven encoding/BOM/newline primitives. CSV must independently prove dialect, record/field boundaries and quoting/escaping behavior, then patch only authorized lexical spans. It must not round-trip through pandas or a generic CSV serializer merely because parsing succeeds.

After H2, structured JSON/XML/HTML work gets its own syntax-aware lexical/subtree locators and preservation proof; it must not pretty-print or rebuild unrelated content.
