"""Plain-language summary of a credit transfer message (pacs.008 or pain.001), for people and agents.

The summary only restates what the message contains; it does not judge validity.
"""

from __future__ import annotations

from typing import Any

from app.services.xml_safety import UntrustedXmlError, parse_untrusted_xml
from app.services.xml_tools import child, children, descendant, local_name, message_id, path, text

AGENT_CHAIN = (
    ("PrvsInstgAgt1", "Previous instructing agent 1"),
    ("PrvsInstgAgt2", "Previous instructing agent 2"),
    ("PrvsInstgAgt3", "Previous instructing agent 3"),
    ("InstgAgt", "Instructing agent"),
    ("DbtrAgt", "Debtor agent"),
    ("IntrmyAgt1", "Intermediary agent 1"),
    ("IntrmyAgt2", "Intermediary agent 2"),
    ("IntrmyAgt3", "Intermediary agent 3"),
    ("InstdAgt", "Instructed agent"),
    ("CdtrAgt", "Creditor agent"),
)
MAX_TRANSACTIONS = 50


def _amount(element: Any | None) -> dict[str, str] | None:
    if element is None:
        return None
    return {"currency": element.get("Ccy", ""), "value": text(element)}


def _address(element: Any | None) -> str | None:
    if element is None:
        return None
    order = [
        "Dept",
        "SubDept",
        "StrtNm",
        "BldgNb",
        "BldgNm",
        "Flr",
        "PstBx",
        "Room",
        "PstCd",
        "TwnNm",
        "TwnLctnNm",
        "DstrctNm",
        "CtrySubDvsn",
    ]
    parts = [text(child(element, name)) for name in order if text(child(element, name))]
    parts += [text(line) for line in children(element) if local_name(line) == "AdrLine" and text(line)]
    country = text(child(element, "Ctry"))
    if country:
        parts.append(country)
    return ", ".join(parts) or None


def _party(element: Any | None) -> dict[str, Any] | None:
    if element is None:
        return None
    organisation = descendant(element, "Id", "OrgId")
    return {
        "name": text(child(element, "Nm")) or None,
        "address": _address(child(element, "PstlAdr")),
        "country": text(descendant(element, "PstlAdr", "Ctry")) or text(child(element, "CtryOfRes")) or None,
        "bic": text(child(organisation, "AnyBIC")) or None if organisation is not None else None,
        "lei": text(child(organisation, "LEI")) or None if organisation is not None else None,
    }


def _account(element: Any | None) -> str | None:
    if element is None:
        return None
    return text(descendant(element, "Id", "IBAN")) or text(descendant(element, "Id", "Othr", "Id")) or None


def _agent(element: Any | None) -> dict[str, Any] | None:
    institution = child(element, "FinInstnId") if element is not None else None
    if institution is None:
        return None
    return {
        "bic": text(child(institution, "BICFI")) or None,
        "name": text(child(institution, "Nm")) or None,
        "clearing_member_id": text(descendant(institution, "ClrSysMmbId", "MmbId")) or None,
        "lei": text(child(institution, "LEI")) or None,
    }


def _remittance(element: Any | None) -> dict[str, Any] | None:
    if element is None:
        return None
    references = [text(item) for item in element.iter() if local_name(item) in {"Ref", "Nb"} and text(item)]
    return {
        "unstructured": [text(item) for item in children(element) if local_name(item) == "Ustrd"],
        "references": references,
    }


def _transaction(transaction: Any, scope: Any) -> dict[str, Any]:
    chain = []
    for role, label in AGENT_CHAIN:
        # In pain.001 the debtor agent sits on the payment information block, not on the transaction.
        details = _agent(child(transaction, role)) or (_agent(child(scope, role)) if role == "DbtrAgt" else None)
        if details:
            chain.append({"role": role, "label": label, **details})
    return {
        "xpath": path(transaction),
        "uetr": text(descendant(transaction, "PmtId", "UETR")) or None,
        "end_to_end_id": text(descendant(transaction, "PmtId", "EndToEndId")) or None,
        "interbank_settlement_amount": _amount(child(transaction, "IntrBkSttlmAmt")),
        "instructed_amount": _amount(child(transaction, "InstdAmt")) or _amount(descendant(transaction, "Amt", "InstdAmt")),
        "exchange_rate": text(child(transaction, "XchgRate")) or None,
        "settlement_date": text(child(transaction, "IntrBkSttlmDt")) or text(descendant(scope, "IntrBkSttlmDt")) or None,
        "requested_execution_date": text(descendant(scope, "ReqdExctnDt", "Dt")) or text(child(scope, "ReqdExctnDt")) or None,
        "charge_bearer": text(child(transaction, "ChrgBr")) or text(child(scope, "ChrgBr")) or None,
        "charges": [_amount(child(item, "Amt")) for item in children(transaction) if local_name(item) == "ChrgsInf"],
        "service_level": text(descendant(transaction, "PmtTpInf", "SvcLvl", "Cd"))
        or text(descendant(scope, "PmtTpInf", "SvcLvl", "Cd"))
        or None,
        "purpose": text(descendant(transaction, "Purp", "Cd")) or None,
        "ultimate_debtor": _party(child(transaction, "UltmtDbtr")) or _party(child(scope, "UltmtDbtr")),
        "debtor": _party(child(transaction, "Dbtr")) or _party(child(scope, "Dbtr")),
        "debtor_account": _account(child(transaction, "DbtrAcct")) or _account(child(scope, "DbtrAcct")),
        "creditor": _party(child(transaction, "Cdtr")),
        "creditor_account": _account(child(transaction, "CdtrAcct")),
        "ultimate_creditor": _party(child(transaction, "UltmtCdtr")),
        "agent_chain": chain,
        "remittance": _remittance(child(transaction, "RmtInf")),
    }


def summarize_payment(xml: str) -> dict[str, Any]:
    """Summarise who pays whom, how much, through which banks and why. Raises ValueError when too large."""
    try:
        root = parse_untrusted_xml(xml)
    except UntrustedXmlError as exc:
        return {"kind": exc.kind, "message_id": None, "message_type": None, "transactions": [], "errors": [exc.as_error()]}

    interbank = next((element for element in root.iter() if local_name(element) == "FIToFICstmrCdtTrf"), None)
    initiation = next((element for element in root.iter() if local_name(element) == "CstmrCdtTrfInitn"), None)
    pairs: list[tuple[Any, Any]] = []
    message_type = None
    if interbank is not None:
        message_type = "pacs.008"
        header = child(interbank, "GrpHdr")
        pairs = [(item, header) for item in children(interbank) if local_name(item) == "CdtTrfTxInf"]
    elif initiation is not None:
        message_type = "pain.001"
        for block in (item for item in children(initiation) if local_name(item) == "PmtInf"):
            pairs += [(item, block) for item in children(block) if local_name(item) == "CdtTrfTxInf"]

    header = descendant(interbank if interbank is not None else initiation, "GrpHdr") if message_type else None
    return {
        "kind": "payment_summary",
        "message_id": message_id(root),
        "message_type": message_type,
        "group": {
            "message_identification": text(child(header, "MsgId")) or None,
            "created": text(child(header, "CreDtTm")) or None,
            "number_of_transactions": text(child(header, "NbOfTxs")) or None,
        }
        if header is not None
        else None,
        "transactions": [_transaction(transaction, scope) for transaction, scope in pairs[:MAX_TRANSACTIONS]],
        "transactions_truncated": len(pairs) > MAX_TRANSACTIONS,
        "note": "This summary restates the message content; it does not validate it.",
        "errors": [],
    }
