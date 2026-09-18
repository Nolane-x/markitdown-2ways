# Phase H20 — Remote RSS/Atom snapshot parity implementation plan

**Goal:** Add a deterministic remote-derived reader for materialized RSS/Atom snapshots
without stealing local/native XML authority from H4.

**Base:** `main@a8e65158c7d56974a1a28a9894236f93cbb3a19b`

**Spec:** `docs/superpowers/specs/2026-09-18-markitdown-2ways-phase-h20-remote-feed-snapshot-parity-design.md`

**One-way baseline:** `RssConverter` blob
`6b7b1201062208f7e24695b388bc4c3baabbb229`.

## Task 1 — RED reader/parity contract

Create `test_remote_feed_reader.py`.

Tests:
- checked-in `test_rss.xml` + HTTPS URL;
- synthetic Atom + HTTPS URL;
- source format/URI/SHA/size;
- exact public Markdown/title parity;
- evidence/result digest;
- one derived root/no locator;
- deterministic canonical serialization/capability report.

Run focused RED: import failure because `read_remote_feed_snapshot_ir` is absent.

Commit: `H20 RED: lock remote feed snapshot reader contract`.

## Task 2 — GREEN reader

Modify `readers/remote.py`.

- validate mandatory HTTP/HTTPS URL/no credentials;
- bounded source capture;
- lazy `RssConverter`;
- require `accepts`;
- convert private bytes; catch conversion errors as deterministic `ValueError`;
- normalize Markdown;
- enforce output budget;
- deterministic IDs;
- evidence `kind="feed"`;
- source format `remote-feed-snapshot`;
- one derived root/no locator;
- no-writeback diagnostic;
- validate IR.

Run focused GREEN.

Commit: `H20: add deterministic remote feed snapshot reader`.

## Task 3 — Authority-separation hardening

Create `test_remote_feed_authority.py`.

Prove:
- same RSS bytes through `read_xml_ir` have native XML locator/metadata;
- H20 without URL rejects;
- extension/MIME alone never grants remote authority;
- HTTPS remote feed becomes derived;
- file/data/ftp/credentials/malformed-host reject;
- arbitrary valid HTTP/HTTPS host accepts valid feed;
- non-feed XML/malformed XML reject;
- precise feed MIME/extension cannot rescue invalid feed bytes.

Only modify production if RED proves a gap.

Commit: `H20 hardening: separate local XML and remote feed authority`.

## Task 4 — Budgets/firewall/public exports

Create:
- `test_remote_feed_hardening.py`;
- `test_remote_feed_public_imports.py`.

Test exact source limit, one-byte-over, bounded reads, exact Markdown limit,
one-byte-under, forbidden network/process imports, exports at remote/readers/top-level,
and absence of feed writer symbols.

Modify only reader package exports.

Commit: `H20: expose hardened remote feed reader`.

## Task 5 — One-way regression

Create `test_remote_feed_oneway_regression.py`.

Lock direct/public RSS and Atom behavior. Final scope requires `_rss_converter.py` blob
unchanged.

Commit: `H20: add feed one-way regression court`.

## Task 6 — Docs and exact closure

Update `TWOWAYS.md` with:
- H20 remote RSS/Atom snapshot parity;
- URL is provenance, not fetch instruction;
- local feed XML remains H4 native authority;
- derived/no writeback semantics;
- H21 YouTube next.

Scope audit permits only spec/plan, remote reader/public exports, H20 tests and docs.
H4 XML and one-way RSS files must be absent.

Freeze final SHA/tree. Require:
- pre-commit;
- package 3.10/3.11/3.12/3.13;
- OCR 3.10/3.11/3.12/3.13;
- exact 9/9 GREEN.

Record Python 3.13 totals/warnings, update PR provenance, prove synthetic parents/tree,
mark ready, guarded merge with exact expected head, then post-merge verify main
parents/tree and RSS converter blob.
