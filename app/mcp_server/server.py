from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from typing import Any

from mcp.server.mcpserver import MCPServer

from app.services.cbpr_pacs008 import check_cbpr_pacs008 as check_cbpr_pacs008_service
from app.services.identifiers import validate_bic as validate_bic_service
from app.services.identifiers import validate_iban as validate_iban_service
from app.services.knowledge_search import search_documents
from app.services.message_reader import read_message
from app.services.mt103 import Mt103Error, convert_mt103
from app.services.payment_status import explain_payment_status as explain_payment_status_service
from app.services.payment_summary import summarize_payment as summarize_payment_service
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

try:
    SERVER_VERSION = package_version("iso20022-mcp")
except PackageNotFoundError:  # running from a source tree that was never installed
    SERVER_VERSION = "0.0.0"

mcp = MCPServer(name="ISO 20022 payments (PayDoc AI)", version=SERVER_VERSION)


@mcp.tool()
def explain_payment_status(xml: str, original_xml: str | None = None, scheme: str = "auto") -> dict[str, Any]:
    """Explain why a payment was rejected, returned or what its status is, from a pacs.002, pain.002 or pacs.004.

    Every status and reason code (e.g. RJCT, AC01, AM04, AC04) is explained from the official ISO 20022
    external code sets. SEPA (EPC) and CBPR+ rules are checked: allowed SEPA reject/return reasons,
    originator, original references, returned amount equal to the original, original UETR in CBPR+.
    Pass the original pacs.008 or pain.001 as original_xml to match each status to its payment.
    scheme: auto (default), sepa, cbpr or generic. Report the explanation and findings as returned.
    """
    try:
        return explain_payment_status_service(xml, original_xml, scheme)
    except ValidatorUnavailableError:
        return {"kind": "validator_unavailable", "transactions": [], "errors": []}
    except ValueError as exc:
        return {"kind": "invalid_input", "transactions": [], "errors": [], "detail": str(exc)}


@mcp.tool()
def read_iso20022_message(xml: str) -> dict[str, Any]:
    """Read any ISO 20022 message (pacs, pain, camt such as camt.053 statements, head, admi) and restate it:
    message name and purpose, headers, references (UETR, end-to-end IDs), amounts, parties and agents,
    status and reason codes with their ISO meaning, statement entries, totals and balances, and the
    structure. It does not judge validity; it lists which specialised tool can check the message.
    """
    try:
        return read_message(xml)
    except ValidatorUnavailableError:
        return {"kind": "validator_unavailable", "errors": []}
    except ValueError as exc:
        return {"kind": "invalid_input", "errors": [], "detail": str(exc)}


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
def check_cbpr_pacs008(xml: str, enforce_unstructured_removal: bool = False) -> dict[str, Any]:
    """Check a cross-border pacs.008 against CBPR+ usage rules.

    Covers a single transaction per message, a mandatory lower-case UUID v4 UETR, charge bearer
    DEBT/CRED/SHAR and when charges information is required, ISO 4217 currency decimals (e.g. no
    decimals for JPY), IBAN/BIC validity, the CBPR+ character set, and all postal address rules.
    Needs no XSD. Report findings exactly as returned; bank-specific rules are not applied.
    """
    try:
        return check_cbpr_pacs008_service(xml, enforce_unstructured_removal)
    except ValidatorUnavailableError:
        return {"kind": "validator_unavailable", "compliant": False, "transactions": [], "errors": []}
    except ValueError as exc:
        return {"kind": "invalid_input", "compliant": False, "transactions": [], "errors": [], "detail": str(exc)}


@mcp.tool()
def summarize_payment(xml: str) -> dict[str, Any]:
    """Summarise a pacs.008 or pain.001: who pays whom, amounts and currencies, dates, charges, the chain of banks
    (BICs) and the remittance information. It restates the message; it does not validate it.
    """
    try:
        return summarize_payment_service(xml)
    except ValidatorUnavailableError:
        return {"kind": "validator_unavailable", "transactions": [], "errors": []}
    except ValueError as exc:
        return {"kind": "invalid_input", "transactions": [], "errors": [], "detail": str(exc)}


@mcp.tool()
def convert_mt103_to_pacs008(mt103: str) -> dict[str, Any]:
    """Draft a CBPR+ pacs.008.001.08 from a Swift MT103 and explain what was mapped, defaulted, left
    unstructured, truncated or not carried over, field by field. The draft is then run through
    check_cbpr_pacs008. It is a migration aid based on public bank mapping guides, not a certified
    Swift translation; say so when presenting the result.
    """
    try:
        return convert_mt103(mt103)
    except Mt103Error as exc:
        return {"kind": "invalid_mt103", "xml": None, "report": [], "detail": str(exc)}
    except ValidatorUnavailableError:
        return {"kind": "validator_unavailable", "xml": None, "report": []}
    except ValueError as exc:
        return {"kind": "invalid_input", "xml": None, "report": [], "detail": str(exc)}


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


def main() -> None:
    """Entry point of the `iso20022-mcp` command: serve the tools over stdio for an MCP host."""
    mcp.run()


if __name__ == "__main__":
    main()
