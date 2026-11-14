from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from app.services.identifiers import validate_bic as validate_bic_service
from app.services.identifiers import validate_iban as validate_iban_service
from app.services.knowledge_search import search_documents
from app.services.postal_address import check_postal_addresses
from app.services.registry import SchemaUnavailableError, supported_messages
from app.services.sepa_sct import check_sepa_sct as check_sepa_sct_service
from app.services.validation import (
    SchemaConfigurationError,
    ValidatorUnavailableError,
)
from app.services.validation import (
    validate_message as validate_xml_message,
)

mcp = MCPServer(name="PayDoc AI ISO 20022", version="0.1.0")


@mcp.tool()
def list_supported_messages() -> dict[str, Any]:
    """List the ISO 20022 message versions registered in the local schema registry."""
    return supported_messages()


@mcp.tool()
def validate_message(message_id: str, xml: str) -> dict[str, Any]:
    """Validate XML deterministically against one explicitly selected local ISO 20022 XSD."""
    try:
        return validate_xml_message(message_id, xml)
    except SchemaUnavailableError:
        return {
            "message_id": message_id,
            "valid": False,
            "kind": "schema_unavailable",
            "errors": [],
            "detail": "No local XSD is registered for this exact message version.",
        }
    except ValidatorUnavailableError:
        return {"message_id": message_id, "valid": False, "kind": "validator_unavailable", "errors": []}
    except SchemaConfigurationError:
        return {"message_id": message_id, "valid": False, "kind": "schema_configuration_error", "errors": []}
    except ValueError as exc:
        return {"message_id": message_id, "valid": False, "kind": "invalid_input", "errors": [], "detail": str(exc)}


@mcp.tool()
def check_cbpr_postal_addresses(xml: str, enforce_unstructured_removal: bool = False) -> dict[str, Any]:
    """Check every postal address (PstlAdr) in an ISO 20022 payment message against the CBPR+ rules.

    Reports each address as structured, hybrid or unstructured, with rule IDs, severities,
    XPaths and fix suggestions. Needs no XSD. Unstructured addresses are warnings unless
    enforce_unstructured_removal is true, because Swift deferred their removal (announced
    27 August 2026). Report findings exactly as returned; do not add rules.
    """
    try:
        return check_postal_addresses(xml, enforce_unstructured_removal)
    except ValidatorUnavailableError:
        return {"kind": "validator_unavailable", "compliant": False, "addresses": [], "errors": []}
    except ValueError as exc:
        return {"kind": "invalid_input", "compliant": False, "addresses": [], "errors": [], "detail": str(exc)}


@mcp.tool()
def check_sepa_sct(xml: str, enforce_unstructured_address_removal: bool = False) -> dict[str, Any]:
    """Check a SEPA Credit Transfer (pacs.008 interbank or pain.001 customer initiation) against the EPC 2025 rules.

    Covers euro-only amounts and limits, SLEV charge bearer, SEPA service level, IBAN-only
    accounts (checksum and SEPA country), BICFI-only agents, the Latin character set, name and
    remittance limits, and EPC address rules (including the debtor address required when an agent
    is in a non-EEA SEPA country). Needs no XSD. Report findings exactly as returned; they cover
    EPC usage rules only, not the whole message or the bank's own rules.
    """
    try:
        return check_sepa_sct_service(xml, enforce_unstructured_address_removal)
    except ValidatorUnavailableError:
        return {"kind": "validator_unavailable", "compliant": False, "transactions": [], "errors": []}
    except ValueError as exc:
        return {"kind": "invalid_input", "compliant": False, "transactions": [], "errors": [], "detail": str(exc)}


@mcp.tool()
def validate_iban(iban: str) -> dict[str, Any]:
    """Check an IBAN's format, national length and structure (Swift IBAN Registry) and its mod-97 check digits.

    Also says whether the country is in the SEPA schemes' scope. It does not prove the account exists.
    """
    return validate_iban_service(iban)


@mcp.tool()
def validate_bic(bic: str) -> dict[str, Any]:
    """Check a BIC's ISO 9362 format and describe its parts (institution, country, location, branch, test BIC, SEPA country).

    It does not prove the bank exists; that needs a BIC directory.
    """
    return validate_bic_service(bic)


@mcp.tool()
def search_iso_documents(query: str, message_id: str | None = None, limit: int = 5) -> dict[str, Any]:
    """Search local ISO 20022 reference notes; results include stable source IDs and provenance links."""
    bounded_limit = max(1, min(limit, 10))
    return search_documents(query[:300], message_id, bounded_limit)


@mcp.tool()
def explain_validation_error(message_id: str, error_code: str) -> dict[str, Any]:
    """Find local documentation relevant to a validation error; do not infer missing rules."""
    return search_documents(f"{message_id} {error_code}"[:300], message_id, 5)


if __name__ == "__main__":
    mcp.run()
