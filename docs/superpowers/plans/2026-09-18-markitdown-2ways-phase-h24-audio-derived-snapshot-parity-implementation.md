# MarkItDown 2Ways Phase H24 — implementation plan

Date: 2026-09-18
Base: `main@485a9c1d404268d99b5bf770a7aa9a52c7328a64`
Design: `2026-09-18-markitdown-2ways-phase-h24-audio-derived-snapshot-parity-design.md`

## Execution discipline

Proceed RED -> GREEN. Do not edit `_audio_converter.py`. Keep H15 native MP3 authority
unchanged. H24 is a derived-only snapshot adapter.

## Task 1 — RED courts

Add tests for:

- public H24 symbols;
- WAV/MP3/M4A/MP4 acceptance surface;
- accepted MIME prefixes;
- branch-order transcription routing;
- conflict cases;
- exact output preservation;
- empty output;
- independent source/output identity;
- resource limits and bounded reads;
- DERIVED capability state;
- no H24 writer;
- one-way blob freeze and offline differential parity;
- production optional-dependency/process/network firewall.

Expected RED: imports fail because the H24 reader does not yet exist.

## Task 2 — pure local reader

Create
`packages/markitdown/src/markitdown/twoways/readers/audio.py`.

Implementation rules:

- no one-way converter import;
- exact frozen extension/MIME acceptance tables;
- exact frozen one-way transcription branch order;
- bounded source capture;
- immutable `AudioConverterSnapshot`;
- immutable positive-integer `AudioDerivedLimits`;
- exact supplied materialized Markdown as the only visible text;
- deterministic source/output identity;
- one DERIVED text node with no native locator;
- explicit H15 non-ownership on MP3.

## Task 3 — read-only exports

Expose:

- `AudioConverterSnapshot`
- `AudioDerivedLimits`
- `read_audio_snapshot_ir`

from both `markitdown.twoways.readers` and `markitdown.twoways`.

Expose no audio writer/edit symbol.

## Task 4 — one-way regression

Freeze `_audio_converter.py` Git blob
`3d96b53c85490021269f198df94e50096f738b19`.

Run offline differential tests with fake exiftool metadata and fake transcription to
prove exact one-way Markdown and transcription route behavior for all four extensions and
conflict cases.

## Task 5 — docs

Update `TWOWAYS.md`:

- add H24 derived-local audio enrichment section;
- distinguish H15 native MP3 authority from H24 derived audio semantics;
- extend support matrix/roadmap;
- state that H24 closes the AudioConverter transcript/metadata semantic gap but adds no
  WAV/M4A/MP4 native writer.

## Task 6 — exact closure

Run exact final-head:

- pre-commit;
- package matrix 3.10–3.13;
- OCR matrix 3.10–3.13.

Do not merge a stale GREEN ancestor.

After 9/9 GREEN:

1. freeze head/tree;
2. verify 0 behind frozen base;
3. audit changed-file scope;
4. verify protected AudioConverter blob;
5. create two-parent synthetic merge;
6. verify exact tree equality;
7. mark ready;
8. guarded merge with expected final head;
9. post-merge main/tree/parents/blob verification.
