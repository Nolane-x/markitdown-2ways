# Phase H21 — YouTube multi-input provenance implementation plan

**Goal:** Add deterministic YouTube page + optional transcript derived-source parity
without network access or false native ownership.

**Base:** `main@667bb3edd6bc90fa4bd99d1d0e957c0f45671f83`

**Spec:** `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h21-youtube-multi-input-provenance-design.md`

## Task 1 — Freeze one-way baseline and RED reader contract

Record `_youtube_converter.py` blob SHA.

Create `test_remote_youtube_reader.py`.

RED tests:
- supported YouTube URL shapes;
- HTML-only title/metadata/description projection;
- source URI/SHA/size/video ID;
- one derived root/no locator;
- deterministic canonical serialization;
- transcript absence evidence.

Expected RED: public H21 symbols/module absent.

Commit: `H21 RED: lock YouTube multi-input reader contract`.

## Task 2 — GREEN deterministic local reader

Create `twoways/readers/youtube.py`.

Implement:
- `YouTubeTranscriptSnapshot`;
- `YouTubeDerivedLimits`;
- URL validation;
- bounded HTML capture;
- current `YouTubeConverter.accepts` ownership check only;
- pure local HTML extraction matching converter formatting;
- deterministic IDs/evidence/diagnostic;
- no transcript service call.

Do not expose public symbols yet beyond module-local testing if import topology requires
separate RED.

Commit: `H21: add deterministic YouTube snapshot reader`.

## Task 3 — RED -> GREEN transcript authority

Extend tests with explicit transcript snapshot:

- ordered parts join with one space;
- transcript evidence digest/size/language/provider;
- video ID must match URL;
- empty/invalid fields reject;
- exact and over-budget transcript limits;
- transcript omitted is not “unavailable”.

Implement only failures proven by RED.

Commit: `H21: bind explicit transcript materialization authority`.

## Task 4 — Offline differential oracle

Create `test_remote_youtube_differential.py`.

Use monkeypatch/fakes only in tests:

- force one-way transcript capability off and compare exact title/Markdown to H21
  HTML-only result;
- replace `YouTubeTranscriptApi` with deterministic in-memory fake and compare exact
  title/Markdown to H21 using equivalent `YouTubeTranscriptSnapshot`;
- forbid real retry/sleep/network.

Production code may not patch globals or import transcript API.

Commit: `H21: add offline YouTube one-way differential court`.

## Task 5 — Hardening and public surface

Create:
- `test_remote_youtube_hardening.py`;
- `test_remote_youtube_public_imports.py`;
- `test_remote_youtube_oneway_regression.py`.

Lock:
- invalid schemes/credentials/lookalike hosts/malformed ports;
- source/transcript/Markdown budgets;
- bounded reads;
- production import firewall;
- derived capability;
- no writer symbols;
- lazy top-level exports;
- one-way converter blob unchanged.

Expose H21 reader/dataclasses from `twoways.readers` and top-level `twoways` without
eagerly importing optional transcript dependencies.

Commit: `H21: expose hardened YouTube multi-input reader`.

## Task 6 — Docs and exact closure

Update `TWOWAYS.md`:

- H21 multi-input provenance;
- HTML and transcript are separate materializations;
- absence of transcript is not evidence of remote unavailability;
- no network/writeback;
- H22 Azure DI next.

Scope permits only spec/plan, H21 reader/public exports/tests/docs.
`_youtube_converter.py` must be absent from diff.

Freeze final SHA/tree and require exact 9/9 GREEN.

Record Python 3.13 totals/warnings, update PR provenance, prove synthetic merge
parents/tree, mark ready, guarded merge with exact head, post-merge verify main and
one-way converter blob.
