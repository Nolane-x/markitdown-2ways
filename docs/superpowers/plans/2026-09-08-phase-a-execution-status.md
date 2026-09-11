# MarkItDown 2Ways Phase A — Execution Status

**Date:** 2026-09-08
**Branch:** `nolane/2way-document-ir-v0`
**PR:** #1
**Status:** implementation complete locally; repository CI evidence pending

## Implemented

Phase A now contains the complete dependency-light Core IR substrate described by the approved design:

- schema `MarkItDown2WaysDocument` version `0.1.0`;
- document, canvas, node, rich-text, image, table, chart and unknown-native contracts;
- geometry, style, provenance and native locators;
- resources, relationships and native-payload preservation hooks;
- typed edit operations and preconditions;
- deterministic graph validation with stable structured violation codes;
- canonical UTF-8 JSON encoding, decoding and SHA-256 digest helpers;
- strict and permissive forward-compatible decoding;
- priority registry matching upstream MarkItDown ordering semantics;
- reader/writer protocols and target information;
- fidelity evidence/report/result contracts;
- stable typed error hierarchy;
- explicit lightweight public namespace `markitdown.twoways`.

## Post-green refactor

The original plan placed validation and canonical codec behavior together in `ir/serialization.py`. After the behavior was green, implementation was split without changing the public contract:

- `ir/_validation.py` owns graph/reference/schema validation;
- `ir/serialization.py` owns canonical dict/JSON codec and delegates boundary validation.

This keeps each module focused while `markitdown.twoways.validate_document` remains unchanged.

## Regression found during refactor

A generic decoder initially coerced JSON integer values accepted by `float` annotations (for example `10`) into `10.0`. The document remained semantically equivalent, but `encode -> decode -> encode` was not byte-identical.

The decoder now preserves the input JSON numeric representation for portable float-compatible values. Regression coverage proves canonical byte equality.

## Verification executed in the isolated mini-workspace

- `PYTHONPATH=packages/markitdown/src pytest -q packages/markitdown/tests/twoways` -> **41 passed**
- `PYTHONHASHSEED=1 ... test_serialization.py` -> **9 passed**
- `PYTHONHASHSEED=777 ... test_serialization.py` -> **9 passed**
- `python -m compileall` over production/test twoways namespaces -> **PASS**
- forbidden dependency/import scan (`pptx`, pandas, openpyxl, Docling, LibreOffice, Mammoth) -> **PASS**
- branch comparison against fork `main` before this status commit -> **behind by 0**

## Environment limitation

The execution container cannot resolve `github.com`, so a normal full repository clone and local Hatch matrix were unavailable. Source changes were applied through the authenticated GitHub connector and focused tests were executed against an isolated local mirror of the new namespace.

The repository already defines `.github/workflows/tests.yml` with Python 3.10, 3.11, 3.12 and 3.13 matrices on `pull_request`. Phase A must not be described as full-matrix green until GitHub publishes run/check evidence for the current PR head.

## Next implementation boundary

After the Phase A matrix is green, the next independent subsystem is Phase B: Markdown projections and typed edit recovery. PPTX native reading/patching should begin only after identity-preserving Markdown/edit contracts are stable, so the OOXML layer consumes a tested edit model instead of inventing another one.
