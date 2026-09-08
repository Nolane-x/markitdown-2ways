from __future__ import annotations

from dataclasses import dataclass, field

from ...ooxml import OOXMLPackageLimits


@dataclass(frozen=True)
class PptxReadOptions:
    include_notes: bool = True
    include_resources: bool = True
    preserve_unknown_native: bool = True
    limits: OOXMLPackageLimits = field(default_factory=OOXMLPackageLimits)


@dataclass(frozen=True)
class PptxPatchOptions:
    strict: bool = True
    verify_output: bool = True
    preserve_zip_metadata: bool = True
    limits: OOXMLPackageLimits = field(default_factory=OOXMLPackageLimits)
