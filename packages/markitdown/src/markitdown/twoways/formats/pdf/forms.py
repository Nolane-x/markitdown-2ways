from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import re

from pypdf import PdfReader
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DictionaryObject,
    IndirectObject,
    TextStringObject,
)

from .limits import PdfNativeLimits
from .model import PdfParseError, PdfTextFieldEvidence

_UNSUPPORTED_TEXT_FLAGS = (1 << 12) | (1 << 13) | (1 << 20) | (1 << 24) | (1 << 25)
_READ_ONLY_FLAG = 1
_PDF_WS = r"\x00\x09\x0A\x0C\x0D\x20"
_DA_TF_PATTERN = re.compile(
    rf"(?:^|[{_PDF_WS}])"
    rf"(/[^\s()<>\[\]{{}}/%]+)"
    rf"[{_PDF_WS}]+"
    rf"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
    rf"[{_PDF_WS}]+Tf(?=$|[{_PDF_WS}/()<>\[\]{{}}%])"
)


def _raw_get(mapping: object, key: str) -> object | None:
    raw_get = getattr(mapping, "raw_get", None)
    if callable(raw_get):
        try:
            return raw_get(key)
        except KeyError:
            return None
    try:
        return mapping[key]  # type: ignore[index]
    except (KeyError, TypeError):
        return None


def _objgen(value: object) -> tuple[int, int] | None:
    if isinstance(value, IndirectObject):
        return (value.idnum, value.generation)
    return None


def _resolve(value: object) -> object:
    if isinstance(value, IndirectObject):
        return value.get_object()
    return value


def _canonical_pdf_value(
    value: object,
    *,
    depth: int,
    max_depth: int,
) -> object:
    if depth > max_depth:
        raise PdfParseError(
            "PDF AcroForm semantic nesting exceeds the configured depth limit.",
            reason="pdf.form.tree_ambiguous",
            details={"depth": depth, "limit": max_depth},
        )
    if isinstance(value, IndirectObject):
        return ("ref", value.idnum, value.generation)
    if isinstance(value, DictionaryObject):
        return (
            "dict",
            tuple(
                sorted(
                    (
                        str(key),
                        _canonical_pdf_value(
                            item,
                            depth=depth + 1,
                            max_depth=max_depth,
                        ),
                    )
                    for key, item in value.items()
                )
            ),
        )
    if isinstance(value, (ArrayObject, list, tuple)):
        return (
            "array",
            tuple(
                _canonical_pdf_value(
                    item,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
                for item in value
            ),
        )
    if isinstance(value, bytes):
        return ("bytes", value.hex())
    if isinstance(value, str):
        return ("text", str(value))
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, float):
        return ("float", value)
    if value is None:
        return ("null", None)
    return (type(value).__name__, repr(value))


def _semantic_digest(value: object, *, max_depth: int) -> str:
    canonical = _canonical_pdf_value(value, depth=0, max_depth=max_depth)
    return sha256(repr(canonical).encode("utf-8")).hexdigest()


def _field_immutable_digest(
    field: DictionaryObject,
    *,
    acroform_objgen: tuple[int, int],
    page_index: int,
    annotation_index: int,
    max_depth: int,
) -> str:
    items: list[tuple[str, object]] = []
    for key, value in field.items():
        key_text = str(key)
        encoded = (
            ("editable-form-value",)
            if key_text == "/V"
            else _canonical_pdf_value(
                value,
                depth=1,
                max_depth=max_depth,
            )
        )
        items.append((key_text, encoded))
    evidence = (
        "pdf-form-text-immutable",
        acroform_objgen,
        page_index,
        annotation_index,
        tuple(sorted(items)),
    )
    return sha256(repr(evidence).encode("utf-8")).hexdigest()


def _field_locator_digest(
    *,
    field_name: str,
    field_objgen: tuple[int, int],
    acroform_objgen: tuple[int, int],
    page_index: int,
    annotation_index: int,
    field_type: str,
    value: str,
) -> str:
    evidence = (
        "pdf-form-text-value",
        field_name,
        field_objgen,
        acroform_objgen,
        page_index,
        annotation_index,
        field_type,
        value,
    )
    return sha256(repr(evidence).encode("utf-8")).hexdigest()


def _as_array(value: object, *, reason: str) -> ArrayObject | list | tuple:
    try:
        resolved = _resolve(value)
    except Exception as exc:
        raise PdfParseError(
            "Unable to resolve PDF AcroForm array authority.",
            reason=reason,
        ) from exc
    if not isinstance(resolved, (ArrayObject, list, tuple)):
        raise PdfParseError(
            "PDF AcroForm authority is not represented by an array.",
            reason=reason,
        )
    return resolved


def _page_bindings(
    annotation_topology: tuple[tuple[tuple[int, int] | None, ...], ...],
) -> dict[tuple[int, int], list[tuple[int, int]]]:
    bindings: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for page_index, page in enumerate(annotation_topology):
        for annotation_index, objgen in enumerate(page):
            if objgen is not None:
                bindings.setdefault(objgen, []).append((page_index, annotation_index))
    return bindings


def _default_resource_fonts(acroform: DictionaryObject) -> DictionaryObject | None:
    dr_ref = _raw_get(acroform, "/DR")
    if dr_ref is None:
        return None
    try:
        dr = _resolve(dr_ref)
    except Exception:
        return None
    if not isinstance(dr, DictionaryObject):
        return None
    font_ref = _raw_get(dr, "/Font")
    if font_ref is None:
        return None
    try:
        fonts = _resolve(font_ref)
    except Exception:
        return None
    if not isinstance(fonts, DictionaryObject) or not fonts:
        return None
    return fonts


def _has_default_appearance_authority(
    acroform: DictionaryObject,
    field: DictionaryObject,
    *,
    default_fonts: DictionaryObject | None,
) -> bool:
    if default_fonts is None:
        return False
    da_raw = _raw_get(field, "/DA")
    if da_raw is None:
        da_raw = _raw_get(acroform, "/DA")
    if not isinstance(da_raw, TextStringObject):
        return False
    da = str(da_raw).strip()
    if not da or any(char in da for char in "()<>[]{}%"):
        return False
    matches = tuple(_DA_TF_PATTERN.finditer(da))
    if not matches:
        return False
    font_name = matches[-1].group(1)
    font_ref = next(
        (value for key, value in default_fonts.items() if str(key) == font_name),
        None,
    )
    if font_ref is None:
        return False
    try:
        font = _resolve(font_ref)
    except Exception:
        return False
    if not isinstance(font, DictionaryObject):
        return False
    if str(font.get("/Type", "")) != "/Font":
        return False
    return str(font.get("/Subtype", "")).startswith("/")


def collect_text_fields(
    reader: PdfReader,
    *,
    limits: PdfNativeLimits,
    source_policy_blocked: bool,
    annotation_topology: tuple[tuple[tuple[int, int] | None, ...], ...],
) -> tuple[
    tuple[PdfTextFieldEvidence, ...],
    tuple[int, int] | None,
    tuple[tuple[int, int] | None, ...],
    tuple[tuple[tuple[int, int], int, int], ...],
    tuple[tuple[tuple[int, int], str], ...],
    bool | None,
]:
    try:
        root = reader.root_object
    except Exception as exc:
        raise PdfParseError(
            "Unable to establish PDF AcroForm catalog authority.",
            reason="pdf.form.tree_ambiguous",
        ) from exc

    acroform_ref = _raw_get(root, "/AcroForm")
    acroform_objgen = _objgen(acroform_ref)
    if acroform_ref is None or acroform_objgen is None:
        return ((), None, (), (), (), None)
    try:
        acroform = _resolve(acroform_ref)
    except Exception as exc:
        raise PdfParseError(
            "Unable to resolve PDF AcroForm authority.",
            reason="pdf.form.tree_ambiguous",
        ) from exc
    if not isinstance(acroform, DictionaryObject):
        raise PdfParseError(
            "PDF AcroForm does not resolve to a dictionary.",
            reason="pdf.form.tree_ambiguous",
        )

    fields_ref = _raw_get(acroform, "/Fields")
    if fields_ref is None:
        return ((), acroform_objgen, (), (), (), None)
    roots = _as_array(fields_ref, reason="pdf.form.tree_ambiguous")
    root_topology = tuple(_objgen(item) for item in roots)

    need_raw = _raw_get(acroform, "/NeedAppearances")
    if isinstance(need_raw, BooleanObject):
        need_appearances: bool | None = bool(need_raw.value)
    else:
        need_appearances = None

    acroform_reason: str | None = None
    if source_policy_blocked:
        acroform_reason = "pdf.form.source_policy"
    elif need_appearances is not True:
        acroform_reason = "pdf.form.need_appearances_required"
    elif "/XFA" in acroform:
        acroform_reason = "pdf.form.xfa"
    elif "/CO" in acroform:
        acroform_reason = "pdf.form.calculation_order"
    elif "/AA" in acroform or "/A" in acroform:
        acroform_reason = "pdf.form.additional_actions"

    default_fonts = _default_resource_fonts(acroform)
    bindings_by_objgen = _page_bindings(annotation_topology)
    stack: list[tuple[object, int]] = [(item, 1) for item in reversed(roots)]
    seen: set[tuple[int, int]] = set()
    ambiguous_owners: set[tuple[int, int]] = set()
    collected: list[tuple[PdfTextFieldEvidence, DictionaryObject]] = []
    total_value_chars = 0
    traversed_fields = 0
    unstable_direct_owner_seen = False

    while stack:
        field_ref, depth = stack.pop()
        if depth > limits.max_field_tree_depth:
            raise PdfParseError(
                "PDF AcroForm field tree exceeds the configured depth limit.",
                reason="pdf.form.tree_ambiguous",
                details={"depth": depth, "limit": limits.max_field_tree_depth},
            )
        traversed_fields += 1
        if traversed_fields > limits.max_total_form_fields:
            raise PdfParseError(
                "PDF AcroForm field count exceeds the configured limit.",
                reason="pdf.form.too_many_fields",
                details={
                    "field_count": traversed_fields,
                    "limit": limits.max_total_form_fields,
                },
            )
        field_objgen = _objgen(field_ref)
        if field_objgen is None:
            unstable_direct_owner_seen = True
            continue
        if field_objgen in seen:
            ambiguous_owners.add(field_objgen)
            continue
        seen.add(field_objgen)
        try:
            field = _resolve(field_ref)
        except Exception as exc:
            raise PdfParseError(
                "Unable to resolve PDF AcroForm field authority.",
                reason="pdf.form.tree_ambiguous",
                details={"field_objgen": field_objgen},
            ) from exc
        if not isinstance(field, DictionaryObject):
            raise PdfParseError(
                "PDF AcroForm field does not resolve to a dictionary.",
                reason="pdf.form.tree_ambiguous",
                details={"field_objgen": field_objgen},
            )

        kids_ref = _raw_get(field, "/Kids")
        if kids_ref is not None:
            kids = _as_array(kids_ref, reason="pdf.form.tree_ambiguous")
            for kid in reversed(kids):
                stack.append((kid, depth + 1))

        name_raw = _raw_get(field, "/T")
        value_raw = _raw_get(field, "/V")
        subtype = str(field.get("/Subtype", ""))
        if not isinstance(name_raw, TextStringObject) or value_raw is None:
            continue
        field_name = str(name_raw)
        if len(field_name) > limits.max_field_name_chars:
            raise PdfParseError(
                "PDF AcroForm field name exceeds the configured character limit.",
                reason="pdf.form.value_too_large",
                details={
                    "field_objgen": field_objgen,
                    "field_name_chars": len(field_name),
                    "limit": limits.max_field_name_chars,
                },
            )

        value_is_text = isinstance(value_raw, TextStringObject)
        value = str(value_raw) if value_is_text else ""
        if value_is_text and len(value) > limits.max_form_value_chars:
            raise PdfParseError(
                "PDF AcroForm value exceeds the configured character limit.",
                reason="pdf.form.value_too_large",
                details={
                    "field_objgen": field_objgen,
                    "value_chars": len(value),
                    "limit": limits.max_form_value_chars,
                },
            )
        total_value_chars += len(value)
        if total_value_chars > limits.max_total_form_value_chars:
            raise PdfParseError(
                "PDF AcroForm values exceed the configured total character limit.",
                reason="pdf.form.total_value_too_large",
                details={
                    "value_chars": total_value_chars,
                    "limit": limits.max_total_form_value_chars,
                },
            )

        field_type = str(field.get("/FT", ""))
        flags_raw = _raw_get(field, "/Ff")
        if flags_raw is None:
            field_flags = 0
            flags_valid = True
        elif isinstance(flags_raw, int) and not isinstance(flags_raw, bool):
            field_flags = int(flags_raw)
            flags_valid = field_flags >= 0
        else:
            field_flags = 0
            flags_valid = False

        max_len_raw = _raw_get(field, "/MaxLen")
        max_len: int | None = None
        max_len_valid = True
        if max_len_raw is not None:
            if isinstance(max_len_raw, int) and not isinstance(max_len_raw, bool):
                max_len = int(max_len_raw)
                max_len_valid = max_len >= 0
            else:
                max_len_valid = False

        page_slots = bindings_by_objgen.get(field_objgen, [])
        if len(page_slots) == 1:
            page_index, annotation_index = page_slots[0]
        else:
            page_index, annotation_index = (-1, -1)

        reason = acroform_reason
        if reason is None and not field_name:
            reason = "pdf.form.field_name"
        elif reason is None and ("/Parent" in field or "/Kids" in field):
            reason = "pdf.form.field_hierarchy"
        elif reason is None and field_type != "/Tx":
            reason = "pdf.form.field_type"
        elif reason is None and subtype != "/Widget":
            reason = "pdf.form.widget_binding"
        elif reason is None and not value_is_text:
            reason = "pdf.form.non_text_value"
        elif reason is None and ("\r" in value or "\n" in value):
            reason = "pdf.form.unsupported_text_mode"
        elif reason is None and ("/AA" in field or "/A" in field):
            reason = "pdf.form.additional_actions"
        elif reason is None and "/AP" in field:
            reason = "pdf.form.appearance_present"
        elif reason is None and not _has_default_appearance_authority(
            acroform,
            field,
            default_fonts=default_fonts,
        ):
            reason = "pdf.form.appearance_authority"
        elif reason is None and not flags_valid:
            reason = "pdf.form.unsupported_text_mode"
        elif reason is None and field_flags & _READ_ONLY_FLAG:
            reason = "pdf.form.read_only"
        elif reason is None and field_flags & _UNSUPPORTED_TEXT_FLAGS:
            reason = "pdf.form.unsupported_text_mode"
        elif reason is None and not max_len_valid:
            reason = "pdf.form.max_length"
        elif reason is None and max_len is not None and len(value) > max_len:
            reason = "pdf.form.max_length"
        elif reason is None and len(page_slots) != 1:
            reason = "pdf.form.widget_binding"

        evidence = PdfTextFieldEvidence(
            field_name=field_name,
            field_objgen=field_objgen,
            page_index=page_index,
            annotation_index=annotation_index,
            value=value,
            field_type=field_type,
            field_flags=field_flags,
            max_len=max_len,
            acroform_objgen=acroform_objgen,
            need_appearances=need_appearances is True,
            locator_digest=_field_locator_digest(
                field_name=field_name,
                field_objgen=field_objgen,
                acroform_objgen=acroform_objgen,
                page_index=page_index,
                annotation_index=annotation_index,
                field_type=field_type,
                value=value,
            ),
            immutable_digest=_field_immutable_digest(
                field,
                acroform_objgen=acroform_objgen,
                page_index=page_index,
                annotation_index=annotation_index,
                max_depth=limits.max_field_tree_depth,
            ),
            writable=reason is None,
            reason_code=reason,
        )
        collected.append((evidence, field))

    name_counts: dict[str, int] = {}
    for evidence, _ in collected:
        name_counts[evidence.field_name] = name_counts.get(evidence.field_name, 0) + 1

    final_fields: list[PdfTextFieldEvidence] = []
    form_bindings: list[tuple[tuple[int, int], int, int]] = []
    fingerprints: list[tuple[tuple[int, int], str]] = []
    for evidence, field in collected:
        reason = evidence.reason_code
        if (
            unstable_direct_owner_seen
            or evidence.field_objgen in ambiguous_owners
            or name_counts[evidence.field_name] > 1
        ):
            reason = "pdf.form.tree_ambiguous"
        final = replace(
            evidence,
            writable=reason is None,
            reason_code=reason,
        )
        final_fields.append(final)
        slots = bindings_by_objgen.get(evidence.field_objgen, [])
        if len(slots) == 1:
            form_bindings.append((evidence.field_objgen, slots[0][0], slots[0][1]))
        fingerprints.append(
            (
                evidence.field_objgen,
                _semantic_digest(
                    field,
                    max_depth=limits.max_field_tree_depth,
                ),
            )
        )

    return (
        tuple(final_fields),
        acroform_objgen,
        root_topology,
        tuple(form_bindings),
        tuple(fingerprints),
        need_appearances,
    )
