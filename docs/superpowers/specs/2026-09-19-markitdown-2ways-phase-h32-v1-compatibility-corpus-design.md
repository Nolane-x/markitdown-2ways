# Phase H32 — v1 compatibility corpus

## Goal

Turn the H30 product contract into a serialization compatibility court before the v1.0
release. H32 freezes representative canonical IR payloads independently from ordinary
round-trip tests so accidental wire drift is caught even when encoder and decoder change
together.

## Corpus

The machine-readable corpus is `docs/twoways-v1-compatibility-corpus.json`.

It freezes two deliberately different cases:

1. `minimal-defaults` — a minimal `DocumentIR` that exercises default/omit-none
   behavior.
2. `representative-document` — the existing rich test fixture covering canvases,
   geometry, text runs, styles, resources, native payloads, provenance, native locators,
   tables, unknown-native payloads and edits.

For each case H32 records the exact canonical byte length and SHA-256 digest.

## Decoder compatibility

H32 also freezes these rules:

- strict mode rejects unknown fields;
- forward mode ignores unknown fields while preserving known semantics;
- unsupported schema majors are rejected;
- encode -> decode -> encode remains byte-identical for frozen goldens.

## Non-goals

H32 adds no reader, writer, format, edit type, dependency, public symbol or schema change.
It does not promise compatibility for unsupported future schema majors.

## Acceptance

The corpus court plus the full package/OCR Python 3.10-3.13 matrices and pre-commit must
all pass on the exact candidate head.
