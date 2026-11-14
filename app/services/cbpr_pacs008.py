"""Deterministic CBPR+ checks for pacs.008 customer credit transfers.

Rule sources (checked November 2026):
- CBPR+ pacs.008.001.08 usage guideline as published on the Goldman Sachs developer
  portal: one transaction per message, mandatory UETR (UUID v4), charge bearer DEBT,
  CRED or SHAR, when charges information is required, and the CBPR+ character set.
- Clearstream "CBPR+ ISO 20022 Swift User Guide" (October 2026): UETR marked mandatory
  in pacs.008.
- ISO 20022 ActiveCurrencyAndAmount: the number of fractional digits must comply with
  ISO 4217 (List One, published by SIX, in data/reference/iso4217.json).
Postal addresses reuse check_postal_addresses; IBANs and BICs reuse validate_iban and
validate_bic. Bank-specific rules (for example a settlement method a bank imposes) are
not applied.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.identifiers import validate_bic, validate_iban
from app.services.postal_address import check_postal_addresses
from app.services.xml_safety import UntrustedXmlError, parse_untrusted_xml
from app.services.xml_tools import child, children, descendant, find_all, finding, local_name, message_id, path, text

RULEBOOK = "CBPR+ pacs.008.001.08 usage rules (UETR, single transaction, charges, currency decimals, character set, addresses)"
EXPECTED_VERSION = "pacs.008.001.08"
REFERENCE_DIR = Path(__file__).resolve().parents[2] / "data" / "reference"

SOURCES = [
    "https://developer.gs.com/docs/services/transaction-banking/cbpr+-pacs008/",
    "https://www.clearstream.com/caas/v1/media/4814538/data/ca917a93e9390d399c6c34ebe14032d0/cbpr-ug.pdf",
    "https://www.six-group.com/en/products-services/financial-information/market-reference-data/data-standards.html",
    "https://www.swift.com/standards/iso-20022/iso-20022-faqs/iso-20022-removal-unstructured-address",
]

UETR_PATTERN = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$")
CBPR_CHARGE_BEARERS = {"DEBT", "CRED", "SHAR"}
# CBPR+ extended character set for text fields, as published in the usage guideline.
CBPR_TEXT = re.compile(r"^[0-9a-zA-Z/\-?:().,'+ !#$%&*=^_`{|}~\";<>@\[\\\]]*$")
TEXT_FIELDS = {"Nm", "AdrLine", "StrtNm", "TwnNm", "Ustrd", "InstrInf", "AddtlInf", "Ref"}
MAX_CHARACTER_FINDINGS = 20
MAX_REPORTED_TRANSACTIONS = 50


@lru_cache(maxsize=1)
def iso4217() -> dict[str, Any]:
    return json.loads((REFERENCE_DIR / "iso4217.json").read_text(encoding="utf-8"))


def _amount(element: Any | None) -> tuple[str, Decimal] | None:
    if element is None:
        return None
    try:
        return element.get("Ccy", ""), Decimal(text(element))
    except InvalidOperation:
        return None


def _currency_findings(element: Any | None) -> list[dict[str, Any]]:
    if element is None:
        return []
    xpath = path(element)
    currency = element.get("Ccy", "")
    entry = iso4217()["currencies"].get(currency)
    if entry is None:
        return [finding("CBPR_CURRENCY_UNKNOWN", "error", f"{currency or 'No currency'} is not an active ISO 4217 currency code.", xpath)]
    parsed = _amount(element)
    if parsed is None:
        return [finding("CBPR_AMOUNT_FORMAT", "error", f"{text(element)!r} is not an amount.", xpath)]
    exponent = parsed[1].as_tuple().exponent
    decimals = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    minor = entry["minor_units"]
    if minor is not None and decimals > minor:
        return [
            finding(
                "CBPR_CURRENCY_DECIMALS",
                "error",
                f"{currency} ({entry['name']}) has {minor} decimal{'s' if minor != 1 else ''} in ISO 4217; this amount has {decimals}.",
                xpath,
                f"Round the amount to {minor} decimal{'s' if minor != 1 else ''}.",
            )
        ]
    if parsed[1] <= 0:
        return [finding("CBPR_AMOUNT_NOT_POSITIVE", "error", "The amount must be greater than zero.", xpath)]
    return []


def _charges_findings(transaction: Any) -> list[dict[str, Any]]:
    bearer_element = child(transaction, "ChrgBr")
    if bearer_element is None:
        return [finding("CBPR_CHARGE_BEARER", "error", "Charge Bearer is mandatory.", path(transaction), "Use DEBT, CRED or SHAR.")]
    bearer = text(bearer_element)
    if bearer not in CBPR_CHARGE_BEARERS:
        suggestion = "SLEV is a SEPA code; cross-border CBPR+ payments use DEBT, CRED or SHAR." if bearer == "SLEV" else None
        return [
            finding(
                "CBPR_CHARGE_BEARER",
                "error",
                f"Charge Bearer must be DEBT, CRED or SHAR; found {bearer!r}.",
                path(bearer_element),
                suggestion,
            )
        ]

    has_charges = child(transaction, "ChrgsInf") is not None
    settled = _amount(child(transaction, "IntrBkSttlmAmt"))
    instructed = _amount(child(transaction, "InstdAmt"))
    same_currency = settled is not None and instructed is not None and settled[0] == instructed[0]
    deducted = same_currency and settled[1] < instructed[1]
    prepaid = same_currency and settled[1] > instructed[1]

    if has_charges:
        return []
    if bearer == "CRED":
        return [
            finding(
                "CBPR_CHARGES_INFO_REQUIRED", "error", "Charges Information is mandatory when the charge bearer is CRED.", path(transaction)
            )
        ]
    if bearer == "SHAR" and deducted:
        return [
            finding(
                "CBPR_CHARGES_INFO_REQUIRED",
                "error",
                "The settlement amount is lower than the instructed amount, so charges were deducted; "
                "with SHAR, Charges Information is then mandatory.",
                path(transaction),
            )
        ]
    if bearer == "DEBT" and prepaid:
        return [
            finding(
                "CBPR_CHARGES_INFO_REQUIRED",
                "error",
                "The settlement amount is higher than the instructed amount (prepaid charges); "
                "with DEBT, Charges Information is then mandatory.",
                path(transaction),
            )
        ]
    return []


def _identifier_findings(transaction: Any) -> list[dict[str, Any]]:
    findings = []
    for element in find_all(transaction, "IBAN"):
        result = validate_iban(text(element))
        findings += [finding(f"CBPR_{error['code']}", "error", f"IBAN: {error['message']}", path(element)) for error in result["errors"]]
    for name in ("BICFI", "AnyBIC"):
        for element in find_all(transaction, name):
            result = validate_bic(text(element))
            findings += [
                finding(f"CBPR_{error['code']}", "error", f"{name}: {error['message']}", path(element)) for error in result["errors"]
            ]
    return findings


def _character_findings(root: Any) -> list[dict[str, Any]]:
    findings = []
    for element in root.iter():
        if local_name(element) in TEXT_FIELDS and text(element) and not CBPR_TEXT.fullmatch(text(element)):
            findings.append(
                finding(
                    "CBPR_CHARACTER_SET",
                    "warning",
                    f"<{local_name(element)}> contains characters outside the CBPR+ character set.",
                    path(element),
                    "Transliterate accented or non-Latin characters.",
                )
            )
            if len(findings) >= MAX_CHARACTER_FINDINGS:
                break
    return findings


def _check_transaction(transaction: Any) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    uetr = descendant(transaction, "PmtId", "UETR")
    if uetr is None or not text(uetr):
        findings.append(
            finding(
                "CBPR_UETR_MISSING",
                "error",
                "The UETR is mandatory in a CBPR+ pacs.008; it tracks the payment end to end.",
                path(transaction),
                "Add a lower-case UUID version 4 in PmtId/UETR.",
            )
        )
    elif not UETR_PATTERN.fullmatch(text(uetr)):
        findings.append(
            finding(
                "CBPR_UETR_FORMAT",
                "error",
                f"{text(uetr)[:40]!r} is not a lower-case UUID version 4 (RFC 4122).",
                path(uetr),
                "Generate a new UUID v4, for example with uuid.uuid4().",
            )
        )
    if child(transaction, "IntrBkSttlmAmt") is None:
        findings.append(finding("CBPR_AMOUNT_MISSING", "error", "Interbank Settlement Amount is mandatory.", path(transaction)))
    for name in ("IntrBkSttlmAmt", "InstdAmt"):
        findings += _currency_findings(child(transaction, name))
    for charges in (item for item in children(transaction) if local_name(item) == "ChrgsInf"):
        findings += _currency_findings(child(charges, "Amt"))
    findings += _charges_findings(transaction)
    findings += _identifier_findings(transaction)
    return {
        "xpath": path(transaction),
        "uetr": text(uetr) or None,
        "end_to_end_id": text(descendant(transaction, "PmtId", "EndToEndId")) or None,
        "findings": findings,
    }


def check_cbpr_pacs008(xml: str, enforce_unstructured_removal: bool = False) -> dict[str, Any]:
    """Check a pacs.008 against CBPR+ usage rules, including IBAN/BIC validity and postal addresses.

    Raises ValueError when the input exceeds the size limit.
    """
    base = {"rulebook": RULEBOOK, "sources": SOURCES}
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
            "message_findings": [],
            "transactions": [],
            "postal_addresses": None,
            "errors": [exc.as_error()],
        }

    detected = message_id(root)
    document = next((element for element in root.iter() if local_name(element) == "FIToFICstmrCdtTrf"), None)
    message_findings: list[dict[str, Any]] = []
    transactions: list[dict[str, Any]] = []
    postal = None
    if document is not None:
        if detected and detected != EXPECTED_VERSION:
            message_findings.append(
                finding(
                    "CBPR_MESSAGE_VERSION",
                    "warning",
                    f"CBPR+ uses {EXPECTED_VERSION}; this message is {detected}. Rules were applied anyway.",
                    path(root),
                )
            )
        header = child(document, "GrpHdr")
        number = text(descendant(header, "NbOfTxs")) if header is not None else ""
        items = [item for item in children(document) if local_name(item) == "CdtTrfTxInf"]
        if number != "1" or len(items) != 1:
            message_findings.append(
                finding(
                    "CBPR_SINGLE_TRANSACTION",
                    "error",
                    "A CBPR+ pacs.008 carries exactly one transaction (NbOfTxs = 1); "
                    f"found NbOfTxs {number or 'missing'} and {len(items)} transaction(s).",
                    path(header if header is not None else document),
                    "Send one pacs.008 per payment.",
                )
            )
        message_findings += _character_findings(document)
        transactions = [_check_transaction(item) for item in items[:MAX_REPORTED_TRANSACTIONS]]
        postal = check_postal_addresses(xml, enforce_unstructured_removal)

    findings = message_findings + [item for transaction in transactions for item in transaction["findings"]]
    address_findings = [item for address in (postal or {}).get("addresses", []) for item in address["findings"]]
    everything = findings + address_findings
    errors = sum(1 for item in everything if item["severity"] == "error")
    return {
        **base,
        "kind": "cbpr_pacs008_check",
        "message_id": detected,
        "in_scope": document is not None,
        "compliant": document is not None and errors == 0,
        "summary": {
            "transactions": len(transactions),
            "errors": errors,
            "warnings": sum(1 for item in everything if item["severity"] == "warning"),
            "address_errors": sum(1 for item in address_findings if item["severity"] == "error"),
        },
        "message_findings": message_findings,
        "transactions": transactions,
        "postal_addresses": postal,
        "errors": [],
    }
