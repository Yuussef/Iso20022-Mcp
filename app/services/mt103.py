"""Read a Swift MT103 and draft the equivalent CBPR+ pacs.008.001.08, with a conversion report.

This is a learning and migration aid, not a certified translator. The mapping follows
public bank guidance on MT103 to pacs.008 translation:
- Barclays, "A new format - comparing an MT103 to a pacs.008": 121 -> UETR, 20 -> Instruction
  Identification, /ROC/ in 70 or 72 -> End To End Identification, 50 -> Debtor, 52 -> Debtor
  Agent, 57 -> Creditor Agent, 59 -> Creditor, 71A OUR/BEN/SHA -> DEBT/CRED/SHAR.
- J.P. Morgan "Migration to ISO 20022 - mapping guide", worked MT103 -> pacs.008 examples:
  32A/33B amounts, 50F structured debtor, 59 account and name, 70 -> unstructured remittance,
  72 /ACC/ -> instruction for creditor agent, other 72 codes -> instruction for next agent,
  and NOTPROVIDED when no end-to-end reference exists.
Swift's official translation rules are on MyStandards (login required). The generated message
is then checked with check_cbpr_pacs008 so the gaps that MT data leaves are visible.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.services.cbpr_pacs008 import check_cbpr_pacs008
from app.services.identifiers import validate_iban

NAMESPACE = "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"
MAX_MT_CHARS = 20_000
CHARGE_CODES = {"OUR": "DEBT", "BEN": "CRED", "SHA": "SHAR"}
SOURCES = [
    "https://www.barclayscorporate.com/content/dam/barclayscorporate-com/images/insights/innovation/ISO-Further-information-slides-15-16-18.pdf",
    "https://www.jpmorgan.com/content/dam/jpmorgan/documents/payments/iso20022-mapping-guide.pdf",
    "https://boj.org.jm/wp-content/uploads/2024/02/Annex-I-Hybrid-Outputs.pdf",
]
DISCLAIMER = (
    "Draft produced from public mapping guidance to help understand MT103 to pacs.008 migration. "
    "It is not a certified Swift translation; check the official CBPR+ translation rules before production use."
)
KNOWN_FIELDS = {
    "20",
    "23B",
    "32A",
    "33B",
    "36",
    "50A",
    "50F",
    "50K",
    "52A",
    "52D",
    "56A",
    "57A",
    "57D",
    "59",
    "59A",
    "59F",
    "70",
    "71A",
    "71F",
    "71G",
    "72",
}
BIC = re.compile(r"^[A-Z0-9]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")


class Mt103Error(ValueError):
    """The text is not an MT103 this converter can read."""


def _blocks(message: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for match in re.finditer(r"\{([1-5]):", message):
        number, start = match.group(1), match.end()
        depth, index = 1, start
        while index < len(message) and depth:
            depth += {"{": 1, "}": -1}.get(message[index], 0)
            index += 1
        blocks.setdefault(number, message[start : index - 1])
    return blocks


def _parse_fields(text_block: str) -> list[tuple[str, str]]:
    body = text_block.strip()
    body = re.sub(r"\n?-\s*$", "", body)
    fields = []
    for match in re.finditer(r"(?:^|\n)\s*:(\d{2}[A-Z]?):(.*?)(?=\n\s*:\d{2}[A-Z]?:|\Z)", body, re.DOTALL):
        lines = [line.rstrip() for line in match.group(2).strip("\n").split("\n")]
        fields.append((match.group(1), "\n".join(line.strip() for line in lines).strip()))
    return fields


def _header_bics(blocks: dict[str, str]) -> tuple[str | None, str | None]:
    """Return (sender, receiver) BIC11 from the basic and application headers when present."""
    sender = receiver = None
    basic = re.match(r"F01([A-Z0-9]{12})", blocks.get("1", ""))
    application = blocks.get("2", "")
    own = basic.group(1)[:8] + basic.group(1)[9:12] if basic else None
    if application.startswith("I"):
        found = re.match(r"I103([A-Z0-9]{12})", application)
        sender, receiver = own, (found.group(1)[:8] + found.group(1)[9:12]) if found else None
    elif application.startswith("O"):
        found = re.match(r"O103\d{4}\d{6}([A-Z0-9]{12})", application)
        sender, receiver = (found.group(1)[:8] + found.group(1)[9:12]) if found else None, own
    return sender, receiver


def _amount(value: str) -> str:
    whole, _, fraction = value.partition(",")
    return f"{int(whole or '0')}.{fraction}" if fraction else str(int(whole or "0"))


def _party_lines(value: str) -> tuple[str | None, list[str]]:
    lines = value.split("\n")
    account = None
    if lines and lines[0].startswith("/"):
        account = lines[0][1:].strip()
        lines = lines[1:]
    return account, [line for line in lines if line]


class _Builder:
    def __init__(self) -> None:
        from lxml import etree

        self.etree = etree
        self.root = etree.Element(f"{{{NAMESPACE}}}Document", nsmap={None: NAMESPACE})

    def add(self, parent: Any, *path: str, text: str | None = None, attrib: dict[str, str] | None = None) -> Any:
        node = parent
        for name in path:
            node = self.etree.SubElement(node, f"{{{NAMESPACE}}}{name}")
        if text is not None:
            node.text = text
        for key, value in (attrib or {}).items():
            node.set(key, value)
        return node

    def xml(self) -> str:
        return self.etree.tostring(self.root, pretty_print=True, encoding="unicode")


def convert_mt103(message: str, created_at: datetime | None = None) -> dict[str, Any]:
    """Draft a pacs.008.001.08 from an MT103 and report how each field was carried over.

    Raises Mt103Error when the text has no MT103 field block, ValueError when it is too large.
    """
    if len(message) > MAX_MT_CHARS:
        raise ValueError(f"MT input exceeds the {MAX_MT_CHARS:,}-character limit.")
    normalised = message.replace("\r\n", "\n").replace("\r", "\n")
    blocks = _blocks(normalised)
    text_block = blocks.get("4", normalised if ":20:" in normalised else "")
    fields = _parse_fields(text_block)
    if not fields or not any(tag == "20" for tag, _ in fields):
        raise Mt103Error("No MT103 text block with field :20: was found.")
    values: dict[str, str] = {}
    report: list[dict[str, Any]] = []

    def note(field: str, status: str, target: str | None, detail: str) -> None:
        report.append({"field": field, "status": status, "target": target, "detail": detail})

    for tag, value in fields:
        if tag in values:
            note(tag, "unmapped", None, "Repeated field; only the first occurrence is used.")
            continue
        values[tag] = value
        if tag not in KNOWN_FIELDS:
            note(tag, "unmapped", None, "This field has no mapping in this converter; carry it over manually if needed.")

    builder = _Builder()
    transfer = builder.add(builder.root, "FIToFICstmrCdtTrf")
    header = builder.add(transfer, "GrpHdr")
    transaction_parent = transfer

    reference = values.get("20", "")
    if len(reference) > 16 or reference.startswith("/") or reference.endswith("/") or "//" in reference:
        note("20", "warning", None, "Field 20 is 16x and must not start or end with '/' or contain '//'.")
    builder.add(header, "MsgId", text=reference[:35])
    note("20", "mapped", "GrpHdr/MsgId", "Sender's reference used as message identification.")
    created = (created_at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    builder.add(header, "CreDtTm", text=created)
    builder.add(header, "NbOfTxs", text="1")
    builder.add(header, "SttlmInf", "SttlmMtd", text="INDA")
    note(
        "-",
        "defaulted",
        "GrpHdr/SttlmInf/SttlmMtd",
        "INDA (settlement by the instructed agent) is assumed; confirm with your correspondent.",
    )

    transaction = builder.add(transaction_parent, "CdtTrfTxInf")
    payment_id = builder.add(transaction, "PmtId")
    builder.add(payment_id, "InstrId", text=reference[:35])
    note("20", "mapped", "PmtId/InstrId", "Sender's reference.")

    roc = None
    for tag in ("70", "72"):
        found = re.search(r"/ROC/([^/\n]+)", values.get(tag, ""))
        if found:
            roc = found.group(1).strip()
            note(tag, "mapped", "PmtId/EndToEndId", f"/ROC/ reference {roc!r} used as end-to-end identification.")
            break
    builder.add(payment_id, "EndToEndId", text=(roc or "NOTPROVIDED")[:35])
    if roc is None:
        note("-", "defaulted", "PmtId/EndToEndId", "No /ROC/ customer reference in 70 or 72, so NOTPROVIDED is used.")

    uetr = re.search(r"\{121:([^}]*)\}", blocks.get("3", ""))
    if uetr:
        builder.add(payment_id, "UETR", text=uetr.group(1).strip())
        note("121", "mapped", "PmtId/UETR", "UETR from the user header (block 3).")
    else:
        note("121", "missing", "PmtId/UETR", "No UETR in block 3; CBPR+ requires one, so the check below reports it.")

    if values.get("23B") and values["23B"] != "CRED":
        note("23B", "unmapped", None, f"Bank operation code {values['23B']} has no direct pacs.008 element.")
    elif values.get("23B"):
        note("23B", "mapped", None, "CRED is the normal credit transfer; nothing to carry over.")

    settlement = re.fullmatch(r"(\d{2})(\d{2})(\d{2})([A-Z]{3})([\d,]+)", values.get("32A", "").replace("\n", ""))
    if settlement:
        year, month, day, currency, amount = settlement.groups()
        builder.add(transaction, "IntrBkSttlmAmt", text=_amount(amount), attrib={"Ccy": currency})
        builder.add(transaction, "IntrBkSttlmDt", text=f"20{year}-{month}-{day}")
        note("32A", "mapped", "IntrBkSttlmAmt, IntrBkSttlmDt", f"{currency} {_amount(amount)} on 20{year}-{month}-{day}.")
    else:
        note("32A", "missing", "IntrBkSttlmAmt", "Field 32A (date, currency, amount) is missing or unreadable.")

    instructed = re.fullmatch(r"([A-Z]{3})([\d,]+)", values.get("33B", "").replace("\n", ""))
    if instructed:
        builder.add(transaction, "InstdAmt", text=_amount(instructed.group(2)), attrib={"Ccy": instructed.group(1)})
        note("33B", "mapped", "InstdAmt", "Currency and instructed amount.")
    if values.get("36"):
        builder.add(transaction, "XchgRate", text=values["36"].replace(",", "."))
        note("36", "mapped", "XchgRate", "Exchange rate.")

    charges = values.get("71A")
    if charges in CHARGE_CODES:
        builder.add(transaction, "ChrgBr", text=CHARGE_CODES[charges])
        note("71A", "mapped", "ChrgBr", f"{charges} becomes {CHARGE_CODES[charges]}.")
    else:
        note("71A", "missing", "ChrgBr", f"Field 71A must be OUR, BEN or SHA; found {charges!r}.")
    for tag in ("71F", "71G"):
        found = re.fullmatch(r"([A-Z]{3})([\d,]+)", values.get(tag, "").replace("\n", ""))
        if found:
            charge = builder.add(transaction, "ChrgsInf")
            builder.add(charge, "Amt", text=_amount(found.group(2)), attrib={"Ccy": found.group(1)})
            builder.add(charge, "Agt", "FinInstnId", "Nm", text="NOTPROVIDED")
            note(
                tag,
                "defaulted",
                "ChrgsInf",
                "Charges amount carried over; the agent that took the charge is not in the MT, so NOTPROVIDED.",
            )

    sender, receiver = _header_bics(blocks)
    if sender:
        builder.add(transaction, "InstgAgt", "FinInstnId", "BICFI", text=sender)
        note("block 1/2", "mapped", "InstgAgt", f"Sender {sender}.")
    if receiver:
        builder.add(transaction, "InstdAgt", "FinInstnId", "BICFI", text=receiver)
        note("block 1/2", "mapped", "InstdAgt", f"Receiver {receiver}.")
    if values.get("56A"):
        builder.add(transaction, "IntrmyAgt1", "FinInstnId", "BICFI", text=_party_lines(values["56A"])[1][0])
        note("56A", "mapped", "IntrmyAgt1", "Intermediary institution.")

    _debtor(builder, transaction, values, note)
    _agent(builder, transaction, values, "52", "DbtrAgt", "Ordering institution", note)
    _agent(builder, transaction, values, "57", "CdtrAgt", "Account with institution", note)
    _creditor(builder, transaction, values, note)

    instructions = values.get("72", "")
    if instructions:
        creditor_agent_info, next_agent_info = [], []
        for line in instructions.split("\n"):
            target = creditor_agent_info if line.startswith("/ACC/") else next_agent_info
            content = line[5:] if line.startswith("/ACC/") else line
            if not line.startswith("/ROC/") and content:
                target.append(content)
        if creditor_agent_info:
            builder.add(transaction, "InstrForCdtrAgt", "InstrInf", text=" ".join(creditor_agent_info)[:140])
            note("72", "mapped", "InstrForCdtrAgt", "/ACC/ instruction for the creditor agent.")
        if next_agent_info:
            builder.add(transaction, "InstrForNxtAgt", "InstrInf", text=" ".join(next_agent_info)[:35])
            note("72", "mapped", "InstrForNxtAgt", "Other sender-to-receiver codes; check them, as some have dedicated pacs.008 elements.")

    if values.get("70"):
        remittance = " ".join(values["70"].split("\n"))
        builder.add(transaction, "RmtInf", "Ustrd", text=remittance[:140])
        note("70", "truncated" if len(remittance) > 140 else "mapped", "RmtInf/Ustrd", "Remittance information as unstructured text.")

    xml = builder.xml()
    check = check_cbpr_pacs008(xml)
    return {
        "kind": "mt103_conversion",
        "target_message": "pacs.008.001.08",
        "xml": xml,
        "fields": [{"tag": tag, "value": value} for tag, value in fields],
        "report": report,
        "cbpr_check": check,
        "disclaimer": DISCLAIMER,
        "sources": SOURCES,
    }


def _structured_party(builder: _Builder, party: Any, lines: list[str]) -> bool:
    """Map option F lines (1/ name, 2/ address, 3/ country/town). Returns True when structured data was found."""
    names = [line[2:] for line in lines if line.startswith("1/")]
    addresses = [line[2:] for line in lines if line.startswith("2/")]
    places = [line[2:] for line in lines if line.startswith("3/")]
    if not (names or places):
        return False
    if names:
        builder.add(party, "Nm", text=" ".join(names)[:140])
    country, _, town = places[0].partition("/") if places else ("", "", "")
    if country or town or addresses:
        address = builder.add(party, "PstlAdr")
        if town:
            builder.add(address, "TwnNm", text=town[:35])
        if country:
            builder.add(address, "Ctry", text=country[:2])
        for line in addresses[:2]:
            builder.add(address, "AdrLine", text=line[:70])
    return True


def _account(builder: _Builder, parent: Any, element: str, account: str) -> str:
    compact = account.replace(" ", "")
    if validate_iban(compact)["valid"]:
        builder.add(parent, element, "Id", "IBAN", text=compact)
        return "IBAN"
    builder.add(parent, element, "Id", "Othr", "Id", text=compact[:34])
    return "other account identification"


def _debtor(builder: _Builder, transaction: Any, values: dict[str, str], note: Any) -> None:
    tag = next((option for option in ("50F", "50K", "50A") if option in values), None)
    debtor = builder.add(transaction, "Dbtr")
    if tag is None:
        builder.add(debtor, "Nm", text="NOTPROVIDED")
        note("50a", "missing", "Dbtr", "No ordering customer (50A/F/K); NOTPROVIDED is used.")
        return
    account, lines = _party_lines(values[tag])
    if tag == "50A" and lines and BIC.fullmatch(lines[0]):
        builder.add(debtor, "Id", "OrgId", "AnyBIC", text=lines[0])
        note(tag, "mapped", "Dbtr/Id/OrgId/AnyBIC", "Ordering customer identified by BIC.")
    elif tag == "50F" and _structured_party(builder, debtor, lines):
        note(tag, "mapped", "Dbtr/Nm, Dbtr/PstlAdr", "Option F gives a name, town and country, so the address can be hybrid.")
    else:
        builder.add(debtor, "Nm", text=(lines[0] if lines else "NOTPROVIDED")[:140])
        if len(lines) > 1:
            address = builder.add(debtor, "PstlAdr")
            for line in lines[1:3]:
                builder.add(address, "AdrLine", text=line[:70])
            note(
                tag,
                "unstructured",
                "Dbtr/PstlAdr/AdrLine",
                "Free-text address lines stay unstructured; add TwnNm and Ctry to make them hybrid.",
            )
        if len(lines) > 3:
            note(tag, "truncated", "Dbtr/PstlAdr", "Only two address lines are kept (CBPR+ limit).")
    if account:
        kind = _account(builder, transaction, "DbtrAcct", account)
        note(tag, "mapped", "DbtrAcct", f"Account carried over as {kind}.")


def _creditor(builder: _Builder, transaction: Any, values: dict[str, str], note: Any) -> None:
    tag = next((option for option in ("59F", "59A", "59") if option in values), None)
    creditor = builder.add(transaction, "Cdtr")
    if tag is None:
        builder.add(creditor, "Nm", text="NOTPROVIDED")
        note("59a", "missing", "Cdtr", "No beneficiary customer (59/59A/59F); NOTPROVIDED is used.")
        return
    account, lines = _party_lines(values[tag])
    if tag == "59A" and lines and BIC.fullmatch(lines[0]):
        builder.add(creditor, "Id", "OrgId", "AnyBIC", text=lines[0])
        note(tag, "mapped", "Cdtr/Id/OrgId/AnyBIC", "Beneficiary identified by BIC.")
    elif tag == "59F" and _structured_party(builder, creditor, lines):
        note(tag, "mapped", "Cdtr/Nm, Cdtr/PstlAdr", "Option F gives a name, town and country, so the address can be hybrid.")
    else:
        builder.add(creditor, "Nm", text=(lines[0] if lines else "NOTPROVIDED")[:140])
        if len(lines) > 1:
            address = builder.add(creditor, "PstlAdr")
            for line in lines[1:3]:
                builder.add(address, "AdrLine", text=line[:70])
            note(
                tag,
                "unstructured",
                "Cdtr/PstlAdr/AdrLine",
                "Free-text address lines stay unstructured; add TwnNm and Ctry to make them hybrid.",
            )
        if len(lines) > 3:
            note(tag, "truncated", "Cdtr/PstlAdr", "Only two address lines are kept (CBPR+ limit).")
    if account:
        kind = _account(builder, transaction, "CdtrAcct", account)
        note(tag, "mapped", "CdtrAcct", f"Account carried over as {kind}.")


def _agent(builder: _Builder, transaction: Any, values: dict[str, str], prefix: str, element: str, label: str, note: Any) -> None:
    tag = next((f"{prefix}{option}" for option in ("A", "D") if f"{prefix}{option}" in values), None)
    if tag is None:
        return
    _, lines = _party_lines(values[tag])
    institution = builder.add(transaction, element, "FinInstnId")
    if tag.endswith("A") and lines and BIC.fullmatch(lines[0]):
        builder.add(institution, "BICFI", text=lines[0])
        note(tag, "mapped", f"{element}/FinInstnId/BICFI", f"{label} BIC.")
    elif lines:
        builder.add(institution, "Nm", text=lines[0][:140])
        if len(lines) > 1:
            address = builder.add(institution, "PstlAdr")
            for line in lines[1:3]:
                builder.add(address, "AdrLine", text=line[:70])
        note(tag, "unstructured", f"{element}/FinInstnId", f"{label} given by name and address; a BIC is preferred in CBPR+.")
