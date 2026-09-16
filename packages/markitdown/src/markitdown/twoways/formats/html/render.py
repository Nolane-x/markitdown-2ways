from __future__ import annotations

from .lexical import parse_html_source


def _escape_common(value: str) -> str:
    parts: list[str] = []
    for character in value:
        if character == "&":
            parts.append("&amp;")
        elif character == "<":
            parts.append("&lt;")
        elif character == ">":
            parts.append("&gt;")
        elif character == "\r":
            parts.append("&#13;")
        else:
            parts.append(character)
    return "".join(parts)


def _semantic_value(source: str, path: str) -> str:
    parsed = parse_html_source(source.encode("utf-8"), encoding="utf-8")
    if not parsed.recovery_stable:
        raise ValueError("rendered HTML validation wrapper became recovery-unstable")
    matches = [node for node in parsed.lexical.nodes if node.path == path]
    if len(matches) != 1 or not isinstance(matches[0].value, str):
        raise ValueError("rendered HTML validation wrapper lost scalar ownership")
    return matches[0].value


def render_html_text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("HTML text replacement must be a string")
    token = _escape_common(value)
    wrapper = f"<html><body><p>{token}</p></body></html>"
    if _semantic_value(wrapper, "/html[1]/body[1]/p[1]/#text[1]") != value:
        raise ValueError("HTML text rendering changed requested semantics")
    return token


def render_html_attribute(value: str, quote: str) -> str:
    if not isinstance(value, str):
        raise TypeError("HTML attribute replacement must be a string")
    if quote not in {"'", '"'}:
        raise ValueError("HTML writable attributes require an existing quote style")

    parts: list[str] = []
    for character in value:
        if character == "&":
            parts.append("&amp;")
        elif character == "<":
            parts.append("&lt;")
        elif character == ">":
            parts.append("&gt;")
        elif character == quote:
            parts.append("&quot;" if quote == '"' else "&#39;")
        elif character == "\t":
            parts.append("&#9;")
        elif character == "\n":
            parts.append("&#10;")
        elif character == "\r":
            parts.append("&#13;")
        else:
            parts.append(character)
    token = "".join(parts)
    wrapper = f"<html><body><p data-x={quote}{token}{quote}>x</p></body></html>"
    if _semantic_value(wrapper, "/html[1]/body[1]/p[1]/@data-x") != value:
        raise ValueError("HTML attribute rendering changed requested semantics")
    return token
