# MarkItDown 2Ways Phase H23 — implementation plan

Date: 2026-09-18
Base: `main@b4d926d153f54b4db15989310311a907131bf895`
Design: `2026-09-18-markitdown-2ways-phase-h23-content-understanding-derived-analysis-design.md`

## Execution discipline

Proceed strict RED -> GREEN. Keep `_cu_converter.py` byte-identical. Production H23
must be standard-library/internal-only and must never import the Azure Content
Understanding SDK.

## Task 1 — freeze RED public and routing contracts

Add courts for the intended public surface:

- `ContentUnderstandingAnalysisSnapshot`
- `ContentUnderstandingDerivedLimits`
- `read_content_understanding_analysis_ir`

Lock complete extension routing, representative MIME aliases, conflict resolution,
modality, default analyzer selection, canonical content types, provenance, capabilities,
limits, deterministic identity and serialization.

Expected state: RED because the H23 reader does not yet exist.

## Task 2 — implement a pure local routing kernel

Create
`packages/markitdown/src/markitdown/twoways/readers/content_understanding.py`.

Requirements:

- frozen local extension/MIME/modality/default-analyzer tables;
- extension precedence over MIME;
- MIME parameter stripping and current alias canonicalization;
- content type derived from resolved file type;
- bounded <=64 KiB source capture;
- immutable materialized-analysis snapshot;
- descriptor validation against independently derived routing;
- exact analysis content as visible Markdown;
- deterministic source + analysis identity;
- DERIVED root with no native locator;
- no network/SDK/credential/process behavior.

## Task 3 — expose read-only API

Export the H23 snapshot, limits and reader from:

- `markitdown.twoways.readers`;
- `markitdown.twoways`.

Expose no H23 writer/edit symbols.

## Task 4 — one-way differential and blob proof

Freeze `_cu_converter.py` at
`230e3d86bf533241b68dfc3d023e48b3effdc788`.

Use a converter instance created without SDK initialization plus an in-memory fake client.
Patch only the test-side `to_llm_input` function. Prove:

- one-way analyzer routing matches H23;
- one-way content type matches H23;
- one-way Markdown equals H23 visible content;
- extension/MIME conflicts resolve identically.

Production H23 must not import the converter.

## Task 5 — documentation

Extend `TWOWAYS.md` with H23 and state that v0.9 now covers both Azure reader bridges
listed by the full-parity program while preserving explicit non-native-writeback
semantics.

## Task 6 — exact closure

Run final-head pre-commit and package/OCR matrices on Python 3.10–3.13. Repair only
demonstrated defects and rerun on the new exact head.

After 9/9 GREEN:

1. freeze final head and tree;
2. confirm branch is 0 behind frozen base and audit final file scope;
3. verify protected CU converter blob;
4. create and verify synthetic two-parent merge with exact tree equality;
5. mark PR ready;
6. guarded merge with expected final head;
7. verify post-merge main parents/tree and converter blob.
