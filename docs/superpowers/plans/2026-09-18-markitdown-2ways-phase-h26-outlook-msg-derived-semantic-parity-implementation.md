# MarkItDown 2Ways Phase H26 — implementation plan

Date: 2026-09-18
Base: `main@72f9b8df1351a4b35712ee57ef9f159d4bee7287`

## Task 1 — RED contract

Add courts for:

- `OutlookMsgConverterSnapshot`;
- `OutlookMsgDerivedLimits`;
- `read_outlook_msg_snapshot_ir`.

Lock exact one-way scaffold/header/body/title semantics, explicit acceptance, provenance,
identity, budgets, public exports and one-way differential behavior.

## Task 2 — pure local reader

Create `markitdown.twoways.readers.outlook_msg`.

Requirements:

- standard-library/internal imports only;
- bounded source capture;
- explicit .msg/MIME acceptance only;
- deterministic per-field digesting;
- exact fixed header ordering and truthiness behavior;
- exact final `.strip()`;
- derived title from materialized subject;
- one DERIVED root, no native locator;
- no native writer.

## Task 3 — public API

Export snapshot, limits and reader from `markitdown.twoways.readers` and
`markitdown.twoways`. Add no H26 edit/write symbols.

## Task 4 — one-way differential proof

Freeze `_outlook_msg_converter.py` at
`79d7656e5bd32d3b6aaa143a32635d5fb3e8f087`.

Run the unchanged converter entirely offline by replacing only test-side OLE/property
materializations with deterministic fakes. Prove H26 Markdown and title semantics match.

## Task 5 — docs

Update `TWOWAYS.md` so the v1.0-gate matrix distinguishes H16 native Subject authority
from H26 complete derived one-way message projection.

## Task 6 — closure

Run exact final-head 9/9 CI. Repair only demonstrated failures. After GREEN, freeze
head/tree, audit scope, verify converter blob, prove synthetic merge tree equality,
mark ready, guarded-merge and post-merge verify.
