from __future__ import annotations

from hashlib import sha256
import re

from ..ir.document import Canvas, Diagnostic, DocumentIR, SourceDescriptor
from ..ir.nodes import ImagePayload, Node, Paragraph, TableCell, TablePayload, TextPayload, TextRun
from ..ir.resources import Resource
from ..ir.style import Style
from ..ir.serialization import validate_document


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_LIST_RE = re.compile(r"^(\s*)([-+*]|\d+\.)\s+(.+)$")
_IMAGE_RE = re.compile(r"^!\[(.*?)\]\((.*?)\)$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_INLINE_TOKEN_RE = re.compile(r"(\*\*[^*]+\*\*|(?<!\*)\*[^*]+\*(?!\*)|`[^`]+`)")


def _stable_id(document_id: str, ordinal: int, kind: str, content: str) -> str:
    material = f"{document_id}\0{ordinal}\0{kind}\0{content}".encode("utf-8")
    return f"{kind}-" + sha256(material).hexdigest()[:24]


def _resource_id(document_id: str, uri: str) -> str:
    material = f"{document_id}\0resource\0{uri}".encode("utf-8")
    return "resource-" + sha256(material).hexdigest()[:24]


def _inline_runs(text: str) -> tuple[TextRun, ...]:
    runs: list[TextRun] = []
    pos = 0
    for match in _INLINE_TOKEN_RE.finditer(text):
        if match.start() > pos:
            runs.append(TextRun(text[pos:match.start()]))
        token = match.group(0)
        if token.startswith("**") and token.endswith("**"):
            runs.append(TextRun(token[2:-2], style=Style(direct={"bold": True})))
        elif token.startswith("*") and token.endswith("*"):
            runs.append(TextRun(token[1:-1], style=Style(direct={"italic": True})))
        elif token.startswith("`") and token.endswith("`"):
            runs.append(TextRun(token[1:-1], style=Style(direct={"code": True})))
        pos = match.end()
    if pos < len(text):
        runs.append(TextRun(text[pos:]))
    if not runs:
        runs.append(TextRun(text))
    return tuple(runs)


def _plain_from_runs(runs: tuple[TextRun, ...]) -> str:
    return "".join(run.text for run in runs)


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_special_start(lines: list[str], index: int) -> bool:
    line = lines[index]
    if not line.strip():
        return True
    if line.startswith("```"):
        return True
    if _HEADING_RE.match(line) or _LIST_RE.match(line) or _IMAGE_RE.match(line):
        return True
    if index + 1 < len(lines) and "|" in line and _TABLE_SEPARATOR_RE.match(lines[index + 1]):
        return True
    return False


def read_markdown_ir(
    markdown: str,
    *,
    document_id: str | None = None,
    source_name: str | None = None,
) -> DocumentIR:
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")
    diagnostics: list[Diagnostic] = []
    if document_id is None:
        document_id = "local-document-1"
        diagnostics.append(Diagnostic(
            code="markdown.semantic.non_reproducible_id",
            severity="warning",
            message="No deterministic document_id was supplied; generated ids are local to this parse.",
        ))

    lines = text.split("\n")
    nodes: dict[str, Node] = {}
    resources: dict[str, Resource] = {}
    root_ids: list[str] = []
    ordinal = 0
    index = 0

    def add_node(node: Node) -> None:
        nonlocal ordinal
        nodes[node.node_id] = node
        root_ids.append(node.node_id)
        ordinal += 1

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        if line.startswith("```"):
            language = line[3:].strip() or None
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and lines[index] != "```":
                code_lines.append(lines[index])
                index += 1
            if index < len(lines) and lines[index] == "```":
                index += 1
            code = "\n".join(code_lines)
            node_id = _stable_id(document_id, ordinal, "text", f"code\0{language or ''}\0{code}")
            add_node(Node(
                node_id=node_id,
                kind="text",
                semantic_role="code",
                order=ordinal,
                canvas_id="flow",
                payload=TextPayload(text=code, paragraphs=(Paragraph(runs=(TextRun(code),)),)),
                metadata={"language": language} if language else {},
            ))
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            content = heading.group(2)
            runs = _inline_runs(content)
            plain = _plain_from_runs(runs)
            role = "title" if level == 1 else f"heading{level}"
            node_id = _stable_id(document_id, ordinal, "text", f"{role}\0{plain}")
            add_node(Node(
                node_id=node_id,
                kind="text",
                semantic_role=role,
                order=ordinal,
                canvas_id="flow",
                payload=TextPayload(text=plain, paragraphs=(Paragraph(runs=runs),)),
            ))
            index += 1
            continue

        list_match = _LIST_RE.match(line)
        if list_match:
            indent, marker, content = list_match.groups()
            level = max(len(indent) // 2, 0)
            ordered = marker.endswith(".") and marker[:-1].isdigit()
            runs = _inline_runs(content)
            plain = _plain_from_runs(runs)
            node_id = _stable_id(document_id, ordinal, "text", f"list\0{level}\0{ordered}\0{plain}")
            add_node(Node(
                node_id=node_id,
                kind="text",
                semantic_role="list_item",
                order=ordinal,
                canvas_id="flow",
                payload=TextPayload(text=plain, paragraphs=(Paragraph(runs=runs, list_level=level),)),
                metadata={"ordered": ordered},
            ))
            index += 1
            continue

        image_match = _IMAGE_RE.match(line)
        if image_match:
            alt, uri = image_match.groups()
            resource_id = _resource_id(document_id, uri)
            resources.setdefault(resource_id, Resource(
                resource_id=resource_id,
                metadata={"source_uri": uri},
            ))
            node_id = _stable_id(document_id, ordinal, "image", f"{alt}\0{uri}")
            add_node(Node(
                node_id=node_id,
                kind="image",
                order=ordinal,
                canvas_id="flow",
                payload=ImagePayload(resource_id=resource_id, alt_text=alt),
                metadata={"source_uri": uri},
            ))
            index += 1
            continue

        if index + 1 < len(lines) and "|" in line and _TABLE_SEPARATOR_RE.match(lines[index + 1]):
            rows: list[list[str]] = [_split_table_row(line)]
            index += 2
            while index < len(lines) and lines[index].strip() and "|" in lines[index]:
                rows.append(_split_table_row(lines[index]))
                index += 1
            columns = max((len(row) for row in rows), default=0)
            cells: list[TableCell] = []
            for row_index, row in enumerate(rows):
                for column in range(columns):
                    cells.append(TableCell(
                        row=row_index,
                        column=column,
                        text=row[column] if column < len(row) else "",
                    ))
            semantic = "\n".join("\t".join(row) for row in rows)
            node_id = _stable_id(document_id, ordinal, "table", semantic)
            add_node(Node(
                node_id=node_id,
                kind="table",
                order=ordinal,
                canvas_id="flow",
                payload=TablePayload(rows=len(rows), columns=columns, cells=tuple(cells)),
            ))
            continue

        paragraph_lines = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not _is_special_start(lines, index):
            paragraph_lines.append(lines[index])
            index += 1
        content = "\n".join(paragraph_lines)
        runs = _inline_runs(content)
        plain = _plain_from_runs(runs)
        node_id = _stable_id(document_id, ordinal, "text", f"paragraph\0{plain}")
        add_node(Node(
            node_id=node_id,
            kind="text",
            semantic_role="paragraph",
            order=ordinal,
            canvas_id="flow",
            payload=TextPayload(text=plain, paragraphs=(Paragraph(runs=runs),)),
        ))

    canvas = Canvas(canvas_id="flow", index=0, kind="flow", root_node_ids=tuple(root_ids))
    document = DocumentIR(
        document_id=document_id,
        source=SourceDescriptor(format="markdown", filename=source_name),
        canvases=(canvas,),
        nodes=nodes,
        root_node_ids=tuple(root_ids),
        resources=resources,
        diagnostics=tuple(diagnostics),
    )
    validate_document(document)
    return document
