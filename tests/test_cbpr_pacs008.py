from __future__ import annotations

from pathlib import Path

import pytest

from app.services.cbpr_pacs008 import check_cbpr_pacs008, iso4217
from app.services.xml_safety import MAX_XML_CHARS

SAMPLES = Path(__file__).resolve().parents[1] / "examples" / "cbpr"
NS = "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"
UETR = "3f2b8c4e-9a1d-4e7b-8c2f-5d6a7b8c9d0e"
PARTS = {
    "pmt_id": f"<PmtId><EndToEndId>E2E-1</EndToEndId><UETR>{UETR}</UETR></PmtId>",
    "amount": '<IntrBkSttlmAmt Ccy="USD">100.00</IntrBkSttlmAmt>',
    "instructed": "",
    "charges": "<ChrgBr>SHAR</ChrgBr>",
    "charges_info": "",
    "debtor": "<Dbtr><Nm>Debtor</Nm></Dbtr>",
    "debtor_agent": "<DbtrAgt><FinInstnId><BICFI>DEMOFRPPXXX</BICFI></FinInstnId></DbtrAgt>",
    "creditor_agent": "<CdtrAgt><FinInstnId><BICFI>DEMOUS33XXX</BICFI></FinInstnId></CdtrAgt>",
    "creditor": "<Cdtr><Nm>Creditor</Nm></Cdtr>",
    "creditor_account": "",
}


def sample(name: str) -> str:
    return (SAMPLES / f"{name}.xml").read_text(encoding="utf-8")


def pacs(transactions: int = 1, nb_of_txs: str = "1", **overrides: str) -> str:
    body = "".join({**PARTS, **overrides}.values())
    header = f"<GrpHdr><MsgId>M1</MsgId><NbOfTxs>{nb_of_txs}</NbOfTxs></GrpHdr>"
    txs = f"<CdtTrfTxInf>{body}</CdtTrfTxInf>" * transactions
    return f'<Document xmlns="{NS}"><FIToFICstmrCdtTrf>{header}{txs}</FIToFICstmrCdtTrf></Document>'


def rules(result: dict) -> list[str]:
    found = [item["rule"] for item in result["message_findings"]]
    found += [item["rule"] for transaction in result["transactions"] for item in transaction["findings"]]
    found += [item["rule"] for address in (result["postal_addresses"] or {}).get("addresses", []) for item in address["findings"]]
    return found


# --- Reference data --------------------------------------------------------------------------


def test_iso4217_reference_data() -> None:
    data = iso4217()

    assert data["published"] == "2026-09-17"
    assert len(data["currencies"]) == 178
    assert data["currencies"]["JPY"]["minor_units"] == 0
    assert data["currencies"]["KWD"]["minor_units"] == 3
    assert data["currencies"]["EUR"]["minor_units"] == 2
    assert data["currencies"]["XAU"]["minor_units"] is None


# --- Samples -----------------------------------------------------------------------------------


def test_valid_sample() -> None:
    result = check_cbpr_pacs008(sample("pacs008-valid"))

    assert result["kind"] == "cbpr_pacs008_check"
    assert result["compliant"] is True
    assert rules(result) == []
    assert result["transactions"][0]["uetr"] == UETR


def test_problem_sample() -> None:
    result = check_cbpr_pacs008(sample("pacs008-problems"))

    assert result["compliant"] is False
    assert set(rules(result)) == {
        "CBPR_SINGLE_TRANSACTION",
        "CBPR_CHARACTER_SET",
        "CBPR_UETR_FORMAT",
        "CBPR_CURRENCY_DECIMALS",
        "CBPR_CHARGES_INFO_REQUIRED",
        "CBPR_IBAN_CHECKSUM",
        "CBPR_UETR_MISSING",
        "CBPR_CHARGE_BEARER",
        "CBPR_ADDR_UNSTRUCTURED",
        "CBPR_ADDR_POSTCODE_IN_TOWN",
    }


def test_minimal_valid_message() -> None:
    assert rules(check_cbpr_pacs008(pacs())) == []


# --- Single transaction and UETR -----------------------------------------------------------------


@pytest.mark.parametrize(("transactions", "nb_of_txs"), [(2, "2"), (1, "2"), (2, "1")])
def test_exactly_one_transaction(transactions: int, nb_of_txs: str) -> None:
    assert "CBPR_SINGLE_TRANSACTION" in rules(check_cbpr_pacs008(pacs(transactions, nb_of_txs)))


@pytest.mark.parametrize(
    ("uetr", "rule"),
    [
        ("", "CBPR_UETR_MISSING"),
        ("3F2B8C4E-9A1D-4E7B-8C2F-5D6A7B8C9D0E", "CBPR_UETR_FORMAT"),
        ("3f2b8c4e-9a1d-1e7b-8c2f-5d6a7b8c9d0e", "CBPR_UETR_FORMAT"),
        ("3f2b8c4e-9a1d-4e7b-7c2f-5d6a7b8c9d0e", "CBPR_UETR_FORMAT"),
        ("not-a-uuid", "CBPR_UETR_FORMAT"),
    ],
)
def test_uetr_rules(uetr: str, rule: str) -> None:
    pmt_id = f"<PmtId><EndToEndId>E2E-1</EndToEndId>{f'<UETR>{uetr}</UETR>' if uetr else ''}</PmtId>"

    assert rules(check_cbpr_pacs008(pacs(pmt_id=pmt_id))) == [rule]


# --- Charges ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("bearer", ["DEBT", "SHAR"])
def test_allowed_charge_bearers(bearer: str) -> None:
    assert rules(check_cbpr_pacs008(pacs(charges=f"<ChrgBr>{bearer}</ChrgBr>"))) == []


def test_slev_is_explained() -> None:
    result = check_cbpr_pacs008(pacs(charges="<ChrgBr>SLEV</ChrgBr>"))
    finding = result["transactions"][0]["findings"][0]

    assert finding["rule"] == "CBPR_CHARGE_BEARER"
    assert "SEPA" in finding["suggestion"]


def test_missing_charge_bearer() -> None:
    assert rules(check_cbpr_pacs008(pacs(charges=""))) == ["CBPR_CHARGE_BEARER"]


def test_cred_needs_charges_information() -> None:
    charges_info = '<ChrgsInf><Amt Ccy="USD">5.00</Amt><Agt><FinInstnId><BICFI>DEMOUS33XXX</BICFI></FinInstnId></Agt></ChrgsInf>'

    assert rules(check_cbpr_pacs008(pacs(charges="<ChrgBr>CRED</ChrgBr>"))) == ["CBPR_CHARGES_INFO_REQUIRED"]
    assert rules(check_cbpr_pacs008(pacs(charges="<ChrgBr>CRED</ChrgBr>", charges_info=charges_info))) == []


def test_shar_with_deduction_needs_charges_information() -> None:
    deducted = pacs(amount='<IntrBkSttlmAmt Ccy="USD">95.00</IntrBkSttlmAmt>', instructed='<InstdAmt Ccy="USD">100.00</InstdAmt>')

    assert rules(check_cbpr_pacs008(deducted)) == ["CBPR_CHARGES_INFO_REQUIRED"]


def test_debt_with_prepaid_charges_needs_charges_information() -> None:
    prepaid = pacs(
        charges="<ChrgBr>DEBT</ChrgBr>",
        amount='<IntrBkSttlmAmt Ccy="USD">105.00</IntrBkSttlmAmt>',
        instructed='<InstdAmt Ccy="USD">100.00</InstdAmt>',
    )

    assert rules(check_cbpr_pacs008(prepaid)) == ["CBPR_CHARGES_INFO_REQUIRED"]


def test_different_currencies_are_not_compared() -> None:
    fx = pacs(amount='<IntrBkSttlmAmt Ccy="USD">95.00</IntrBkSttlmAmt>', instructed='<InstdAmt Ccy="EUR">100.00</InstdAmt>')

    assert rules(check_cbpr_pacs008(fx)) == []


# --- Currencies and amounts ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ('<IntrBkSttlmAmt Ccy="JPY">1500</IntrBkSttlmAmt>', []),
        ('<IntrBkSttlmAmt Ccy="JPY">1500.5</IntrBkSttlmAmt>', ["CBPR_CURRENCY_DECIMALS"]),
        ('<IntrBkSttlmAmt Ccy="KWD">10.125</IntrBkSttlmAmt>', []),
        ('<IntrBkSttlmAmt Ccy="KWD">10.1255</IntrBkSttlmAmt>', ["CBPR_CURRENCY_DECIMALS"]),
        ('<IntrBkSttlmAmt Ccy="USD">10.001</IntrBkSttlmAmt>', ["CBPR_CURRENCY_DECIMALS"]),
        ('<IntrBkSttlmAmt Ccy="ABC">10.00</IntrBkSttlmAmt>', ["CBPR_CURRENCY_UNKNOWN"]),
        ('<IntrBkSttlmAmt Ccy="USD">0</IntrBkSttlmAmt>', ["CBPR_AMOUNT_NOT_POSITIVE"]),
        ('<IntrBkSttlmAmt Ccy="USD">ten</IntrBkSttlmAmt>', ["CBPR_AMOUNT_FORMAT"]),
        ("", ["CBPR_AMOUNT_MISSING"]),
    ],
)
def test_currency_rules(amount: str, expected: list[str]) -> None:
    assert rules(check_cbpr_pacs008(pacs(amount=amount))) == expected


def test_charges_amount_decimals_are_checked() -> None:
    charges_info = '<ChrgsInf><Amt Ccy="JPY">500.5</Amt></ChrgsInf>'

    assert rules(check_cbpr_pacs008(pacs(charges="<ChrgBr>CRED</ChrgBr>", charges_info=charges_info))) == ["CBPR_CURRENCY_DECIMALS"]


# --- Identifiers, characters, addresses ------------------------------------------------------------


def test_identifiers_are_validated() -> None:
    bad_iban = "<CdtrAcct><Id><IBAN>DE89370400440532013001</IBAN></Id></CdtrAcct>"
    bad_bic = "<CdtrAgt><FinInstnId><BICFI>DEMO1S33</BICFI></FinInstnId></CdtrAgt>"

    assert rules(check_cbpr_pacs008(pacs(creditor_account=bad_iban))) == ["CBPR_IBAN_CHECKSUM"]
    assert rules(check_cbpr_pacs008(pacs(creditor_agent=bad_bic))) == ["CBPR_BIC_FORMAT"]


def test_character_set_is_a_warning() -> None:
    result = check_cbpr_pacs008(pacs(creditor="<Cdtr><Nm>Ünïcödé GmbH</Nm></Cdtr>"))

    assert rules(result) == ["CBPR_CHARACTER_SET"]
    assert result["compliant"] is True


def test_cbpr_extended_characters_are_allowed() -> None:
    assert rules(check_cbpr_pacs008(pacs(creditor="<Cdtr><Nm>A&amp;B Trading #1 @ Co. [UK]</Nm></Cdtr>"))) == []


def test_address_findings_are_included_and_enforceable() -> None:
    xml = pacs(debtor="<Dbtr><Nm>Debtor</Nm><PstlAdr><AdrLine>1 Main St, Paris</AdrLine></PstlAdr></Dbtr>")

    relaxed = check_cbpr_pacs008(xml)
    enforced = check_cbpr_pacs008(xml, enforce_unstructured_removal=True)

    assert rules(relaxed) == ["CBPR_ADDR_UNSTRUCTURED"]
    assert relaxed["compliant"] is True
    assert enforced["compliant"] is False
    assert enforced["summary"]["address_errors"] == 1


# --- Message handling ----------------------------------------------------------------------------------


def test_other_versions_get_a_warning() -> None:
    assert rules(check_cbpr_pacs008(pacs().replace("pacs.008.001.08", "pacs.008.001.10"))) == ["CBPR_MESSAGE_VERSION"]


def test_other_messages_are_out_of_scope() -> None:
    result = check_cbpr_pacs008('<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"><CstmrCdtTrfInitn/></Document>')

    assert result["in_scope"] is False
    assert result["compliant"] is False
    assert result["postal_addresses"] is None


@pytest.mark.parametrize(("xml", "kind"), [("<Doc>", "malformed_xml"), ('<!DOCTYPE D [<!ENTITY a "A">]><D>&a;</D>', "unsupported_xml")])
def test_bad_xml(xml: str, kind: str) -> None:
    assert check_cbpr_pacs008(xml)["kind"] == kind


def test_oversized_input_raises() -> None:
    with pytest.raises(ValueError, match="limit"):
        check_cbpr_pacs008("x" * (MAX_XML_CHARS + 1))
