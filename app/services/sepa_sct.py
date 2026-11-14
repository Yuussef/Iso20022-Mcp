"""Deterministic SEPA Credit Transfer (SCT) checks for pacs.008 and pain.001 messages.

Rules come from the EPC 2025 SCT implementation guidelines (effective 5 October 2025):
- EPC115-06 SCT Inter-PSP IG 2025 v1.0, pacs.008.001.08
- EPC132-08 SCT Customer-to-PSP IG 2025 v1.0, pain.001.001.09
Address rules come from EPC153-22 v2.2 (30 September 2026), which deferred the end
of unstructured addresses without a new date. SEPA countries come from EPC409-09 v8.0.

The XSD does not enforce any of these usage rules. The check needs no schema file.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.identifiers import sepa_countries, validate_bic, validate_iban
from app.services.postal_address import ELEMENT_MAX_LENGTH
from app.services.xml_safety import UntrustedXmlError, parse_untrusted_xml
from app.services.xml_tools import child, children, descendant, finding, local_name, message_id, path, text

RULEBOOK = "EPC SEPA Credit Transfer 2025 implementation guidelines (pacs.008.001.08 Inter-PSP, pain.001.001.09 Customer-to-PSP)"
EXPECTED_VERSIONS = {"pacs.008": "pacs.008.001.08", "pain.001": "pain.001.001.09"}

UNSTRUCTURED_ADDRESS_END = {
    "status": "deferred",
    "originally_planned": "2026-11-15",
    "deferral_issued": "2026-09-30",
    "detail": (
        "In September 2026 the EPC delayed the November 2026 end date of the unstructured address format under "
        "all five EPC payment schemes; a new end date will be set later (EPC153-22 v2.2)."
    ),
    "source_url": (
        "https://www.europeanpaymentscouncil.eu/sites/default/files/kb/file/2026-09/"
        "EPC153-22%20v2.2%20EPC%20guidance%20document%20-%20Provision%20of%20Addresses%20under%20the%20EPC%20Payment%20Schemes.pdf"
    ),
}

SOURCES = [
    "https://www.europeanpaymentscouncil.eu/sites/default/files/kb/file/2025-10/EPC115-06%20SCT%20Inter-PSP%20IG%202025%20V1.0.pdf",
    "https://www.europeanpaymentscouncil.eu/sites/default/files/kb/file/2025-10/EPC132-08%20SCT%20C2PSP%20IG%202025%20V1.0.pdf",
    UNSTRUCTURED_ADDRESS_END["source_url"],
    "https://www.europeanpaymentscouncil.eu/document-library/other/epc-list-sepa-scheme-countries",
]

# EPC IG section 1.4: the Latin character set every SEPA PSP must support.
LATIN = re.compile(r"^[A-Za-z0-9/\-?:().,'+ ]*$")
MIN_AMOUNT = Decimal("0.01")
MAX_AMOUNT = Decimal("999999999.99")
NAME_MAX_LENGTH = 70
UNSTRUCTURED_REMITTANCE_MAX = 140
STRUCTURED_REMITTANCE_MAX = 140
MAX_ADDRESS_LINES = 2
MAX_REPORTED_TRANSACTIONS = 200
PARTIES = ("UltmtDbtr", "Dbtr", "Cdtr", "UltmtCdtr")


def _amount_findings(amount_element: Any | None, label: str) -> list[dict[str, Any]]:
    if amount_element is None:
        return [finding("SEPA_AMOUNT_MISSING", "error", f"The {label} is missing.", "")]
    xpath = path(amount_element)
    findings = []
    currency = amount_element.get("Ccy", "")
    if currency != "EUR":
        findings.append(
            finding("SEPA_CURRENCY", "error", f"SEPA Credit Transfers are in euro only; found {currency or 'no currency'}.", xpath)
        )
    try:
        value = Decimal(text(amount_element))
    except InvalidOperation:
        return findings + [finding("SEPA_AMOUNT_FORMAT", "error", f"{text(amount_element)!r} is not an amount.", xpath)]
    if value < MIN_AMOUNT or value > MAX_AMOUNT:
        findings.append(finding("SEPA_AMOUNT_RANGE", "error", f"The amount must be between 0.01 and 999999999.99; found {value}.", xpath))
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        findings.append(finding("SEPA_AMOUNT_DECIMALS", "error", "Euro amounts have at most two decimals.", xpath))
    return findings


def _identifier_findings(element: Any | None, label: str) -> list[dict[str, Any]]:
    value = text(element)
    if element is None or not value:
        return []
    problems = []
    if not LATIN.fullmatch(value):
        problems.append("uses characters outside the SEPA Latin character set")
    if value.startswith("/") or value.endswith("/"):
        problems.append("starts or ends with '/'")
    if "//" in value:
        problems.append("contains '//'")
    if not problems:
        return []
    return [finding("SEPA_REFERENCE_FORMAT", "error", f"{label} {value[:40]!r} " + " and ".join(problems) + ".", path(element))]


def _text_charset_findings(element: Any | None, label: str) -> list[dict[str, Any]]:
    value = text(element)
    if element is None or not value or LATIN.fullmatch(value):
        return []
    return [
        finding(
            "SEPA_CHARACTER_SET",
            "warning",
            f"{label} contains characters outside the SEPA Latin character set; PSPs only have to support those "
            "unless a bilateral or multilateral agreement says otherwise.",
            path(element),
            "Transliterate accented or non-Latin characters (for example é to e).",
        )
    ]


def _account_findings(account: Any | None, role: str, label: str) -> list[dict[str, Any]]:
    if account is None:
        return [finding("SEPA_ACCOUNT_MISSING", "error", f"The {label} account is mandatory.", "", f"Add {role}Acct/Id/IBAN.")]
    iban_element = descendant(account, "Id", "IBAN")
    if iban_element is None:
        return [finding("SEPA_ACCOUNT_NOT_IBAN", "error", f"Only an IBAN is allowed for the {label} account.", path(account))]
    result = validate_iban(text(iban_element))
    findings = [
        finding(f"SEPA_{error['code']}", "error", f"{label.capitalize()} IBAN: {error['message']}", path(iban_element))
        for error in result["errors"]
    ]
    if result["valid"] and not result["sepa"]:
        findings.append(
            finding(
                "SEPA_IBAN_OUTSIDE_SEPA",
                "error",
                f"{label.capitalize()} IBAN country {result['country']} is not in the SEPA schemes' geographical scope (EPC409-09).",
                path(iban_element),
            )
        )
    return findings


def _agent(container: Any, role: str) -> tuple[Any | None, str | None]:
    institution = descendant(container, role, "FinInstnId")
    bic = text(child(institution, "BICFI")) if institution is not None else ""
    return institution, bic or None


def _agent_findings(institution: Any | None, label: str) -> list[dict[str, Any]]:
    if institution is None:
        return []
    findings = []
    others = [local_name(item) for item in children(institution) if local_name(item) != "BICFI"]
    if others:
        findings.append(
            finding(
                "SEPA_AGENT_NOT_BIC",
                "error",
                f"Only 'BICFI' is allowed to identify the {label}; found {', '.join(others)}.",
                path(institution),
            )
        )
    bic_element = child(institution, "BICFI")
    if bic_element is not None:
        result = validate_bic(text(bic_element))
        findings += [
            finding(f"SEPA_{error['code']}", "error", f"{label.capitalize()}: {error['message']}", path(bic_element))
            for error in result["errors"]
        ]
        if result["country"] and not result["sepa"]:
            findings.append(
                finding(
                    "SEPA_BIC_OUTSIDE_SEPA",
                    "warning",
                    f"{label.capitalize()} BIC country {result['country']} is not in the SEPA schemes' geographical scope.",
                    path(bic_element),
                )
            )
    return findings


def _address_findings(address: Any, label: str, enforce_removal: bool, country_required: bool) -> list[dict[str, Any]]:
    xpath = path(address)
    items = children(address)
    lines = [item for item in items if local_name(item) == "AdrLine"]
    structured = {local_name(item): item for item in items if local_name(item) not in {"AdrLine", "AdrTp"}}
    findings: list[dict[str, Any]] = []

    if lines and set(structured) <= {"Ctry"}:
        findings.append(
            finding(
                "SEPA_ADDRESS_UNSTRUCTURED",
                "error" if enforce_removal else "warning",
                f"The {label} address is unstructured. The EPC deferred the end of this format (originally November 2026) "
                "and will set a new date.",
                xpath,
                "Use a structured address, or a hybrid one: <TwnNm> and <Ctry> plus at most two <AdrLine>.",
            )
        )
        if country_required and "Ctry" not in structured:
            findings.append(
                finding(
                    "SEPA_ADDRESS_COUNTRY_REQUIRED",
                    "error",
                    f"<Ctry> is mandatory in the {label} address because the debtor agent or creditor agent is in a non-EEA SEPA country.",
                    xpath,
                )
            )
    else:
        for name, rule in (("TwnNm", "SEPA_ADDRESS_TOWN_MISSING"), ("Ctry", "SEPA_ADDRESS_COUNTRY_MISSING")):
            if not text(structured.get(name)):
                kind = "hybrid" if lines else "structured"
                findings.append(finding(rule, "error", f"A {kind} {label} address must contain <{name}>.", xpath))
    if len(lines) > MAX_ADDRESS_LINES:
        findings.append(
            finding(
                "SEPA_ADDRESS_TOO_MANY_LINES", "error", f"At most {MAX_ADDRESS_LINES} <AdrLine> are allowed; found {len(lines)}.", xpath
            )
        )
    for name, element in structured.items():
        limit = ELEMENT_MAX_LENGTH.get(name)
        if limit and len(text(element)) > limit:
            findings.append(finding("SEPA_ADDRESS_TOO_LONG", "error", f"<{name}> is limited to {limit} characters.", path(element)))
    for line in lines:
        if len(text(line)) > 70:
            findings.append(finding("SEPA_ADDRESS_TOO_LONG", "error", "<AdrLine> is limited to 70 characters.", path(line)))
        findings += _text_charset_findings(line, f"The {label} address line")
    return findings


def _remittance_findings(remittance: Any | None) -> list[dict[str, Any]]:
    if remittance is None:
        return []
    xpath = path(remittance)
    unstructured = [item for item in children(remittance) if local_name(item) == "Ustrd"]
    structured = [item for item in children(remittance) if local_name(item) == "Strd"]
    findings = []
    if unstructured and structured:
        findings.append(
            finding(
                "SEPA_REMITTANCE_BOTH",
                "error",
                "Either 'Structured' or 'Unstructured' remittance information may be present, not both.",
                xpath,
            )
        )
    if len(unstructured) > 1:
        findings.append(finding("SEPA_REMITTANCE_REPEATED", "error", "Only one occurrence of 'Unstructured' is allowed.", xpath))
    if len(structured) > 1:
        findings.append(finding("SEPA_REMITTANCE_REPEATED", "error", "Only one occurrence of 'Structured' is allowed.", xpath))
    for item in unstructured:
        if len(text(item)) > UNSTRUCTURED_REMITTANCE_MAX:
            findings.append(
                finding(
                    "SEPA_REMITTANCE_TOO_LONG",
                    "error",
                    f"'Unstructured' is limited to {UNSTRUCTURED_REMITTANCE_MAX} characters.",
                    path(item),
                )
            )
        findings += _text_charset_findings(item, "The remittance information")
    for item in structured:
        from lxml import etree

        inner = (item.text or "") + "".join(etree.tostring(node, encoding="unicode", with_tail=True) for node in item)
        inner = re.sub(r'\sxmlns(:\w+)?="[^"]*"', "", inner)
        inner = re.sub(r"<(/?)\w+:", r"<\1", inner)
        if len(inner.strip()) > STRUCTURED_REMITTANCE_MAX:
            findings.append(
                finding(
                    "SEPA_REMITTANCE_TOO_LONG",
                    "error",
                    f"The tags and data inside 'Structured' must not exceed {STRUCTURED_REMITTANCE_MAX} characters.",
                    path(item),
                )
            )
    return findings


def _service_level_findings(transaction: Any, block: Any) -> list[dict[str, Any]]:
    for container in (transaction, block):
        code = descendant(container, "PmtTpInf", "SvcLvl", "Cd")
        if code is not None:
            if text(code) != "SEPA":
                return [finding("SEPA_SERVICE_LEVEL", "error", f"Only service level 'SEPA' is allowed; found {text(code)!r}.", path(code))]
            return []
    return [
        finding(
            "SEPA_SERVICE_LEVEL_MISSING",
            "error",
            "Payment Type Information with service level 'SEPA' must be present at transaction or group level.",
            path(transaction),
            "Add <PmtTpInf><SvcLvl><Cd>SEPA</Cd></SvcLvl></PmtTpInf>.",
        )
    ]


def _charge_bearer_findings(transaction: Any, block: Any, interbank: bool) -> list[dict[str, Any]]:
    element = child(transaction, "ChrgBr")
    if element is None and not interbank:
        element = child(block, "ChrgBr")
    if element is None:
        if interbank:
            return [finding("SEPA_CHARGE_BEARER", "error", "Charge Bearer is mandatory and must be 'SLEV'.", path(transaction))]
        return [
            finding(
                "SEPA_CHARGE_BEARER_RECOMMENDED",
                "info",
                "Charge Bearer is optional in pain.001 but recommended at payment information level, with 'SLEV'.",
                path(transaction),
            )
        ]
    if text(element) != "SLEV":
        return [finding("SEPA_CHARGE_BEARER", "error", f"Only 'SLEV' is allowed as Charge Bearer; found {text(element)!r}.", path(element))]
    return []


def _check_transaction(transaction: Any, block: Any, interbank: bool, enforce_removal: bool) -> dict[str, Any]:
    party_scope = transaction if interbank else block
    findings: list[dict[str, Any]] = []

    for name, label in (
        ("InstrId", "Instruction Identification"),
        ("EndToEndId", "End To End Identification"),
        ("TxId", "Transaction Identification"),
    ):
        findings += _identifier_findings(descendant(transaction, "PmtId", name), label)
    findings += _service_level_findings(transaction, block)
    if interbank:
        findings += _amount_findings(child(transaction, "IntrBkSttlmAmt"), "interbank settlement amount")
    else:
        findings += _amount_findings(descendant(transaction, "Amt", "InstdAmt"), "instructed amount")
    findings += _charge_bearer_findings(transaction, block, interbank)

    debtor_agent, debtor_bic = _agent(party_scope, "DbtrAgt")
    creditor_agent, creditor_bic = _agent(transaction, "CdtrAgt")
    findings += _agent_findings(debtor_agent, "debtor agent")
    findings += _agent_findings(creditor_agent, "creditor agent")
    non_eea = set(sepa_countries()["non_eea_bic_country_codes"])
    non_eea_agent = any(bic and len(bic) >= 6 and bic[4:6] in non_eea for bic in (debtor_bic, creditor_bic))

    findings += _account_findings(child(party_scope, "DbtrAcct"), "Dbtr", "debtor")
    findings += _account_findings(child(transaction, "CdtrAcct"), "Cdtr", "creditor")

    for role in PARTIES:
        scope = party_scope if role in {"UltmtDbtr", "Dbtr"} else transaction
        party = child(scope, role)
        label = {"UltmtDbtr": "ultimate debtor", "Dbtr": "debtor", "Cdtr": "creditor", "UltmtCdtr": "ultimate creditor"}[role]
        if party is None:
            if role in {"Dbtr", "Cdtr"}:
                findings.append(finding("SEPA_PARTY_MISSING", "error", f"The {label} is mandatory.", path(scope)))
            continue
        name = child(party, "Nm")
        if role in {"Dbtr", "Cdtr"} and not text(name):
            findings.append(finding("SEPA_NAME_MISSING", "error", f"The {label} name is mandatory.", path(party)))
        if name is not None and len(text(name)) > NAME_MAX_LENGTH:
            findings.append(
                finding("SEPA_NAME_TOO_LONG", "error", f"The {label} name is limited to {NAME_MAX_LENGTH} characters.", path(name))
            )
        findings += _text_charset_findings(name, f"The {label} name")
        address = child(party, "PstlAdr")
        if address is not None:
            findings += _address_findings(address, label, enforce_removal, country_required=role == "Dbtr" and non_eea_agent)
        elif role == "Dbtr" and non_eea_agent:
            findings.append(
                finding(
                    "SEPA_DEBTOR_ADDRESS_REQUIRED",
                    "error",
                    "The debtor address (AT-P005) is mandatory because the debtor agent or creditor agent is in a non-EEA SEPA country.",
                    path(party),
                )
            )

    findings += _remittance_findings(child(transaction, "RmtInf"))
    return {
        "xpath": path(transaction),
        "end_to_end_id": text(descendant(transaction, "PmtId", "EndToEndId")) or None,
        "non_eea_agent": non_eea_agent,
        "findings": findings,
    }


def check_sepa_sct(xml: str, enforce_unstructured_address_removal: bool = False) -> dict[str, Any]:
    """Check a pacs.008 or pain.001 message against the EPC SEPA Credit Transfer usage rules.

    Raises ValueError when the input exceeds the size limit.
    """
    base = {
        "rulebook": RULEBOOK,
        "unstructured_address_end": {**UNSTRUCTURED_ADDRESS_END, "enforced": enforce_unstructured_address_removal},
        "sources": SOURCES,
    }
    try:
        root = parse_untrusted_xml(xml)
    except UntrustedXmlError as exc:
        return {
            **base,
            "kind": exc.kind,
            "message_id": None,
            "message_type": None,
            "in_scope": False,
            "compliant": False,
            "summary": None,
            "message_findings": [],
            "transactions": [],
            "transactions_truncated": False,
            "errors": [exc.as_error()],
        }

    detected = message_id(root)
    interbank_root = next(iter(element for element in root.iter() if local_name(element) == "FIToFICstmrCdtTrf"), None)
    initiation_root = next(iter(element for element in root.iter() if local_name(element) == "CstmrCdtTrfInitn"), None)
    document = interbank_root if interbank_root is not None else initiation_root
    message_type = "pacs.008" if interbank_root is not None else "pain.001" if initiation_root is not None else None

    message_findings: list[dict[str, Any]] = []
    blocks: list[tuple[Any, Any]] = []
    if document is not None:
        header = child(document, "GrpHdr")
        message_findings += _identifier_findings(child(header, "MsgId") if header is not None else None, "Message Identification")
        expected = EXPECTED_VERSIONS[message_type]
        if detected and detected != expected:
            message_findings.append(
                finding(
                    "SEPA_MESSAGE_VERSION",
                    "warning",
                    f"The EPC 2025 guidelines use {expected}; this message is {detected}. Rules were applied anyway.",
                    path(root),
                )
            )
        if message_type == "pacs.008":
            if header is not None and child(header, "TtlIntrBkSttlmAmt") is None:
                message_findings.append(
                    finding(
                        "SEPA_TOTAL_AMOUNT_MISSING",
                        "error",
                        "Total Interbank Settlement Amount is mandatory in the group header.",
                        path(header),
                    )
                )
            blocks = [(transaction, header) for transaction in children(document) if local_name(transaction) == "CdtTrfTxInf"]
        else:
            for payment_information in (item for item in children(document) if local_name(item) == "PmtInf"):
                message_findings += _identifier_findings(child(payment_information, "PmtInfId"), "Payment Information Identification")
                blocks += [
                    (transaction, payment_information)
                    for transaction in children(payment_information)
                    if local_name(transaction) == "CdtTrfTxInf"
                ]

    interbank = message_type == "pacs.008"
    transactions = [
        _check_transaction(transaction, block, interbank, enforce_unstructured_address_removal)
        for transaction, block in blocks[:MAX_REPORTED_TRANSACTIONS]
    ]
    all_findings = message_findings + [item for transaction in transactions for item in transaction["findings"]]
    errors = sum(1 for item in all_findings if item["severity"] == "error")
    return {
        **base,
        "kind": "sepa_sct_check",
        "message_id": detected,
        "message_type": message_type,
        "in_scope": message_type is not None,
        "compliant": message_type is not None and errors == 0,
        "summary": {
            "transactions": len(transactions),
            "errors": errors,
            "warnings": sum(1 for item in all_findings if item["severity"] == "warning"),
        },
        "message_findings": message_findings,
        "transactions": transactions,
        "transactions_truncated": len(blocks) > len(transactions),
        "errors": [],
    }
