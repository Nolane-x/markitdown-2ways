# Phase H33 — deterministic engineering budgets

## Goal

Close the pre-v1 hardening sequence with deterministic complexity and dependency budgets.
H33 prevents the 2Ways implementation from silently becoming larger, more dependency-heavy
or broader in public surface without an explicit design decision.

## Baseline

The H32 candidate contains:

- 200 production Python files under `markitdown.twoways`;
- 1,547,539 production source bytes;
- a largest production Python file of 37,389 bytes.

These values are recorded as evidence, not as ceilings.

## Required ceilings

H33 creates deliberately bounded headroom rather than freezing every byte:

- at most 220 production Python files;
- at most 1,750,000 production source bytes;
- at most 45,000 bytes for any one production Python file;
- exactly the H30 public-root cardinality;
- exactly 17 native support rows and 12 derived support rows;
- no silent expansion of the six core runtime dependencies.

Any future budget growth must be intentional and accompanied by a design record and
regression court.

## Performance policy

Required CI does not use wall-clock microbenchmarks because shared runners make such
thresholds flaky. Performance regressions that need timing evidence should use separate
benchmark evidence, while required CI enforces deterministic structural proxies and
bounded parser/reader limits already covered by format-specific courts.

## Non-goals

H33 adds no format, writer, edit type, dependency, schema change or public symbol.

## Acceptance

The H33 budget court, pre-commit and package/OCR Python 3.10-3.13 matrices must pass on
the exact candidate head.
