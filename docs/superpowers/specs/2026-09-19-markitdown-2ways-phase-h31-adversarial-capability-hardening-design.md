# Phase H31 — Adversarial capability hardening

## Goal

Strengthen the frozen H30 capability boundary without widening the v1 feature surface.
H31 treats capability metadata as security-sensitive authority and assumes malformed,
duplicated, stale, or post-construction-mutated inputs are adversarial.

## Invariants

1. A capability decision cannot gain authority after construction through mutation of
   its constraint mapping.
2. Unknown default capability states fail closed.
3. Missing capability metadata remains read-only.
4. Malformed capability wire values, invalid states, invalid constraints and duplicate
   operation claims are rejected.
5. An unspecified operation never inherits authority from another writable operation.
6. The H30 native matrix must not expose structural add/remove/resource replacement as
   direct native mutations.
7. Every H18-H29 derived surface remains derived and has no native writeback.

## Production change

`CapabilityDecision.constraints` becomes a detached immutable mapping. This preserves
mapping equality and encoding behavior while preventing callers from mutating the
top-level authority constraints after a frozen decision has been created.

`NodeCapabilityProfile.default_state` is normalized through `CapabilityState` and rejects
unknown values.

## Non-goals

H31 does not add formats, writers, edit types, remote writeback, archive structural
editing, or new public root symbols. It does not change the IR schema or capability wire
key.

## Acceptance court

The H31 adversarial court exercises mutation attempts, malformed wire families,
duplicate authority, fallback behavior, default read-only reporting, forbidden structural
operations and derived writeback denial. Full package/OCR and pre-commit matrices remain
the integration gate.
