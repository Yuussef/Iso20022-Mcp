"""Small helpers for reading ISO 20022 XML trees and reporting rule findings."""

from __future__ import annotations

import re
from typing import Any

MESSAGE_NAMESPACE = re.compile(r"urn:iso:std:iso:20022:tech:xsd:([a-z]{4}\.\d{3}\.\d{3}\.\d{2,3})$")


def local_name(element: Any) -> str:
    """Element name without its namespace ("" for comments and processing instructions)."""
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def children(element: Any) -> list[Any]:
    return [child for child in element if isinstance(child.tag, str)]


def child(element: Any, name: str) -> Any | None:
    return next((item for item in children(element) if local_name(item) == name), None)


def descendant(element: Any, *names: str) -> Any | None:
    """Follow a path of child names, e.g. descendant(tx, "DbtrAcct", "Id", "IBAN")."""
    node = element
    for name in names:
        if node is None:
            return None
        node = child(node, name)
    return node


def find_all(root: Any, name: str) -> list[Any]:
    return [element for element in root.iter() if isinstance(element.tag, str) and local_name(element) == name]


def text(element: Any | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def path(element: Any) -> str:
    """Readable XPath built from local names, indexing repeated siblings: /Document/A/B[2]/C."""
    parts = []
    node = element
    while node is not None:
        name = local_name(node)
        parent = node.getparent()
        if parent is not None:
            same_name = [sibling for sibling in children(parent) if local_name(sibling) == name]
            if len(same_name) > 1:
                name = f"{name}[{same_name.index(node) + 1}]"
        parts.append(name)
        node = parent
    return "/" + "/".join(reversed(parts))


def message_id(root: Any) -> str | None:
    """The ISO 20022 message identifier taken from the first non-header namespace, e.g. pacs.008.001.08."""
    for element in root.iter():
        if not isinstance(element.tag, str) or not element.tag.startswith("{"):
            continue
        match = MESSAGE_NAMESPACE.match(element.tag[1:].split("}", 1)[0])
        if match and not match.group(1).startswith("head."):
            return match.group(1)
    return None


def finding(rule: str, severity: str, message: str, xpath: str, suggestion: str | None = None) -> dict[str, Any]:
    return {"rule": rule, "severity": severity, "message": message, "xpath": xpath, "suggestion": suggestion}
