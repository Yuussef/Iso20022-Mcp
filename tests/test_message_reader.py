from __future__ import annotations

from pathlib import Path

import pytest

from app.services.message_reader import MESSAGE_NAMES, read_message

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def read(name: str) -> dict:
    return read_message((EXAMPLES / name).read_text(encoding="utf-8"))


def test_statement() -> None:
    result = read("read/camt053-statement.xml")

    assert (result["message_id"], result["message_name"]) == ("camt.053.001.08", "BankToCustomerStatement")
    assert result["recognised"] is True
    assert result["entries"]["count"] == 3
    assert result["entries"]["totals"] == {"EUR": {"credits": "500.00", "debits": "1750.50"}}
    first = result["entries"]["items"][0]
    assert (first["credit_debit"], first["amount"], first["status"], first["booking_date"]) == ("DBIT", "1250.50", "BOOK", "2026-11-16")
    assert first["end_to_end_ids"] == ["INVOICE-2026-0042"]
    assert [balance["type"] for balance in result["balances"]] == ["OPBD", "CLBD"]
    assert result["ibans"] == ["FR1420041010050500013M02606"]
    assert result["suggested_tools"] == []  # statements are out of scope for the address rules


def test_status_report_codes_are_explained() -> None:
    result = read("status/pacs002-cbpr-reject.xml")

    assert result["message_name"] == "FIToFIPaymentStatusReport"
    assert result["references"]["uetr"] == ["3f2b8c4e-9a1d-4e7b-8c2f-5d6a7b8c9d0e"]
    codes = {code["code"]: code for code in result["codes"]}
    assert codes["RJCT"]["code_set"] == "ExternalPaymentTransactionStatus1Code"
    assert codes["AC04"]["code_set"] == "ExternalStatusReason1Code"
    assert codes["AC04"]["meaning"].startswith("Account number specified has been closed")
    assert result["suggested_tools"] == ["explain_payment_status"]


def test_return_reason_uses_the_return_code_set() -> None:
    codes = read("status/pacs004-sepa-return.xml")["codes"]

    assert codes == [
        {
            "element": "Cd",
            "code": "AC04",
            "code_set": "ExternalReturnReason1Code",
            "meaning": "Account number specified has been closed on the bank of account's books",
            "xpath": "/Document/PmtRtr/TxInf/RtrRsnInf/Rsn/Cd",
        }
    ]


def test_payment_parties_agents_and_tools() -> None:
    result = read("cbpr/pacs008-valid.xml")

    assert [(party["role"], party["name"]) for party in result["parties"]] == [
        ("Dbtr", "Atelier Demo SARL"),
        ("Cdtr", "Example Trading Pte Ltd"),
    ]
    assert ("CdtrAgt", "DEMOSGSGXXX") in [(agent["role"], agent["bic"]) for agent in result["agents"]]
    assert result["suggested_tools"] == ["check_cbpr_pacs008", "check_sepa_sct", "summarize_payment", "check_cbpr_postal_addresses"]
    assert result["outline"]["name"] == "FIToFICstmrCdtTrf"


def test_business_application_header() -> None:
    xml = (
        "<Envelope>"
        '<AppHdr xmlns="urn:iso:std:iso:20022:tech:xsd:head.001.001.02">'
        "<Fr><FIId><FinInstnId><BICFI>DEMOFRPPXXX</BICFI></FinInstnId></FIId></Fr>"
        "<To><FIId><FinInstnId><BICFI>DEMOUS33XXX</BICFI></FinInstnId></FIId></To><BizMsgIdr>B1</BizMsgIdr>"
        "<MsgDefIdr>pacs.009.001.08</MsgDefIdr><BizSvc>swift.cbprplus.02</BizSvc></AppHdr>"
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.009.001.08"><FICdtTrf><GrpHdr><MsgId>M</MsgId></GrpHdr></FICdtTrf></Document>'
        "</Envelope>"
    )

    result = read_message(xml)

    assert result["message_id"] == "pacs.009.001.08"
    assert result["message_name"] == "FinancialInstitutionCreditTransfer"
    assert result["business_header"]["from"] == "DEMOFRPPXXX"
    assert result["business_header"]["business_service"] == "swift.cbprplus.02"


def test_unknown_message_still_described() -> None:
    result = read_message(
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:sese.023.001.09">'
        "<SctiesSttlmTxInstr><TxId>T</TxId></SctiesSttlmTxInstr></Document>"
    )

    assert result["recognised"] is False
    assert result["message_name"] == "SctiesSttlmTxInstr"
    assert result["outline"]["children"] == [{"name": "TxId"}]


def test_known_names_are_well_formed() -> None:
    assert all(len(key) == 8 and key[4] == "." for key in MESSAGE_NAMES)


@pytest.mark.parametrize(("xml", "kind"), [("<Doc>", "malformed_xml"), ('<!DOCTYPE D [<!ENTITY a "A">]><D>&a;</D>', "unsupported_xml")])
def test_bad_xml(xml: str, kind: str) -> None:
    assert read_message(xml)["kind"] == kind
