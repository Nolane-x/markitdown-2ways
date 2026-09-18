# Phase H19 — Bing SERP Remote-Derived Snapshot Parity Implementation Plan

**Goal:** Add deterministic, read-only `DocumentIR` parity for already-materialized Bing
SERP HTML snapshots while preserving H18 Wikipedia output and proving there is no remote
writeback authority.

**Base:** `6bdfa3cebe1060b5c5a8bced4206f20a8dab3a19`

**Spec:** `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h19-bing-serp-remote-derived-snapshot-parity-design.md`

## Global constraints

- Keep `BingSerpConverter` blob exactly
  `fd00a70ab76ff01fcdc2e3bfb47aaf20708408c8`.
- No live network I/O.
- No writer or writer-registry change.
- No schema bump.
- Preserve H18 Wikipedia canonical serialization exactly.
- Reuse only private helpers; do not publish a generic caller-labelled remote adapter.
- Final exact court is pre-commit + package/OCR Python 3.10–3.13 = 9/9 GREEN.

### Task 1 — RED Bing reader/parity contract

Files:
- Modify `packages/markitdown/src/markitdown/twoways/readers/remote.py` only after RED.
- Create `packages/markitdown/tests/twoways/test_remote_bing_serp_reader.py`.

RED tests:
- inline deterministic Bing HTML with at least two `b_algo` results;
- accepted URL `https://www.bing.com/search?q=markitdown`;
- reader symbol initially missing;
- public one-way Markdown/title exact parity;
- source/result digests;
- one derived root node;
- deterministic IDs/canonical serialization.

Commit RED separately.

### Task 2 — GREEN private kernel + Bing reader

Refactor H18 only enough to share private mechanics:
- bounded snapshot capture;
- Markdown normalization;
- capability creation;
- deterministic remote-derived document builder.

Keep Wikipedia source format/evidence/diagnostic/canonical bytes unchanged.

Add:
- `_BING_SERP_CONVERTER_BLOB_SHA`;
- source-specific URL structural preflight;
- lazy import of `BingSerpConverter`;
- `read_bing_serp_snapshot_ir(...)`.

Run H18 + H19 reader tests GREEN.

### Task 3 — RED/GREEN capability, public imports and H18 regression

Create:
- `test_remote_bing_serp_public_imports.py`.

Assert:
- public export from `readers.remote`, `readers`, top-level `twoways`;
- no writer/writeback exports;
- derived capability exact;
- no native locator;
- schema remains 0.1.0;
- H18 Wikipedia canonical digest/output remains unchanged across the refactor.

Implement only required lazy exports.

### Task 4 — adversarial URL/budget/network hardening

Create:
- `test_remote_bing_serp_hardening.py`.

Cover:
- missing URL;
- http instead of https;
- wrong host and lookalike host;
- credentials;
- malformed host;
- non-search Bing path;
- converter ownership rejection;
- exact/over source limit;
- exact/over Markdown limit;
- bounded-read probe;
- structural network/process import firewall;
- degenerate HTML remains derived.

Fix only proven production gaps.

### Task 5 — one-way invariance

Create:
- `test_remote_bing_serp_oneway_regression.py`.

Assert:
- direct converter ownership;
- direct converter semantics;
- public `MarkItDown.convert_stream` semantics;
- H18 Wikipedia one-way regression remains green.

Final scope audit must prove one-way converter file unchanged.

### Task 6 — docs and closure

Update `TWOWAYS.md`:
- add H19 Bing snapshot parity;
- explicitly say no search execution/network/writeback;
- retain RSS for H20.

Freeze final head, then require:
- scope audit;
- converter blob proof;
- exact 9/9 final-head CI;
- Python 3.13 totals;
- PR provenance;
- synthetic merge parents/tree equality;
- mark ready;
- guarded merge with exact head;
- post-merge main/tree/blob proof.
