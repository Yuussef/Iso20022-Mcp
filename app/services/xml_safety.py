"""Hardened parsing for untrusted XML, shared by every service that reads user-supplied messages."""

from __future__ import annotations

from typing import Any

MAX_XML_CHARS = 1_000_000


class ValidatorUnavailableError(Exception):
    """Raised when the lxml dependency is not installed."""


class UntrustedXmlError(Exception):
    """The input is not XML this service will process (malformed, or carries a DTD)."""

    def __init__(self, kind: str, code: str, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.code = code
        self.message = message
        self.line = line

    def as_error(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "line": self.line, "column": None, "xpath": None}


def _etree() -> Any:
    try:
        from lxml import etree
    except ImportError as exc:
        raise ValidatorUnavailableError from exc
    return etree


def safe_parser() -> Any:
    """A parser that never touches the network, never expands entities and never loads DTDs."""
    etree = _etree()
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False, recover=False)


def parse_untrusted_xml(xml: str) -> Any:
    """Parse user-supplied XML and return its root element.

    Raises ValueError when the input is too large, and UntrustedXmlError when it is
    malformed or declares a DOCTYPE (ISO 20022 messages never carry one).
    """
    if len(xml) > MAX_XML_CHARS:
        raise ValueError(f"XML input exceeds the {MAX_XML_CHARS:,}-character limit.")
    etree = _etree()
    try:
        root = etree.fromstring(xml.encode("utf-8"), parser=safe_parser())
    except etree.XMLSyntaxError as exc:
        raise UntrustedXmlError("malformed_xml", "XML_SYNTAX_ERROR", str(exc).split(", line")[0][:500], exc.lineno) from exc
    # Entities are already left unexpanded by the parser, but unresolved entity references
    # make lxml's XSD validator raise, so reject any DOCTYPE up front.
    if root.getroottree().docinfo.doctype:
        raise UntrustedXmlError("unsupported_xml", "DTD_NOT_ALLOWED", "XML documents with a DOCTYPE declaration are not accepted.")
    return root
