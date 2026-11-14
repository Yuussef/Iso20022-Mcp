"""Deterministic CBPR+ postal address checks for ISO 20022 payment messages.

The XSD alone accepts addresses that CBPR+ rejects: an address made only of
<AdrLine> free text, a structured address without town or country, a hybrid
address with too many lines. This module applies those usage-guideline rules to
every <PstlAdr> in a message and explains each finding.

Rule sources (checked November 2026):
- Swift, "ISO 20022: The removal of unstructured address" FAQ: town and country in
  designated fields for all agents and parties; BIC only remains valid for agents;
  camt.052/053/054/060, camt.025 and admi.024 are out of scope.
- Swift news, 27 August 2026 (updated 21 September 2026): the SR2026 payments
  changes, including the removal of unstructured addresses originally planned for
  14 November 2026, are deferred; a new date is to be announced by December 2026.
- CBPR+ pacs.008.001.08 usage guideline as published on the Goldman Sachs developer
  portal: TwnNm and Ctry mandatory when the address is structured or hybrid, at most
  two AdrLine (70 characters) in a hybrid address, and per-element length limits.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.xml_safety import UntrustedXmlError, parse_untrusted_xml

RULEBOOK = "CBPR+ postal address rules (hybrid option since SR2025, removal of unstructured addresses in SR2026)"

UNSTRUCTURED_REMOVAL = {
    "status": "deferred",
    "originally_planned": "2026-11-14",
    "deferral_announced": "2026-08-27",
    "detail": (
        "Swift deferred the SR2026 payments changes, including the removal of unstructured postal "
        "addresses originally planned for 14 November 2026. A new date is to be announced by December 2026."
    ),
    "source_url": (
        "https://www.swift.com/insights/news/"
        "swift-accepts-community-request-extend-structured-address-migration-iso-20022-payment-messages"
    ),
}

SOURCES = [
    "https://www.swift.com/standards/iso-20022/iso-20022-faqs/iso-20022-removal-unstructured-address",
    UNSTRUCTURED_REMOVAL["source_url"],
    "https://developer.gs.com/docs/services/transaction-banking/cbpr+-pacs008/",
]

# Maximum lengths of structured PostalAddress elements in the CBPR+ pacs.008 usage guideline.
ELEMENT_MAX_LENGTH = {
    "Dept": 70,
    "SubDept": 70,
    "StrtNm": 70,
    "BldgNb": 16,
    "BldgNm": 35,
    "Flr": 70,
    "PstBx": 16,
    "Room": 70,
    "PstCd": 16,
    "TwnNm": 35,
    "TwnLctnNm": 35,
    "DstrctNm": 35,
    "CtrySubDvsn": 35,
}
ADDRESS_LINE_MAX_LENGTH = 70
HYBRID_MAX_ADDRESS_LINES = 2
OUT_OF_SCOPE_MESSAGES = ("admi.024", "camt.025", "camt.052", "camt.053", "camt.054", "camt.060")
MAX_REPORTED_ADDRESSES = 200

COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
POSTCODE_LIKE = re.compile(r"\d{3,}")
MESSAGE_NAMESPACE = re.compile(r"urn:iso:std:iso:20022:tech:xsd:([a-z]{4}\.\d{3}\.\d{3}\.\d{2,3})$")

ROLE_LABELS = {
    "Dbtr": "Debtor",
    "Cdtr": "Creditor",
    "UltmtDbtr": "Ultimate debtor",
    "UltmtCdtr": "Ultimate creditor",
    "InitgPty": "Initiating party",
    "DbtrAgt": "Debtor agent",
    "CdtrAgt": "Creditor agent",
    "InstgAgt": "Instructing agent",
    "InstdAgt": "Instructed agent",
    "IntrmyAgt1": "Intermediary agent 1",
    "IntrmyAgt2": "Intermediary agent 2",
    "IntrmyAgt3": "Intermediary agent 3",
    "PrvsInstgAgt1": "Previous instructing agent 1",
    "PrvsInstgAgt2": "Previous instructing agent 2",
    "PrvsInstgAgt3": "Previous instructing agent 3",
    "InstgRmbrsmntAgt": "Instructing reimbursement agent",
    "InstdRmbrsmntAgt": "Instructed reimbursement agent",
    "ThrdRmbrsmntAgt": "Third reimbursement agent",
}


def _local_name(element: Any) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _children(element: Any) -> list[Any]:
    return [child for child in element if isinstance(child.tag, str)]


def _text(element: Any) -> str:
    return (element.text or "").strip()


def _path(element: Any) -> str:
    parts = []
    node = element
    while node is not None:
        name = _local_name(node)
        parent = node.getparent()
        if parent is not None:
            same_name = [sibling for sibling in _children(parent) if _local_name(sibling) == name]
            if len(same_name) > 1:
                name = f"{name}[{same_name.index(node) + 1}]"
        parts.append(name)
        node = parent
    return "/" + "/".join(reversed(parts))


def _message_id(root: Any) -> str | None:
    for element in root.iter():
        if not isinstance(element.tag, str) or not element.tag.startswith("{"):
            continue
        match = MESSAGE_NAMESPACE.match(element.tag[1:].split("}", 1)[0])
        if match and not match.group(1).startswith("head."):
            return match.group(1)
    return None


def _finding(rule: str, severity: str, message: str, xpath: str, suggestion: str | None = None) -> dict[str, Any]:
    return {"rule": rule, "severity": severity, "message": message, "xpath": xpath, "suggestion": suggestion}


def _check_address(address: Any, enforce_removal: bool) -> dict[str, Any]:
    parent = address.getparent()
    is_agent = parent is not None and _local_name(parent) == "FinInstnId"
    role_element = parent.getparent() if is_agent else parent
    role = _local_name(role_element) if role_element is not None else ""
    bic = None
    if is_agent:
        bic = next((_text(child) for child in _children(parent) if _local_name(child) == "BICFI"), None)

    children = _children(address)
    lines = [child for child in children if _local_name(child) == "AdrLine"]
    structured = {_local_name(child): child for child in children if _local_name(child) not in {"AdrLine", "AdrTp"}}
    if lines and not structured:
        address_format = "unstructured"
    elif lines:
        address_format = "hybrid"
    else:
        address_format = "structured"

    xpath = _path(address)
    findings: list[dict[str, Any]] = []

    if address_format == "unstructured":
        if bic:
            suggestion = f"Remove the postal address: the BIC {bic} alone identifies this agent."
        else:
            suggestion = (
                "Put the town in <TwnNm> and the ISO country code in <Ctry>, then keep at most two <AdrLine> "
                "for the rest of the address (hybrid), or structure it fully."
            )
        findings.append(
            _finding(
                "CBPR_ADDR_UNSTRUCTURED",
                "error" if enforce_removal else "warning",
                "Unstructured address (only <AdrLine>). CBPR+ removes this option in SR2026; "
                "Swift deferred the original 14 November 2026 date and will announce a new one.",
                xpath,
                suggestion,
            )
        )
    else:
        if "TwnNm" not in structured or not _text(structured["TwnNm"]):
            findings.append(
                _finding(
                    "CBPR_ADDR_TOWN_MISSING",
                    "error",
                    f"A {address_format} address must contain <TwnNm>.",
                    xpath,
                    "Add the town name in <TwnNm>.",
                )
            )
        if "Ctry" not in structured or not _text(structured["Ctry"]):
            findings.append(
                _finding(
                    "CBPR_ADDR_COUNTRY_MISSING",
                    "error",
                    f"A {address_format} address must contain <Ctry>.",
                    xpath,
                    "Add the ISO 3166 alpha-2 country code in <Ctry>.",
                )
            )

    if address_format == "hybrid" and len(lines) > HYBRID_MAX_ADDRESS_LINES:
        findings.append(
            _finding(
                "CBPR_ADDR_TOO_MANY_LINES",
                "error",
                f"A hybrid address allows at most {HYBRID_MAX_ADDRESS_LINES} <AdrLine>; found {len(lines)}.",
                xpath,
                "Move details such as street, building or post code into their structured elements.",
            )
        )

    country = structured.get("Ctry")
    if country is not None and _text(country) and not COUNTRY_CODE.fullmatch(_text(country)):
        findings.append(
            _finding(
                "CBPR_ADDR_COUNTRY_FORMAT",
                "error",
                f"<Ctry> must be a two-letter upper-case ISO 3166 code; found {_text(country)[:40]!r}.",
                _path(country),
            )
        )

    for name, element in structured.items():
        limit = ELEMENT_MAX_LENGTH.get(name)
        if limit and len(_text(element)) > limit:
            findings.append(
                _finding(
                    "CBPR_ADDR_TOO_LONG",
                    "error",
                    f"<{name}> is limited to {limit} characters; found {len(_text(element))}.",
                    _path(element),
                )
            )
    for line in lines:
        if len(_text(line)) > ADDRESS_LINE_MAX_LENGTH:
            findings.append(
                _finding(
                    "CBPR_ADDR_TOO_LONG",
                    "error",
                    f"<AdrLine> is limited to {ADDRESS_LINE_MAX_LENGTH} characters; found {len(_text(line))}.",
                    _path(line),
                )
            )

    town = _text(structured["TwnNm"]) if "TwnNm" in structured else ""
    if town and POSTCODE_LIKE.search(town):
        findings.append(
            _finding(
                "CBPR_ADDR_POSTCODE_IN_TOWN",
                "warning",
                f"<TwnNm> {town!r} looks like it contains a post code, a common mapping error that weakens screening.",
                _path(structured["TwnNm"]),
                "Move the post code to <PstCd>.",
            )
        )
    if address_format == "hybrid" and town:
        town_pattern = re.compile(rf"(?<!\w){re.escape(town)}(?!\w)", re.IGNORECASE)
        for line in lines:
            if town_pattern.search(_text(line)):
                findings.append(
                    _finding(
                        "CBPR_ADDR_DUPLICATED_IN_LINE",
                        "warning",
                        f"<AdrLine> repeats the town {town!r} already given in <TwnNm>.",
                        _path(line),
                        "Keep each piece of address data in one place only.",
                    )
                )

    if bic:
        findings.append(
            _finding(
                "CBPR_ADDR_AGENT_HAS_BIC",
                "info",
                f"This agent is identified by BIC {bic}; for agents the BIC alone is a valid option.",
                xpath,
            )
        )

    return {
        "role": role,
        "role_label": ROLE_LABELS.get(role, role),
        "xpath": xpath,
        "format": address_format,
        "agent_bic": bic,
        "findings": findings,
    }


def check_postal_addresses(xml: str, enforce_unstructured_removal: bool = False) -> dict[str, Any]:
    """Check every <PstlAdr> in an ISO 20022 message against the CBPR+ address rules.

    Unstructured addresses are warnings by default, because Swift deferred their
    removal; pass enforce_unstructured_removal=True to treat them as errors.
    Raises ValueError when the input exceeds the size limit.
    """
    removal = {**UNSTRUCTURED_REMOVAL, "enforced": enforce_unstructured_removal}
    base = {"rulebook": RULEBOOK, "unstructured_removal": removal, "sources": SOURCES}
    try:
        root = parse_untrusted_xml(xml)
    except UntrustedXmlError as exc:
        return {
            **base,
            "kind": exc.kind,
            "message_id": None,
            "in_scope": False,
            "compliant": False,
            "summary": None,
            "addresses": [],
            "addresses_truncated": False,
            "errors": [exc.as_error()],
        }

    message_id = _message_id(root)
    in_scope = not (message_id and message_id.startswith(OUT_OF_SCOPE_MESSAGES))
    addresses = []
    if in_scope:
        found = [element for element in root.iter() if isinstance(element.tag, str) and _local_name(element) == "PstlAdr"]
        addresses = [_check_address(address, enforce_unstructured_removal) for address in found[:MAX_REPORTED_ADDRESSES]]
    else:
        found = []

    findings = [finding for address in addresses for finding in address["findings"]]
    errors = sum(1 for finding in findings if finding["severity"] == "error")
    return {
        **base,
        "kind": "postal_address_check",
        "message_id": message_id,
        "in_scope": in_scope,
        "compliant": errors == 0,
        "summary": {
            "addresses": len(addresses),
            "structured": sum(1 for address in addresses if address["format"] == "structured"),
            "hybrid": sum(1 for address in addresses if address["format"] == "hybrid"),
            "unstructured": sum(1 for address in addresses if address["format"] == "unstructured"),
            "errors": errors,
            "warnings": sum(1 for finding in findings if finding["severity"] == "warning"),
        },
        "addresses": addresses,
        "addresses_truncated": len(found) > len(addresses),
        "errors": [],
    }
