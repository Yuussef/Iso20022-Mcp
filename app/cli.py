"""`iso20022-check`: run the payment checks from a terminal or from an agent skill.

Examples:
    iso20022-check payment.xml                 # picks SEPA or CBPR+ from the message
    iso20022-check payment.xml --profile sepa
    iso20022-check payment.xml --summary --json
    iso20022-check --iban "DE89 3704 0044 0532 0130 00"
    iso20022-check --bic DEUTDEFF
    iso20022-check --mt103 message.txt

Exit codes: 0 no errors, 1 rule errors found, 2 the input could not be read.
Everything runs offline; no message content leaves the machine.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.services.cbpr_pacs008 import check_cbpr_pacs008
from app.services.identifiers import validate_bic, validate_iban
from app.services.message_reader import read_message
from app.services.mt103 import Mt103Error, convert_mt103
from app.services.payment_status import SCHEMES, explain_payment_status
from app.services.payment_summary import summarize_payment
from app.services.postal_address import check_postal_addresses
from app.services.sepa_sct import check_sepa_sct
from app.services.xml_safety import UntrustedXmlError, parse_untrusted_xml
from app.services.xml_tools import local_name, text

PROFILES = ("auto", "sepa", "cbpr", "address", "status", "read")
STATUS_ROOTS = {"FIToFIPmtStsRpt", "CstmrPmtStsRpt", "PmtRtr"}
PAYMENT_ROOTS = {"FIToFICstmrCdtTrf", "CstmrCdtTrfInitn"}


def _choose_profile(xml: str) -> str:
    """status for pacs.002/pain.002/pacs.004; SEPA for pain.001 and pacs.008 with service level SEPA;
    CBPR+ for other pacs.008; read for every other message."""
    try:
        root = parse_untrusted_xml(xml)
    except UntrustedXmlError:
        return "cbpr"
    names = {local_name(element) for element in root.iter()}
    if names & STATUS_ROOTS:
        return "status"
    if not names & PAYMENT_ROOTS:
        return "read"
    if "CstmrCdtTrfInitn" in names:
        return "sepa"
    service_levels = {
        text(element) for element in root.iter() if local_name(element) == "Cd" and local_name(element.getparent()) == "SvcLvl"
    }
    return "sepa" if "SEPA" in service_levels else "cbpr"


def _findings(result: dict[str, Any]) -> list[dict[str, Any]]:
    found = list(result.get("message_findings", []))
    for transaction in result.get("transactions", []):
        found += transaction.get("findings", [])
    postal = result.get("postal_addresses") or (result if result.get("kind") == "postal_address_check" else None)
    for address in (postal or {}).get("addresses", []):
        found += address.get("findings", [])
    return found


def _print_findings(result: dict[str, Any], title: str) -> int:
    if result.get("errors"):
        for error in result["errors"]:
            print(f"FAIL {error['code']}: {error['message']}")
        return 2
    if result.get("in_scope") is False:
        print(f"SKIP {title}: this message type is out of scope.")
        return 0
    findings = _findings(result)
    errors = [item for item in findings if item["severity"] == "error"]
    status = "PASS meets" if not errors else "FAIL breaks"
    print(
        f"{status} {title} | {result.get('message_id') or 'unknown message'} | {len(errors)} error(s), "
        f"{sum(1 for item in findings if item['severity'] == 'warning')} warning(s)"
    )
    for item in findings:
        print(f"  [{item['severity'].upper()}] {item['rule']}: {item['message']}")
        if item.get("suggestion"):
            print(f"      fix: {item['suggestion']}")
        if item.get("xpath"):
            print(f"      at {item['xpath']}")
    return 1 if errors else 0


def _print_summary(summary: dict[str, Any]) -> None:
    for transaction in summary.get("transactions", []):
        amount = transaction.get("interbank_settlement_amount") or transaction.get("instructed_amount") or {}
        debtor = (transaction.get("debtor") or {}).get("name") or "?"
        creditor = (transaction.get("creditor") or {}).get("name") or "?"
        route = [agent for agent in transaction.get("agent_chain", []) if agent["role"] not in {"InstgAgt", "InstdAgt"}]
        banks = " -> ".join(agent.get("bic") or agent.get("name") or "?" for agent in route)
        print(f"* {debtor} pays {creditor} {amount.get('value', '?')} {amount.get('currency', '')}".rstrip())
        if banks:
            print(f"  banks: {banks}")
        if transaction.get("uetr"):
            print(f"  UETR {transaction['uetr']}")


def _print_status(result: dict[str, Any]) -> None:
    group = result.get("group") or {}
    if group.get("status"):
        status = group["status"]
        print(f"* group status {status['code']}: {status['meaning'] or 'not an ISO code'}")
    for transaction in result.get("transactions", []):
        status = transaction.get("status") or {}
        original = transaction["original"]
        reference = original.get("uetr") or original.get("end_to_end_id") or original.get("transaction_id") or "?"
        print(f"* {status.get('code', '?')} {reference}: {status.get('meaning') or 'not an ISO code'}")
        for reason in transaction.get("reasons", []):
            label = reason.get("code") or reason.get("proprietary") or "?"
            print(f"  reason {label}: {reason.get('meaning') or 'not in the ISO list'}")
            if reason.get("scheme_meaning"):
                print(f"    SEPA: {reason['scheme_meaning']}")
            for info in reason.get("additional_info", []):
                print(f"    info: {info}")
        if transaction.get("returned_amount"):
            amount = transaction["returned_amount"]
            print(f"  returned {amount['value']} {amount['currency']}")
        if transaction.get("match"):
            matched = transaction["match"]["matched_by"]
            print(f"  original payment: {'matched by ' + matched if matched else 'NOT FOUND'}")


def _print_reading(result: dict[str, Any]) -> int:
    if result.get("errors"):
        return _print_findings(result, "reader")
    print(f"* {result.get('message_id') or 'unknown message'}: {result.get('message_name') or '?'}")
    if result.get("purpose"):
        print(f"  {result['purpose']}")
    references = {key: value for key, value in result["references"].items() if value}
    for key, value in references.items():
        print(f"  {key}: {', '.join(value[:5])}")
    if result["amounts"]:
        print(f"  amounts: {len(result['amounts'])} (first: {result['amounts'][0]['value']} {result['amounts'][0]['currency']})")
    for code in result["codes"]:
        print(f"  {code['element']} {code['code']}: {code['meaning'] or 'not in the ISO list'}")
    entries = result.get("entries")
    if entries:
        totals = "; ".join(f"{ccy} credits {t['credits']} / debits {t['debits']}" for ccy, t in entries["totals"].items())
        print(f"  entries: {entries['count']} ({totals})")
    for balance in result["balances"]:
        print(f"  balance {balance['type']}: {balance['amount']} {balance['currency']} {balance['credit_debit']} on {balance['date']}")
    if result["suggested_tools"]:
        print(f"  check it with: {', '.join(result['suggested_tools'])}")
    return 0


def _emit(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")  # legacy Windows consoles cannot print every symbol
    parser = argparse.ArgumentParser(
        prog="iso20022-check", description="Offline ISO 20022 payment checks (SEPA, CBPR+, addresses, IBAN/BIC, MT103)."
    )
    parser.add_argument(
        "file", nargs="?", help="ISO 20022 XML file (pacs.008, pain.001, pacs.002, pain.002, pacs.004 or any other message)"
    )
    parser.add_argument("--original", metavar="FILE", help="with a status or return: the original pacs.008 or pain.001 to match")
    parser.add_argument("--scheme", choices=SCHEMES, default="auto", help="with a status or return: rule set (default: detected)")
    parser.add_argument("--profile", choices=PROFILES, default="auto", help="rule set to apply (default: picked from the message)")
    parser.add_argument("--summary", action="store_true", help="also print who pays whom through which banks")
    parser.add_argument("--enforce-address-removal", action="store_true", help="treat unstructured addresses as errors")
    parser.add_argument("--iban", help="validate one IBAN")
    parser.add_argument("--bic", help="validate one BIC")
    parser.add_argument("--mt103", metavar="FILE", help="draft a pacs.008 from an MT103 text file and report the conversion")
    parser.add_argument("--json", action="store_true", help="print the full JSON result")
    args = parser.parse_args(argv)

    if args.iban or args.bic:
        result = validate_iban(args.iban) if args.iban else validate_bic(args.bic)
        if args.json:
            _emit(result, True)
        else:
            label = result.get("print_format") or result.get("bic")
            print(
                f"{'PASS valid' if result['valid'] else 'FAIL invalid'} {label}"
                + (f" | {result.get('country')}" if result.get("country") else "")
            )
            for error in result["errors"]:
                print(f"  {error['code']}: {error['message']}")
            print(f"  note: {result['limitation']}")
        return 0 if result["valid"] else 1

    if args.mt103:
        try:
            result = convert_mt103(Path(args.mt103).read_text(encoding="utf-8"))
        except (OSError, Mt103Error, ValueError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        if args.json:
            _emit(result, True)
            return 0 if result["cbpr_check"]["compliant"] else 1
        for item in result["report"]:
            target = f" -> {item['target']}" if item["target"] else ""
            print(f"  {item['field']:>9} {item['status'].upper():<12}{target}  {item['detail']}")
        print()
        print(result["xml"])
        code = _print_findings(result["cbpr_check"], "CBPR+ rules (draft)")
        print(f"note: {result['disclaimer']}")
        return code

    if not args.file:
        parser.print_help()
        return 2
    try:
        xml = Path(args.file).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"FAIL cannot read {args.file}: {exc}", file=sys.stderr)
        return 2

    profile = _choose_profile(xml) if args.profile == "auto" else args.profile
    if profile in {"status", "read"}:
        try:
            original = Path(args.original).read_text(encoding="utf-8") if args.original else None
            result = explain_payment_status(xml, original, args.scheme) if profile == "status" else read_message(xml)
        except (OSError, ValueError) as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        if args.json:
            _emit({"profile": profile, "result": result}, True)
            return 2 if result.get("errors") else (1 if result.get("compliant") is False and result.get("in_scope") else 0)
        if profile == "read":
            return _print_reading(result)
        _print_status(result)
        return _print_findings(result, f"{(result.get('scheme') or 'generic').upper()} status/return rules")

    try:
        if profile == "sepa":
            result, title = check_sepa_sct(xml, args.enforce_address_removal), "EPC SEPA Credit Transfer rules"
        elif profile == "address":
            result, title = check_postal_addresses(xml, args.enforce_address_removal), "CBPR+ postal address rules"
        else:
            result, title = check_cbpr_pacs008(xml, args.enforce_address_removal), "CBPR+ pacs.008 rules"
        summary = summarize_payment(xml) if args.summary else None
    except ValueError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2

    if args.json:
        _emit({"profile": profile, "result": result, "summary": summary}, True)
        return 2 if result.get("errors") else (0 if result.get("compliant", True) or result.get("in_scope") is False else 1)
    if summary:
        _print_summary(summary)
    return _print_findings(result, title)


if __name__ == "__main__":
    sys.exit(main())
