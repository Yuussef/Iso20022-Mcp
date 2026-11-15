"""Read any ISO 20022 message and restate what it contains, without judging it.

The reader identifies the message, then collects what people usually look for: the business
application header, group header, references (UETR, end-to-end IDs), amounts, parties and
agents, status and reason codes (explained from the ISO external code sets), statement
entries and balances (camt.052/053/054), and an outline of the structure. It also says which
specialised tool can check the message against scheme rules.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.payment_status import iso_codes
from app.services.xml_safety import UntrustedXmlError, parse_untrusted_xml
from app.services.xml_tools import child, children, descendant, find_all, local_name, message_id, path, text

# ISO 20022 message names for common payments and cash-management messages.
MESSAGE_NAMES = {
    "pacs.002": ("FIToFIPaymentStatusReport", "Status of one or more interbank payments, for example a rejection."),
    "pacs.003": ("FIToFICustomerDirectDebit", "Interbank customer direct debit."),
    "pacs.004": ("PaymentReturn", "Return of funds of a payment that was already settled."),
    "pacs.007": ("FIToFIPaymentReversal", "Reversal of a settled interbank payment."),
    "pacs.008": ("FIToFICustomerCreditTransfer", "Interbank customer credit transfer."),
    "pacs.009": ("FinancialInstitutionCreditTransfer", "Credit transfer between financial institutions, including cover payments (COV)."),
    "pacs.010": ("FinancialInstitutionDirectDebit", "Direct debit between financial institutions."),
    "pacs.028": ("FIToFIPaymentStatusRequest", "Request for the status of an interbank payment."),
    "pain.001": ("CustomerCreditTransferInitiation", "Payment order from a customer to its bank."),
    "pain.002": ("CustomerPaymentStatusReport", "Bank's status report on a customer's payment order."),
    "pain.007": ("CustomerPaymentReversal", "Customer's reversal of a direct debit."),
    "pain.008": ("CustomerDirectDebitInitiation", "Direct debit collection order from a creditor to its bank."),
    "pain.013": ("CreditorPaymentActivationRequest", "Request to pay sent by a creditor."),
    "pain.014": ("CreditorPaymentActivationRequestStatusReport", "Status of a request to pay."),
    "camt.026": ("UnableToApply", "Investigation: the receiver cannot apply a payment."),
    "camt.027": ("ClaimNonReceipt", "Investigation: the creditor says the funds did not arrive."),
    "camt.029": ("ResolutionOfInvestigation", "Answer to a cancellation request or investigation."),
    "camt.052": ("BankToCustomerAccountReport", "Intraday account report."),
    "camt.053": ("BankToCustomerStatement", "End-of-day account statement."),
    "camt.054": ("BankToCustomerDebitCreditNotification", "Notification of individual debits and credits."),
    "camt.055": ("CustomerPaymentCancellationRequest", "Customer's request to cancel a payment order."),
    "camt.056": ("FIToFIPaymentCancellationRequest", "Interbank request to cancel or recall a payment."),
    "camt.057": ("NotificationToReceive", "Advance notice that funds will arrive."),
    "camt.060": ("AccountReportingRequest", "Request for an account report or statement."),
    "camt.087": ("RequestToModifyPayment", "Investigation: request to change a payment."),
    "admi.002": ("MessageReject", "Technical rejection of a message."),
    "admi.024": ("NotificationOfCorrespondence", "Free-format notification between institutions."),
}
PARTY_ROLES = ("Dbtr", "Cdtr", "UltmtDbtr", "UltmtCdtr", "InitgPty")
AGENT_ROLES = ("DbtrAgt", "CdtrAgt", "InstgAgt", "InstdAgt", "IntrmyAgt1", "IntrmyAgt2", "IntrmyAgt3", "Svcr")
MAX_ITEMS = 50
MAX_ENTRIES = 20


def _tools_for(prefix: str | None, has_address: bool) -> list[str]:
    tools = {
        "pacs.008": ["check_cbpr_pacs008", "check_sepa_sct", "summarize_payment"],
        "pain.001": ["check_sepa_sct", "summarize_payment"],
        "pacs.002": ["explain_payment_status"],
        "pain.002": ["explain_payment_status"],
        "pacs.004": ["explain_payment_status"],
    }.get(prefix or "", [])
    if has_address and prefix not in {"camt.052", "camt.053", "camt.054", "camt.060", "camt.025", "admi.024"}:
        tools.append("check_cbpr_postal_addresses")
    return tools


def _outline(element: Any, depth: int = 0, max_depth: int = 3) -> dict[str, Any]:
    names = Counter(local_name(item) for item in children(element))
    node: dict[str, Any] = {"name": local_name(element)}
    if depth < max_depth and names:
        node["children"] = []
        seen = set()
        for item in children(element):
            name = local_name(item)
            if name in seen:
                continue
            seen.add(name)
            entry = _outline(item, depth + 1, max_depth)
            if names[name] > 1:
                entry["count"] = names[name]
            node["children"].append(entry)
    return node


def _codes(root: Any) -> list[dict[str, Any]]:
    sets = iso_codes()["code_sets"]
    found = []
    seen = set()
    for element in root.iter():
        name = local_name(element)
        value = text(element)
        if not value:
            continue
        code_set = None
        if name in {"TxSts", "Sts"} and local_name(element.getparent()) != "Ntry":
            code_set = "ExternalPaymentTransactionStatus1Code"
        elif name in {"GrpSts", "PmtInfSts"}:
            code_set = "ExternalPaymentGroupStatus1Code"
        elif name == "Cd" and local_name(element.getparent()) == "Rsn":
            grandparent = local_name(element.getparent().getparent())
            code_set = (
                "ExternalReturnReason1Code"
                if grandparent == "RtrRsnInf"
                else "ExternalStatusReason1Code"
                if grandparent == "StsRsnInf"
                else None
            )
        if code_set and (name, value, code_set) not in seen:
            seen.add((name, value, code_set))
            found.append(
                {
                    "element": name,
                    "code": value,
                    "code_set": code_set,
                    "meaning": sets[code_set]["codes"].get(value),
                    "xpath": path(element),
                }
            )
    return found[:MAX_ITEMS]


def _entries(root: Any) -> dict[str, Any] | None:
    entries = find_all(root, "Ntry")
    if not entries:
        return None
    totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"CRDT": Decimal(0), "DBIT": Decimal(0)})
    items = []
    for entry in entries:
        amount = child(entry, "Amt")
        indicator = text(child(entry, "CdtDbtInd"))
        currency = amount.get("Ccy", "") if amount is not None else ""
        try:
            value = Decimal(text(amount)) if amount is not None else Decimal(0)
        except InvalidOperation:
            value = Decimal(0)
        if indicator in {"CRDT", "DBIT"}:
            totals[currency][indicator] += value
        if len(items) < MAX_ENTRIES:
            items.append(
                {
                    "amount": text(amount) or None,
                    "currency": currency or None,
                    "credit_debit": indicator or None,
                    "status": text(descendant(entry, "Sts", "Cd")) or text(child(entry, "Sts")) or None,
                    "booking_date": text(descendant(entry, "BookgDt", "Dt")) or text(descendant(entry, "BookgDt", "DtTm")) or None,
                    "value_date": text(descendant(entry, "ValDt", "Dt")) or None,
                    "bank_reference": text(child(entry, "AcctSvcrRef")) or None,
                    "end_to_end_ids": sorted({text(item) for item in find_all(entry, "EndToEndId") if text(item)})[:5],
                    "remittance": " ".join(text(item) for item in find_all(entry, "Ustrd") if text(item))[:140] or None,
                }
            )
    return {
        "count": len(entries),
        "totals": {currency: {"credits": str(value["CRDT"]), "debits": str(value["DBIT"])} for currency, value in sorted(totals.items())},
        "items": items,
        "items_truncated": len(entries) > len(items),
    }


def _balances(root: Any) -> list[dict[str, Any]]:
    balances = []
    for balance in find_all(root, "Bal")[:MAX_ITEMS]:
        amount = child(balance, "Amt")
        balances.append(
            {
                "type": text(descendant(balance, "Tp", "CdOrPrtry", "Cd")) or text(descendant(balance, "Tp", "CdOrPrtry", "Prtry")) or None,
                "amount": text(amount) or None,
                "currency": amount.get("Ccy") if amount is not None else None,
                "credit_debit": text(child(balance, "CdtDbtInd")) or None,
                "date": text(descendant(balance, "Dt", "Dt")) or text(descendant(balance, "Dt", "DtTm")) or None,
            }
        )
    return balances


def read_message(xml: str) -> dict[str, Any]:
    """Describe any ISO 20022 message. Raises ValueError when the input is too large."""
    try:
        root = parse_untrusted_xml(xml)
    except UntrustedXmlError as exc:
        return {"kind": exc.kind, "message_id": None, "errors": [exc.as_error()]}

    detected = message_id(root)
    prefix = detected[:8] if detected else None
    name, purpose = MESSAGE_NAMES.get(prefix or "", (None, None))
    document = next((item for item in root.iter() if local_name(item) == "Document"), root)
    business = next(iter(children(document)), None)
    header = next((item for item in root.iter() if local_name(item) == "AppHdr"), None)
    group = next((item for item in root.iter() if local_name(item) == "GrpHdr"), None)

    amounts = [
        {"element": local_name(item), "currency": item.get("Ccy"), "value": text(item), "xpath": path(item)}
        for item in root.iter()
        if isinstance(item.tag, str) and item.get("Ccy") and text(item)
    ]
    parties = []
    for role in PARTY_ROLES:
        for party in find_all(root, role)[:MAX_ITEMS]:
            parties.append(
                {
                    "role": role,
                    "name": text(child(party, "Nm")) or text(descendant(party, "Pty", "Nm")) or None,
                    "bic": text(descendant(party, "Id", "OrgId", "AnyBIC")) or None,
                    "country": text(descendant(party, "PstlAdr", "Ctry")) or None,
                    "xpath": path(party),
                }
            )
    agents = []
    for role in AGENT_ROLES:
        for agent in find_all(root, role)[:MAX_ITEMS]:
            institution = child(agent, "FinInstnId")
            if institution is not None:
                agents.append(
                    {
                        "role": role,
                        "bic": text(child(institution, "BICFI")) or None,
                        "name": text(child(institution, "Nm")) or None,
                        "xpath": path(agent),
                    }
                )

    def values(element_name: str) -> list[str]:
        return sorted({text(item) for item in find_all(root, element_name) if text(item)})[:MAX_ITEMS]

    return {
        "kind": "message_reading",
        "message_id": detected,
        "message_name": name or (local_name(business) if business is not None else None),
        "purpose": purpose,
        "recognised": name is not None,
        "root_element": local_name(business) if business is not None else local_name(root),
        "business_header": {
            "from": text(descendant(header, "Fr", "FIId", "FinInstnId", "BICFI")) or None,
            "to": text(descendant(header, "To", "FIId", "FinInstnId", "BICFI")) or None,
            "business_message_id": text(child(header, "BizMsgIdr")) or None,
            "message_definition": text(child(header, "MsgDefIdr")) or None,
            "business_service": text(child(header, "BizSvc")) or None,
        }
        if header is not None
        else None,
        "group_header": {
            "message_identification": text(child(group, "MsgId")) or None,
            "created": text(child(group, "CreDtTm")) or None,
            "number_of_transactions": text(child(group, "NbOfTxs")) or None,
            "control_sum": text(child(group, "CtrlSum")) or None,
        }
        if group is not None
        else None,
        "references": {
            "uetr": values("UETR") + values("OrgnlUETR"),
            "end_to_end_ids": values("EndToEndId") + values("OrgnlEndToEndId"),
            "instruction_ids": values("InstrId") + values("OrgnlInstrId"),
            "transaction_ids": values("TxId") + values("OrgnlTxId"),
        },
        "amounts": amounts[:MAX_ITEMS],
        "amounts_truncated": len(amounts) > MAX_ITEMS,
        "parties": parties[:MAX_ITEMS],
        "agents": agents[:MAX_ITEMS],
        "ibans": values("IBAN"),
        "codes": _codes(root),
        "entries": _entries(root),
        "balances": _balances(root),
        "outline": _outline(business) if business is not None else None,
        "suggested_tools": _tools_for(prefix, bool(find_all(root, "PstlAdr"))),
        "note": "This restates the message content. It does not check it against scheme rules unless a suggested tool is used.",
        "errors": [],
    }
