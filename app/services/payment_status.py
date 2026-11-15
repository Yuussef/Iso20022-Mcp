"""Explain payment status reports (pacs.002, pain.002) and payment returns (pacs.004).

Every status and reason code is explained from the ISO 20022 External Code Sets
(data/reference/iso_external_codes.json). Scheme rules are applied on top:
- SEPA (EPC115-06 SCT Inter-PSP IG 2025): a pacs.002 reject carries transaction status
  RJCT, one reason with its originator, a reason from the EPC reject list, and the original
  end-to-end and transaction identifications; a pacs.004 return carries a reason from the
  EPC return list, an originator, SLEV, and the returned amount equal to the original amount
  in euro (data/reference/epc_sct_reason_codes.json).
- CBPR+ (pacs.002 as published on the Goldman Sachs developer portal; Clearstream CBPR+
  guide): the original UETR is mandatory and, when the group status is RJCT, every
  transaction status is RJCT. Reasons are optional in CBPR+.
When the original payment (pacs.008 or pain.001) is supplied, each status or return is
matched to its original transaction by UETR, end-to-end or transaction identification.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any

from app.paths import REFERENCE_DIR
from app.services.xml_safety import UntrustedXmlError, parse_untrusted_xml
from app.services.xml_tools import child, children, descendant, find_all, finding, local_name, message_id, path, text

SCHEMES = ("auto", "sepa", "cbpr", "generic")
UETR_PATTERN = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$")
MAX_TRANSACTIONS = 200
SOURCES = [
    "https://www.iso20022.org/catalogue-messages/additional-content-messages/external-code-sets",
    "https://www.europeanpaymentscouncil.eu/sites/default/files/kb/file/2025-10/EPC115-06%20SCT%20Inter-PSP%20IG%202025%20V1.0.pdf",
    "https://developer.gs.com/docs/services/transaction-banking/cbpr+-pacs002",
    "https://www.clearstream.com/caas/v1/media/4814538/data/ca917a93e9390d399c6c34ebe14032d0/cbpr-ug.pdf",
]
ROOTS = {"FIToFIPmtStsRpt": "pacs.002", "CstmrPmtStsRpt": "pain.002", "PmtRtr": "pacs.004"}


@lru_cache(maxsize=1)
def iso_codes() -> dict[str, Any]:
    return json.loads((REFERENCE_DIR / "iso_external_codes.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def epc_codes() -> dict[str, Any]:
    return json.loads((REFERENCE_DIR / "epc_sct_reason_codes.json").read_text(encoding="utf-8"))


def _meaning(code_set: str, code: str) -> str | None:
    return iso_codes()["code_sets"][code_set]["codes"].get(code)


def _status(code: str | None, code_set: str) -> dict[str, Any] | None:
    if not code:
        return None
    return {"code": code, "meaning": _meaning(code_set, code), "known": _meaning(code_set, code) is not None}


def _reasons(container: Any, element: str, code_set: str) -> list[dict[str, Any]]:
    reasons = []
    for info in (item for item in children(container) if local_name(item) == element):
        code = text(descendant(info, "Rsn", "Cd")) or None
        originator = descendant(info, "Orgtr")
        reasons.append(
            {
                "code": code,
                "proprietary": text(descendant(info, "Rsn", "Prtry")) or None,
                "meaning": _meaning(code_set, code) if code else None,
                "known": bool(code and _meaning(code_set, code)),
                "additional_info": [text(item) for item in children(info) if local_name(item) == "AddtlInf" and text(item)],
                "originator": (
                    text(descendant(originator, "Nm"))
                    or text(descendant(originator, "Id", "OrgId", "AnyBIC"))
                    or text(descendant(originator, "Id", "OrgId", "BICOrBEI"))
                    or None
                )
                if originator is not None
                else None,
                "has_originator": originator is not None,
                "xpath": path(info),
            }
        )
    return reasons


def _amount(element: Any | None) -> dict[str, Any] | None:
    if element is None:
        return None
    return {"currency": element.get("Ccy", ""), "value": text(element)}


def _decimal(amount: dict[str, Any] | None) -> Decimal | None:
    try:
        return Decimal(amount["value"]) if amount else None
    except InvalidOperation:
        return None


def _original_refs(transaction: Any, group: Any | None) -> dict[str, Any]:
    # lxml elements are falsy when they have no children, so compare with None explicitly.
    original_group = child(transaction, "OrgnlGrpInf")
    if original_group is None:
        original_group = group
    return {
        "message_id": text(child(original_group, "OrgnlMsgId")) if original_group is not None else None,
        "message_name": text(child(original_group, "OrgnlMsgNmId")) if original_group is not None else None,
        "instruction_id": text(child(transaction, "OrgnlInstrId")) or None,
        "end_to_end_id": text(child(transaction, "OrgnlEndToEndId")) or None,
        "transaction_id": text(child(transaction, "OrgnlTxId")) or None,
        "uetr": text(child(transaction, "OrgnlUETR")) or None,
    }


def _detect_scheme(root: Any) -> str:
    codes = {text(item) for item in find_all(root, "Cd") if local_name(item.getparent()) == "SvcLvl"}
    bearers = {text(item) for item in find_all(root, "ChrgBr")}
    if "SEPA" in codes or "SLEV" in bearers:
        return "sepa"
    if find_all(root, "OrgnlUETR"):
        return "cbpr"
    return "generic"


def _original_transactions(xml: str) -> list[dict[str, Any]]:
    root = parse_untrusted_xml(xml)
    header = next((item for item in root.iter() if local_name(item) == "GrpHdr"), None)
    message = text(child(header, "MsgId")) if header is not None else ""
    found = []
    for transaction in find_all(root, "CdtTrfTxInf"):
        found.append(
            {
                "message_id": message or None,
                "uetr": text(descendant(transaction, "PmtId", "UETR")) or None,
                "end_to_end_id": text(descendant(transaction, "PmtId", "EndToEndId")) or None,
                "transaction_id": text(descendant(transaction, "PmtId", "TxId")) or None,
                "instruction_id": text(descendant(transaction, "PmtId", "InstrId")) or None,
                "amount": _amount(child(transaction, "IntrBkSttlmAmt")) or _amount(descendant(transaction, "Amt", "InstdAmt")),
                "xpath": path(transaction),
            }
        )
    return found


def _match(refs: dict[str, Any], originals: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    for key in ("uetr", "end_to_end_id", "transaction_id", "instruction_id"):
        if refs.get(key) and refs[key] != "NOTPROVIDED":
            hits = [item for item in originals if item.get(key) == refs[key]]
            if len(hits) == 1:
                return hits[0], key
    return None, None


def _check_transaction(transaction: Any, kind: str, scheme: str, group: Any | None, group_status: str | None) -> dict[str, Any]:
    xpath = path(transaction)
    findings: list[dict[str, Any]] = []
    refs = _original_refs(transaction, group)
    is_return = kind == "pacs.004"
    status_code = None if is_return else (text(child(transaction, "TxSts")) or None)
    reasons = _reasons(
        transaction, "RtrRsnInf" if is_return else "StsRsnInf", "ExternalReturnReason1Code" if is_return else "ExternalStatusReason1Code"
    )
    status = (
        {"code": "RETURNED", "meaning": "Funds returned to the debtor agent (pacs.004).", "known": True}
        if is_return
        else _status(status_code, "ExternalPaymentTransactionStatus1Code")
    )

    if not is_return and status_code is None and group_status is None:
        findings.append(finding("STATUS_MISSING", "error", "No transaction or group status is given.", xpath))
    if status and not status["known"]:
        findings.append(
            finding(
                "STATUS_UNKNOWN_CODE", "warning", f"Status {status['code']!r} is not in the ISO 20022 transaction status code list.", xpath
            )
        )
    for reason in reasons:
        if reason["code"] and not reason["known"]:
            findings.append(
                finding(
                    "REASON_UNKNOWN_CODE",
                    "warning",
                    f"Reason {reason['code']!r} is not in the ISO 20022 {'return' if is_return else 'status'} reason code list "
                    f"({iso_codes()['release']}); it may be newer, bilateral or a typo.",
                    reason["xpath"],
                )
            )
    effective = status_code or group_status
    has_reason = any(reason["code"] or reason["proprietary"] for reason in reasons)
    if (effective == "RJCT" or is_return) and not has_reason:
        severity = "error" if scheme == "sepa" else "warning"
        findings.append(
            finding(
                "RETURN_WITHOUT_REASON" if is_return else "REJECT_WITHOUT_REASON",
                severity,
                f"The {'return' if is_return else 'rejection'} gives no reason code, so the cause cannot be explained.",
                xpath,
                "Ask the sender for the reason, or check the bank's own rejection report.",
            )
        )
    if not any(refs[key] for key in ("uetr", "end_to_end_id", "transaction_id", "instruction_id")):
        findings.append(
            finding("NO_ORIGINAL_REFERENCE", "warning", "No original UETR, end-to-end, transaction or instruction identification.", xpath)
        )
    if group_status == "RJCT" and status_code and status_code != "RJCT":
        findings.append(
            finding(
                "GROUP_REJECTED_TRANSACTION_NOT", "error", f"The group is rejected but this transaction has status {status_code}.", xpath
            )
        )

    if scheme == "cbpr":
        if not refs["uetr"]:
            findings.append(
                finding(
                    "CBPR_ORIGINAL_UETR_MISSING",
                    "error" if kind == "pacs.002" else "warning",
                    "The original UETR is needed to tie this message to the payment in a CBPR+ flow.",
                    xpath,
                )
            )
        elif not UETR_PATTERN.fullmatch(refs["uetr"]):
            findings.append(finding("CBPR_ORIGINAL_UETR_FORMAT", "error", f"{refs['uetr']!r} is not a lower-case UUID v4.", xpath))
        if kind == "pacs.002" and status_code is None:
            findings.append(finding("CBPR_TX_STATUS_MISSING", "error", "Transaction status is mandatory in a CBPR+ pacs.002.", xpath))

    returned = original_amount = None
    if is_return:
        returned = _amount(child(transaction, "RtrdIntrBkSttlmAmt"))
        original_amount = _amount(child(transaction, "OrgnlIntrBkSttlmAmt"))

    if scheme == "sepa" and kind in {"pacs.002", "pacs.004"}:
        allowed = epc_codes()["return_pacs004" if is_return else "reject_pacs002"]
        if not is_return and status_code and status_code != "RJCT":
            findings.append(
                finding("SEPA_TX_STATUS", "error", f"A SEPA pacs.002 only reports rejections (RJCT); found {status_code}.", xpath)
            )
        if len(reasons) > 1:
            findings.append(finding("SEPA_REASON_COUNT", "error", "Only one reason is allowed.", xpath))
        for reason in reasons:
            if not reason["has_originator"]:
                findings.append(finding("SEPA_ORIGINATOR_MISSING", "error", "The reason originator is mandatory.", reason["xpath"]))
            if reason["code"] and reason["code"] not in allowed:
                findings.append(
                    finding(
                        "SEPA_REASON_NOT_ALLOWED",
                        "error",
                        f"{reason['code']} is not a SEPA Credit Transfer {'return' if is_return else 'reject'} reason "
                        f"(allowed: {', '.join(sorted(allowed))}).",
                        reason["xpath"],
                    )
                )
            if reason["code"] in allowed:
                reason["scheme_meaning"] = allowed[reason["code"]]
        for key, label in (
            ("end_to_end_id", "Original End To End Identification"),
            ("transaction_id", "Original Transaction Identification"),
        ):
            if not refs[key]:
                findings.append(finding("SEPA_ORIGINAL_REFERENCE", "error", f"{label} is mandatory.", xpath))
        if refs["message_name"] and not refs["message_name"].startswith("pacs.008"):
            findings.append(
                finding(
                    "SEPA_ORIGINAL_MESSAGE_NAME",
                    "error",
                    f"The original message name must begin with pacs.008; found {refs['message_name']}.",
                    xpath,
                )
            )
        identifier = "RtrId" if is_return else "StsId"
        if not text(child(transaction, identifier)):
            findings.append(finding("SEPA_IDENTIFICATION_MISSING", "error", f"{identifier} is mandatory.", xpath))
        if is_return:
            if (
                returned
                and original_amount
                and (_decimal(returned) != _decimal(original_amount) or returned["currency"] != original_amount["currency"])
            ):
                findings.append(
                    finding(
                        "SEPA_RETURN_AMOUNT",
                        "error",
                        f"The returned amount ({returned['value']} {returned['currency']}) must equal the original amount "
                        f"({original_amount['value']} {original_amount['currency']}).",
                        xpath,
                    )
                )
            if returned and returned["currency"] != "EUR":
                findings.append(finding("SEPA_CURRENCY", "error", "SEPA returns are in euro only.", xpath))
            bearer = text(child(transaction, "ChrgBr"))
            if bearer and bearer != "SLEV":
                findings.append(finding("SEPA_CHARGE_BEARER", "error", f"Only SLEV is allowed; found {bearer}.", xpath))

    return {
        "xpath": xpath,
        "status": status,
        "reasons": reasons,
        "original": refs,
        "returned_amount": returned,
        "original_amount": original_amount,
        "settlement_date": text(child(transaction, "IntrBkSttlmDt")) or None,
        "findings": findings,
    }


def explain_payment_status(xml: str, original_xml: str | None = None, scheme: str = "auto") -> dict[str, Any]:
    """Explain a pacs.002, pain.002 or pacs.004 and check it against the scheme rules.

    Raises ValueError when an input exceeds the size limit or the scheme is unknown.
    """
    if scheme not in SCHEMES:
        raise ValueError(f"scheme must be one of {', '.join(SCHEMES)}")
    base = {"code_list_release": iso_codes()["release"], "sources": SOURCES}
    try:
        root = parse_untrusted_xml(xml)
    except UntrustedXmlError as exc:
        return {**base, "kind": exc.kind, "message_type": None, "compliant": False, "transactions": [], "errors": [exc.as_error()]}

    document = next((element for element in root.iter() if local_name(element) in ROOTS), None)
    if document is None:
        return {
            **base,
            "kind": "payment_status_explanation",
            "message_id": message_id(root),
            "message_type": None,
            "in_scope": False,
            "compliant": False,
            "transactions": [],
            "errors": [],
            "note": "Only pacs.002, pain.002 and pacs.004 are explained by this tool; use read_iso20022_message for other messages.",
        }

    kind = ROOTS[local_name(document)]
    applied = _detect_scheme(root) if scheme == "auto" else scheme
    group = child(document, "OrgnlGrpInfAndSts")
    if group is None:
        group = child(document, "OrgnlGrpInf")
    group_status_code = text(child(group, "GrpSts")) if group is not None else ""
    group_status = _status(group_status_code or None, "ExternalPaymentGroupStatus1Code")
    group_reasons = _reasons(group, "StsRsnInf", "ExternalStatusReason1Code") if group is not None else []
    message_findings: list[dict[str, Any]] = []
    if applied == "sepa" and kind == "pacs.002" and group_status_code and group_status_code not in {"RJCT", "PART"}:
        message_findings.append(
            finding(
                "SEPA_GROUP_STATUS", "error", f"Only RJCT and PART are allowed as group status; found {group_status_code}.", path(group)
            )
        )
    if group_status and not group_status["known"]:
        message_findings.append(
            finding("STATUS_UNKNOWN_CODE", "warning", f"Group status {group_status_code!r} is not an ISO code.", path(group))
        )

    if kind == "pain.002":
        pairs = []
        for block in (item for item in children(document) if local_name(item) == "OrgnlPmtInfAndSts"):
            block_status = text(child(block, "PmtInfSts")) or group_status_code or None
            pairs += [(item, block_status) for item in children(block) if local_name(item) == "TxInfAndSts"]
    else:
        element = "TxInf" if kind == "pacs.004" else "TxInfAndSts"
        pairs = [(item, group_status_code or None) for item in children(document) if local_name(item) == element]

    transactions = [_check_transaction(item, kind, applied, group, status) for item, status in pairs[:MAX_TRANSACTIONS]]

    match_summary = None
    if original_xml:
        try:
            originals = _original_transactions(original_xml)
        except UntrustedXmlError as exc:
            message_findings.append(finding("ORIGINAL_UNREADABLE", "error", f"The original message cannot be read: {exc.message}", ""))
            originals = []
        matched = 0
        for transaction in transactions:
            original, key = _match(transaction["original"], originals)
            transaction["match"] = {"matched_by": key, "original_xpath": original["xpath"] if original else None}
            if original is None:
                transaction["findings"].append(
                    finding(
                        "ORIGINAL_NOT_FOUND",
                        "error",
                        "No transaction in the original message has the same UETR or references.",
                        transaction["xpath"],
                    )
                )
                continue
            matched += 1
            reported = transaction["original"]["message_id"]
            if reported and original["message_id"] and reported != original["message_id"]:
                transaction["findings"].append(
                    finding(
                        "ORIGINAL_MESSAGE_ID_MISMATCH",
                        "warning",
                        f"Original message identification {reported!r} differs from the supplied message ({original['message_id']!r}).",
                        transaction["xpath"],
                    )
                )
            if transaction["original_amount"] and original["amount"]:
                if (
                    _decimal(transaction["original_amount"]) != _decimal(original["amount"])
                    or transaction["original_amount"]["currency"] != original["amount"]["currency"]
                ):
                    transaction["findings"].append(
                        finding(
                            "ORIGINAL_AMOUNT_MISMATCH",
                            "error",
                            "The original amount stated here "
                            f"({transaction['original_amount']['value']} {transaction['original_amount']['currency']}) "
                            f"differs from the original payment ({original['amount']['value']} {original['amount']['currency']}).",
                            transaction["xpath"],
                        )
                    )
        match_summary = {"original_transactions": len(originals), "matched": matched}

    everything = message_findings + [item for transaction in transactions for item in transaction["findings"]]
    errors = sum(1 for item in everything if item["severity"] == "error")
    header = child(document, "GrpHdr")
    return {
        **base,
        "kind": "payment_status_explanation",
        "message_id": message_id(root),
        "message_type": kind,
        "scheme": applied,
        "in_scope": True,
        "compliant": errors == 0,
        "message_identification": text(child(header, "MsgId")) if header is not None else None,
        "group": {"status": group_status, "reasons": group_reasons, "original_message_id": text(child(group, "OrgnlMsgId")) or None}
        if group is not None
        else None,
        "summary": {
            "transactions": len(transactions),
            "rejected": sum(1 for item in transactions if item["status"] and item["status"]["code"] == "RJCT"),
            "returned": len(transactions) if kind == "pacs.004" else 0,
            "errors": errors,
            "warnings": sum(1 for item in everything if item["severity"] == "warning"),
        },
        "match": match_summary,
        "message_findings": message_findings,
        "transactions": transactions,
        "transactions_truncated": len(pairs) > len(transactions),
        "errors": [],
    }
