# MarkItDown 2Ways Phase H26 — OutlookMsgConverter derived semantic parity

Date: 2026-09-18
Status: frozen design
Base: `main@72f9b8df1351a4b35712ee57ef9f159d4bee7287`

## Purpose

H26 closes the semantic gap between the unchanged one-way `OutlookMsgConverter` and
the existing H16 native MSG tranche.

H16 intentionally owns only one native operation: fixed-allocation replacement of an
existing top-level Unicode `PidTagSubject`. It does not claim that the H16 native IR is
a full reproduction of the one-way converter's human-readable email projection.

H26 therefore adds a separate read-only derived adapter. The caller supplies exact MSG
source bytes plus an already-materialized semantic snapshot containing the four values
the one-way converter renders:

- sender / From;
- recipients / To;
- subject / Subject;
- body / PR_BODY.

H26 reconstructs the exact one-way Markdown scaffold and title semantics without
executing `olefile`, charset detection, code-page decoding or any process/network path.

## Protected one-way authority

Protected file:
`packages/markitdown/src/markitdown/converters/_outlook_msg_converter.py`

Frozen Git blob at H26 base:
`79d7656e5bd32d3b6aaa143a32635d5fb3e8f087`

H26 must not modify this converter.

## Scope and acceptance

H26 covers the stable explicit one-way registration surface:

- extension `.msg`;
- MIME prefix `application/vnd.ms-outlook`.

Extension authority takes precedence over MIME authority, matching the one-way converter.

The one-way converter also has an optional dependency-backed OLE structural sniff when
StreamInfo is absent. H26 deliberately does not duplicate that fallback as semantic
authority: structural sniffing belongs to the native CFB/MSG layer and can evolve under a
separate proof. H26 fails closed when neither explicit extension nor MIME authority is
present.

## Semantic snapshot

`OutlookMsgConverterSnapshot` contains:

- `sender: str | None`;
- `recipients: str | None`;
- `subject: str | None`;
- `body: str | None`;
- `provider: str`;
- optional `materialization_id`;
- optional `message_encoding`;
- optional `internet_encoding`.

Field values are already-materialized strings. H26 does not decode MSG property streams.
Empty strings and `None` are distinct provenance values even though both are omitted by
the one-way projection's truthiness checks.

## Exact projection

H26 reproduces the one-way converter algorithm exactly:

1. start with `# Email Message\n\n`;
2. append truthy headers in fixed order From, To, Subject as
   `**<name>:** <value>\n`;
3. append `\n## Content\n\n`;
4. append body only when truthy;
5. apply final `.strip()`.

The derived document title is the materialized subject value, matching
`DocumentConverterResult(title=headers.get("Subject"))`.

## Identity and provenance

Document identity independently binds:

- exact source SHA-256 and size;
- StreamInfo filename/MIME/extension/URI;
- acceptance authority;
- presence and raw UTF-8 digest of each semantic field;
- provider/materialization ID;
- optional encoding descriptors;
- final Markdown SHA-256;
- protected converter identity.

H26 records `twoways.outlook_msg_converter_snapshot.v1` with the same authorities and
explicit evidence that no optional one-way runtime path was executed.

## Capability boundary

The sole H26 root is DERIVED and has no native locator.

`replace_text` has:

- state: `CapabilityState.DERIVED`;
- reason: `msg.output.not_native_writable`;
- `identity_markdown=False`;
- `native_owner=False`;
- `remote_writeback=False`;
- `materialization="explicit-local-only"`.

H26 exposes no writer. H16 remains the only native MSG mutation authority.

## Resource budgets

`OutlookMsgDerivedLimits` independently bounds:

- source bytes;
- aggregate snapshot UTF-8 bytes;
- final Markdown UTF-8 bytes.

Source reads are bounded to <=64 KiB. Limits must be positive integers and reject booleans.

## Production dependency firewall

The H26 production reader must not import or invoke:

- `olefile`;
- `charset_normalizer`;
- `codecs`-based source decoding;
- subprocess/network/browser/retry/sleep paths;
- the one-way converter.

One-way parity is proved only in tests with deterministic in-memory fakes.

## Required courts

H26 completion requires:

1. exact extension/MIME acceptance;
2. fixed From/To/Subject ordering;
3. header omission for falsey materialized fields;
4. exact body and final `.strip()` semantics;
5. subject-to-title semantics;
6. independent source/header/body identity;
7. provider/materialization/encoding provenance;
8. exact resource boundaries and bounded reads;
9. DERIVED/no-native capabilities;
10. canonical serialization determinism;
11. public read-only exports and no writer symbols;
12. production dependency firewall;
13. frozen one-way converter blob;
14. offline differential parity against the unchanged one-way converter;
15. full repository regression suite.

## Closure

The exact final H26 head must pass pre-commit plus package and OCR matrices on Python
3.10-3.13 (9/9). Then freeze head/tree, prove exact two-parent synthetic merge tree
identity against the frozen base, mark ready, guarded-merge with expected head and
re-verify post-merge main plus the protected converter blob.
