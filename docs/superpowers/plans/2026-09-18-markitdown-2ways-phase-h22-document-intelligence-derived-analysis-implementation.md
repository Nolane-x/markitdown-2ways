# MarkItDown 2Ways Phase H22 — implementation plan

Date: 2026-09-18
Base: `main@dfd340565f6cf6df850e89dc60f8688d98d6848a`
Design: `2026-09-18-markitdown-2ways-phase-h22-document-intelligence-derived-analysis-design.md`

## Execution discipline

Proceed strict RED -> GREEN. Do not edit the existing one-way
`_doc_intel_converter.py`. Do not add Azure SDK dependencies to the 2Ways import path.
Keep H22 derived/read-only.

## Task 1 — freeze contract with RED courts

Add tests that import the intended public names before implementation exists:

- `DocumentIntelligenceAnalysisSnapshot`
- `DocumentIntelligenceDerivedLimits`
- `read_document_intelligence_analysis_ir`

Add tests for deterministic IR, evidence fields, source binding, comment removal,
capability state, canonical serialization, resource limits, invalid metadata, default
file-type ownership, import firewall and absence of writer symbols.

Expected result: RED because H22 public surface and reader do not exist.

## Task 2 — implement the pure local reader

Create
`packages/markitdown/src/markitdown/twoways/readers/document_intelligence.py`.

Implementation rules:

- standard-library/internal imports only;
- bounded source capture in <=64 KiB requests;
- pure StreamInfo ownership helper mirroring default one-way file types;
- immutable analysis snapshot dataclass;
- positive-integer limits dataclass;
- exact HTML-comment stripping transform;
- deterministic IDs from source + analysis + Markdown evidence;
- one derived text root, no native locator;
- explicit analysis provenance envelope;
- no network, SDK, credentials or writer path.

Expected result: focused H22 courts GREEN.

## Task 3 — expose read-only public API

Export the three H22 symbols from:

- `markitdown.twoways.readers`
- `markitdown.twoways`

Do not expose any H22 writer/edit symbol.

Preserve lazy root imports: Azure SDK modules must remain absent after
`import markitdown.twoways`.

## Task 4 — one-way regression and differential proof

Freeze
`_doc_intel_converter.py` at Git blob
`f8a5c8e8c82638fc5186105679ff1af0175992c8`.

Use a fake in-memory `DocumentIntelligenceClient`, poller and analysis result to run the
existing converter without Azure or network. Prove H22 Markdown equals the unchanged
converter output for multiline HTML comments and surrounding content.

Also prove the production H22 reader source has no Azure/network/process imports.

## Task 5 — documentation

Update `TWOWAYS.md` to add H22 as a read-only derived-analysis boundary and link this
design plus plan. State explicitly that native file readers retain native mutation
authority and H22 analysis never grants native writeback.

## Task 6 — exact closure gate

Run exact-head CI:

- pre-commit;
- package Python 3.10–3.13;
- OCR Python 3.10–3.13.

If any lane fails, repair only the demonstrated defect, preserve scope, and rerun on the
new exact head. Do not merge a stale green ancestor.

## Task 7 — freeze and merge proof

After 9/9 GREEN:

1. freeze final head SHA and tree SHA;
2. compare H22 branch to frozen base and audit changed-file scope;
3. create/verify synthetic merge parents and exact tree equality;
4. mark PR ready only after proof;
5. guarded merge with expected final head;
6. verify post-merge main parents/tree;
7. verify protected converter blob remains
   `f8a5c8e8c82638fc5186105679ff1af0175992c8`.
