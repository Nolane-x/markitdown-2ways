# Phase H20 — RSS/Atom Remote-Derived Snapshot Parity Implementation Plan

**Goal:** Add remote-derived RSS/Atom parity while proving the same feed bytes remain
native-writable XML when explicitly read through H4 local XML authority.

**Base:** `a8e65158c7d56974a1a28a9894236f93cbb3a19b`

## Task 1 — RED remote reader + local/native authority split

Create `test_remote_rss_atom_reader.py`.

Using `tests/test_files/test_rss.xml`:
- remote reader symbol initially missing;
- exact public one-way Markdown/title parity;
- remote source/result evidence;
- DERIVED capability/no locator;
- deterministic canonical round trip;
- same bytes through `read_xml_ir` remain native XML with native locator and at least one
  writable XML lexical owner.

Commit RED separately.

## Task 2 — GREEN RSS/Atom remote reader

Modify only `readers/remote.py`:
- add converter blob constant;
- add HTTP(S)/no-credentials generic remote URL validator for feeds;
- reuse bounded capture/normalization/capability helpers;
- lazy-import `RssConverter`;
- require converter ownership;
- build `remote-rss-atom-snapshot` derived IR;
- leave H4 and H18/H19 reader bodies untouched.

Run H18-H20 reader tests GREEN.

## Task 3 — hardening

Create `test_remote_rss_atom_hardening.py`.

Cover invalid/missing URL, non-feed ownership, source/result exact boundaries,
bounded-read probe and network/process firewall.

Fix only proven gaps.

## Task 4 — public surface

RED then GREEN:
- `read_rss_atom_snapshot_ir` from remote/readers/top-level twoways;
- no writer/writeback exports;
- preserve lazy imports.

## Task 5 — one-way regression

Create `test_remote_rss_atom_oneway_regression.py`.

Assert direct `RssConverter` and public `MarkItDown.convert_stream` remain green.
Keep converter blob exact.

## Task 6 — docs/final integration

Update `TWOWAYS.md` with local-vs-remote authority split.
Freeze final head and require exact 9/9, Python 3.13 totals, scope/blob proof, synthetic
tree equality, guarded merge and post-merge verification.
