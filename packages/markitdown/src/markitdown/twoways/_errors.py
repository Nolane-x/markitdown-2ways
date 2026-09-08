from __future__ import annotations

from typing import Any, Mapping


class TwoWayError(Exception):
    """Base exception for the MarkItDown 2Ways subsystem."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


class _NamedTwoWayError(TwoWayError):
    default_code = "two_way.error"

    def __init__(
        self,
        message: str,
        details: Mapping[str, Any] | None = None,
        *,
        code: str | None = None,
    ) -> None:
        super().__init__(code or self.default_code, message, details)


class IRValidationError(_NamedTwoWayError):
    default_code = "two_way.ir_validation"


class UnsupportedSchemaVersionError(_NamedTwoWayError):
    default_code = "two_way.unsupported_schema_version"


class ReaderNotFoundError(_NamedTwoWayError):
    default_code = "two_way.reader_not_found"


class WriterNotFoundError(_NamedTwoWayError):
    default_code = "two_way.writer_not_found"


class UnsupportedEditError(_NamedTwoWayError):
    default_code = "two_way.unsupported_edit"


class SourcePackageMismatchError(_NamedTwoWayError):
    default_code = "two_way.source_package_mismatch"


class AmbiguousNativeLocatorError(_NamedTwoWayError):
    default_code = "two_way.ambiguous_native_locator"


class PatchPreconditionError(_NamedTwoWayError):
    default_code = "two_way.patch_precondition"


class RoundTripVerificationError(_NamedTwoWayError):
    default_code = "two_way.round_trip_verification"


class MarkdownProjectionError(_NamedTwoWayError):
    default_code = "markdown.projection"


class MarkdownImportError(_NamedTwoWayError):
    default_code = "markdown.import"


class MarkdownIdentityError(_NamedTwoWayError):
    default_code = "markdown.identity"


class MarkdownSemanticParseError(_NamedTwoWayError):
    default_code = "markdown.semantic_parse"
