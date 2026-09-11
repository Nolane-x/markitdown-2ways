# Two-Way Document Technology Study

**Date:** 2026-09-08  
**Purpose:** engineering research for `Nolane-x/markitdown-2ways`  
**Baseline branch:** `nolane/2way-document-ir-v0`

This note records the concrete architectural lessons used to design MarkItDown 2Ways. It distinguishes ideas worth adopting from implementation details that should remain external or optional.

## 1. Microsoft MarkItDown — preserve the ingestion core

Repository: https://github.com/microsoft/markitdown  
Fork baseline: `b6e8bbdce628d564c6af031b5f26cda6e818ea10`

### Current architecture

The current core revolves around `DocumentConverter` and `DocumentConverterResult` in:

`packages/markitdown/src/markitdown/_base_converter.py`

Converters expose:

- `accepts(file_stream, stream_info, **kwargs)`
- `convert(file_stream, stream_info, **kwargs)`

`MarkItDown` owns a prioritized converter registry in:

`packages/markitdown/src/markitdown/_markitdown.py`

Built-ins are registered in a clear priority order, and plugins are discovered through the `markitdown.plugin` entry-point group.

### Important seam for 2Ways

Do **not** replace `DocumentConverter` with a bidirectional abstraction. That would destabilize the public one-way contract and complicate upstream merges.

Instead, add parallel `DocumentIRReader` and `DocumentWriter` protocols under a new namespace and compose them through a `TwoWayMarkItDown` facade.

### PPTX-specific useful existing code

`PptxConverter` already contains practical handling for:

- slide ordering,
- title/body text,
- tables,
- charts,
- group-shape traversal,
- speaker notes,
- alt text,
- embedded images,
- SVG images that lack raster fallback.

Those helpers are valuable knowledge for a PPTX IR reader. Shared low-level utilities should only be extracted when both old and new paths can use them without changing current Markdown output.

## 2. Docling / docling-core — rich canonical document representation

Repositories:

- https://github.com/docling-project/docling
- https://github.com/docling-project/docling-core

### What Docling gets right

`DoclingDocument` is a rich, typed canonical model rather than a Markdown string. Its model includes:

- text items,
- pictures,
- tables,
- key-value/form structures,
- body/furniture hierarchy,
- groups,
- page information,
- layout bounding boxes,
- provenance.

Its source model is versioned and serialized through a structured schema.

The Docling documentation explicitly treats Markdown as one serializer among several. It also documents that Markdown can flatten information that the internal model retains — e.g. merged table cell spans remain in the internal table representation but cannot be faithfully expressed in ordinary Markdown tables.

### Lesson adopted

MarkItDown 2Ways must keep a richer IR as canonical and treat Markdown as a projection.

### Lesson extended

Docling provenance identifies where content came from in the source. For Office round-trip editing we need an additional mutation-oriented layer:

- OOXML part URI,
- relationship id,
- shape/object id,
- `creationId` when available,
- native-unit geometry,
- source package digest.

This turns provenance into a safe writer locator.

### Integration policy

Docling should remain an optional reader/backend or interop adapter. The core fork should not require Docling simply to get a good IR design.

## 3. Pandoc — Reader -> AST -> Writer architecture

Repository: https://github.com/jgm/pandoc

Pandoc's API documentation describes a direct architecture:

`[input format] ==reader==> [Pandoc AST] ==writer==> [output format]`

This yields M×N conversions from M readers and N writers.

### Lesson adopted

A format reader should not know which output writer will eventually be used. Writers consume the common IR.

This is the central reason to avoid implementing isolated pairs such as:

- Markdown -> PPTX
- PPTX -> Markdown
- Markdown -> DOCX
- DOCX -> Markdown

as unrelated converters.

### Important limitation to avoid

Pandoc itself documents that its native representation is less expressive than many source formats, so formatting details can be lost.

Our IR therefore needs geometry, style inheritance, resources, native relationships and source-package preservation in addition to semantic blocks.

### Licensing note

Pandoc is GPL-licensed. We can learn from its public architecture and interoperability concepts, but this MIT fork should not copy GPL implementation code into the project without a deliberate licensing decision.

## 4. pptx-automizer — source-preserving PowerPoint mutation

Repository: https://github.com/singerla/pptx-automizer

### Key mental model

pptx-automizer is template-oriented. It loads a root PPTX plus optional source templates, queues operations, and applies them when output is written.

Its documentation highlights:

- existing PPTX templates as the source of masters/themes/layouts,
- shape-level modification,
- direct XML callbacks through `xmldom`,
- `creationId` as a more stable selector than slide/shape names,
- optional automatic import of slide masters,
- a bridge to PptxGenJS for generated shapes.

### Lesson adopted

For a document with an original PPTX, regeneration is the wrong default. Start with the original package and patch the minimum native parts.

This is the architectural foundation of `mode="patch"`.

### Lesson adapted

We do not copy the Node-specific queue API into the Python core. Instead, typed `EditOperation` objects provide the deferred/validated mutation layer.

### Stable identity strategy

Preferred PPTX locator order:

1. `creationId`,
2. `cNvPr/@id`,
3. shape name + structural context,
4. XML path fallback.

Every patch additionally carries a precondition digest so an old edit cannot silently hit a different object.

## 5. PptxGenJS — strong synthetic PPTX generation

Repository: https://github.com/gitbrent/PptxGenJS

PptxGenJS generates standards-compliant OOXML presentations and supports:

- text,
- tables,
- shapes,
- images,
- charts,
- slide masters,
- SVG,
- notes/media-related presentation features,
- Buffer/Blob/stream output.

### Lesson adopted

Synthetic generation is a separate capability from high-fidelity patching.

A rebuild writer is useful for Markdown-only or AI-created content, but it should never be mistaken for source-preserving round trip.

### Integration policy

Do not make Node.js mandatory for the Python package. The first rebuild writer should use `python-pptx`, which MarkItDown already depends on for PPTX ingestion.

A future optional PptxGenJS bridge is justified only when a feature/fidelity benchmark shows measurable advantage.

## 6. Marp CLI — Markdown slide semantics, but not the fidelity core

Repository: https://github.com/marp-team/marp-cli

### Useful idea

Marp demonstrates an ergonomic Markdown-to-slides authoring model with themes and slide semantics.

### Critical implementation finding

The standard PPTX export path renders slide images and places them as slide backgrounds using PptxGenJS.

The experimental editable PPTX path currently:

1. converts to PDF,
2. invokes headless LibreOffice with PDF import,
3. converts that imported result to PPTX.

Its own source emits a warning that slide reproducibility is not fully guaranteed.

### Decision

Do not use the PDF/LibreOffice route for MarkItDown 2Ways round-trip fidelity.

Marp remains useful as inspiration for Markdown directives, themes and rebuild authoring ergonomics.

## 7. python-pptx — first native Python substrate

Repository: https://github.com/scanny/python-pptx

MarkItDown already has `python-pptx` in its `pptx` optional dependency and uses it in `PptxConverter`.

### Why it is the right first dependency

- no new language/runtime requirement,
- already integrated into existing MarkItDown tests and packaging,
- reads existing PPTX object models,
- can create/edit PowerPoint content,
- exposes underlying OOXML elements when high-level APIs are insufficient.

### Boundary

Direct private XML access must be isolated in `twoways/native/` adapters. High-level IR code should not depend on internal python-pptx element shapes.

This protects us from upstream python-pptx changes and makes a future alternate OOXML backend possible.

## 8. Architecture synthesis

The strongest combined model is:

```text
                 Microsoft MarkItDown
                  ingestion knowledge
                          |
                          v
                 format IR readers
                          |
                          v
                  +---------------+
                  |  Document IR  |
                  +-------+-------+
                          |
          +---------------+----------------+
          |               |                |
          v               v                v
      Markdown         edit ops         JSON/.m2w
      projection           |                bundle
          |                |                 |
          +----------------+-----------------+
                           |
                           v
                     writer registry
                           |
                  +--------+--------+
                  |                 |
                  v                 v
             patch writer       rebuild writer
             source OOXML       synthetic OOXML
                  |                 |
                  +--------+--------+
                           v
                         output
```

The intellectual lineage is:

- MarkItDown: converter selection and format ingestion;
- Docling: rich canonical document model and provenance;
- Pandoc: reader/IR/writer separation;
- pptx-automizer: preserve the existing PPTX and patch native XML using stable identities;
- PptxGenJS: generated-presentation capability;
- Marp: Markdown authoring semantics and a warning against raster/PDF reconstruction as fidelity infrastructure;
- python-pptx: practical Python implementation substrate already inside MarkItDown's dependency ecosystem.

## 9. Technical decisions resulting from the study

### Decision 1 — canonical IR, not canonical Markdown

Ordinary Markdown cannot encode all layout, theme, relationship, chart, animation, object and provenance information required by round trip.

### Decision 2 — two writer modes

- `patch`: source-preserving and provenance-required;
- `rebuild`: synthetic generation and explicit fidelity downgrade.

`auto` may select between them; strict `patch` never silently becomes `rebuild`.

### Decision 3 — source package preservation

A rich IR still cannot model every OOXML extension. A portable `.m2w` bundle can preserve the original package and assets so unknown native content survives.

### Decision 4 — explicit edit operations

AI/human edits should become typed operations with preconditions. This makes mutation auditable, testable and safely translatable to format-specific writers.

### Decision 5 — stable object identity is first-class

The IR needs native locators in addition to semantic ids. For PPTX, `creationId` is preferred when present.

### Decision 6 — evidence-based fidelity

Writers return a fidelity report. Patch mode compares ZIP/package parts, validates relationships, reopens output and re-reads edited targets.

### Decision 7 — keep core lightweight

No mandatory Docling, Node.js, LibreOffice, browser engine, or cloud service. Those can be optional bridges.

### Decision 8 — preserve upstream mergeability

Most new code belongs under `markitdown.twoways`. Existing converters are modified only for safe shared helpers or explicit compatibility hooks.

## 10. Initial benchmark scenarios

The engineering work should be benchmarked against realistic tasks, not only unit objects.

### PPTX benchmark A — tiny text edit

Input: professionally designed deck with masters, charts, images and unknown extension data.  
Edit: change one sentence on slide 4.  
Success: requested text changes; unrelated package members remain unchanged where feasible; deck reopens; fidelity tier is `exact-preserve` or `high` with evidence.

### PPTX benchmark B — image replacement

Input: deck with crop/position/alt text.  
Edit: replace one image while retaining placement.  
Success: relationships are valid, untouched media unchanged, requested image digest appears in output.

### PPTX benchmark C — Markdown-originated rebuild

Input: marked-up Markdown with slide directives.  
Output: editable PPTX.  
Success: semantic/layout contract is satisfied; fidelity correctly reports `reconstructed` rather than pretending it is a round trip.

### Markdown projection benchmark

Input: PPTX -> Document IR -> identity-marked Markdown.  
Edit: change one paragraph in Markdown.  
Success: re-import creates a deterministic `ReplaceText` operation on the original node without deleting geometry/style/native metadata.

## 11. Things deliberately not copied

- Pandoc source code or AST implementation.
- Marp's PDF -> LibreOffice editable-PPTX pipeline.
- pptx-automizer's Node-specific execution model.
- Docling's complete schema as a dependency of the core.
- PptxGenJS as a mandatory runtime.

We adopt proven architectural ideas while building a Python-native, upstream-compatible implementation suited to MarkItDown's existing codebase.
