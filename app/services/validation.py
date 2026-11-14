from __future__ import annotations

from typing import Any

from app.services.registry import SchemaUnavailableError, schema_path
from app.services.xml_safety import (
    MAX_XML_CHARS,
    UntrustedXmlError,
    ValidatorUnavailableError,
    parse_untrusted_xml,
    safe_parser,
)

__all__ = [
    "MAX_XML_CHARS",
    "SchemaConfigurationError",
    "ValidatorUnavailableError",
    "validate_message",
]


class SchemaConfigurationError(Exception):
    """Raised when a registered local XSD cannot be parsed or compiled."""


def _rejected(message_id: str, kind: str, error: dict[str, Any]) -> dict[str, Any]:
    return {"message_id": message_id, "valid": False, "kind": kind, "errors": [error], "errors_truncated": False}


def validate_message(message_id: str, xml: str) -> dict[str, Any]:
    if len(xml) > MAX_XML_CHARS:
        raise ValueError(f"XML input exceeds the {MAX_XML_CHARS:,}-character limit.")
    selected_schema = schema_path(message_id)
    if selected_schema is None:
        raise SchemaUnavailableError(message_id)

    try:
        xml_root = parse_untrusted_xml(xml)
    except UntrustedXmlError as exc:
        return _rejected(message_id, exc.kind, exc.as_error())

    from lxml import etree

    try:
        schema = etree.XMLSchema(etree.parse(str(selected_schema), parser=safe_parser()))
    except (etree.XMLSyntaxError, etree.XMLSchemaParseError) as exc:
        raise SchemaConfigurationError from exc

    try:
        valid = schema.validate(xml_root)
    except etree.XMLSchemaValidateError:
        error = UntrustedXmlError("unsupported_xml", "XSD_VALIDATOR_ERROR", "The XML could not be processed by the schema validator.")
        return _rejected(message_id, error.kind, error.as_error())
    error_entries = list(schema.error_log)
    errors = [
        {
            "code": (entry.type_name or "XSD_VALIDATION_ERROR")[:100],
            "message": entry.message[:500],
            "line": entry.line or None,
            "column": entry.column or None,
            "xpath": entry.path,
        }
        for entry in error_entries[:100]
    ]
    return {
        "message_id": message_id,
        "valid": valid,
        "kind": "xsd_validation",
        "errors": errors,
        "errors_truncated": len(error_entries) > len(errors),
    }
