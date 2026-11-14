from __future__ import annotations

from pathlib import Path

import pytest

from app.services.sepa_sct import check_sepa_sct
from app.services.xml_safety import MAX_XML_CHARS

SAMPLES = Path(__file__).resolve().parents[1] / "examples" / "sepa"
NS = "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"
VALID_TX = {
    "pmt_id": "<PmtId><EndToEndId>E2E-1</EndToEndId><TxId>TX-1</TxId></PmtId>",
    "amount": '<IntrBkSttlmAmt Ccy="EUR">10.00</IntrBkSttlmAmt>',
    "charges": "<ChrgBr>SLEV</ChrgBr>",
    "debtor": "<Dbtr><Nm>Debtor Name</Nm></Dbtr>",
    "debtor_account": "<DbtrAcct><Id><IBAN>FR1420041010050500013M02606</IBAN></Id></DbtrAcct>",
    "debtor_agent": "<DbtrAgt><FinInstnId><BICFI>DEMOFRPPXXX</BICFI></FinInstnId></DbtrAgt>",
    "creditor_agent": "<CdtrAgt><FinInstnId><BICFI>DEMODEFFXXX</BICFI></FinInstnId></CdtrAgt>",
    "creditor": "<Cdtr><Nm>Creditor Name</Nm></Cdtr>",
    "creditor_account": "<CdtrAcct><Id><IBAN>DE89370400440532013000</IBAN></Id></CdtrAcct>",
    "remittance": "",
}


def sample(name: str) -> str:
    return (SAMPLES / f"{name}.xml").read_text(encoding="utf-8")


def pacs(header_extra: str = "", msg_id: str = "MSG-1", **overrides: str) -> str:
    parts = {**VALID_TX, **overrides}
    header = (
        f"<GrpHdr><MsgId>{msg_id}</MsgId><NbOfTxs>1</NbOfTxs>"
        '<TtlIntrBkSttlmAmt Ccy="EUR">10.00</TtlIntrBkSttlmAmt>'
        f"<PmtTpInf><SvcLvl><Cd>SEPA</Cd></SvcLvl></PmtTpInf>{header_extra}</GrpHdr>"
    )
    transaction = f"<CdtTrfTxInf>{''.join(parts.values())}</CdtTrfTxInf>"
    return f'<Document xmlns="{NS}"><FIToFICstmrCdtTrf>{header}{transaction}</FIToFICstmrCdtTrf></Document>'


def rules(result: dict) -> list[str]:
    return [item["rule"] for item in result["message_findings"]] + [
        item["rule"] for transaction in result["transactions"] for item in transaction["findings"]
    ]


# --- Bundled samples -------------------------------------------------------------------------


def test_valid_pacs008_sample() -> None:
    result = check_sepa_sct(sample("pacs008-valid"))

    assert result["kind"] == "sepa_sct_check"
    assert (result["message_id"], result["message_type"]) == ("pacs.008.001.08", "pacs.008")
    assert result["compliant"] is True
    assert rules(result) == []


def test_valid_pain001_sample_with_two_transactions() -> None:
    result = check_sepa_sct(sample("pain001-valid"))

    assert result["message_type"] == "pain.001"
    assert result["summary"]["transactions"] == 2
    assert result["compliant"] is True


def test_problem_sample_reports_every_planted_issue() -> None:
    result = check_sepa_sct(sample("pacs008-problems"))

    assert result["compliant"] is False
    assert set(rules(result)) == {
        "SEPA_REFERENCE_FORMAT",
        "SEPA_TOTAL_AMOUNT_MISSING",
        "SEPA_SERVICE_LEVEL",
        "SEPA_CURRENCY",
        "SEPA_AMOUNT_DECIMALS",
        "SEPA_CHARGE_BEARER",
        "SEPA_BIC_CASE",
        "SEPA_IBAN_CHECKSUM",
        "SEPA_IBAN_OUTSIDE_SEPA",
        "SEPA_CHARACTER_SET",
        "SEPA_DEBTOR_ADDRESS_REQUIRED",
        "SEPA_ADDRESS_UNSTRUCTURED",
        "SEPA_ADDRESS_TOO_MANY_LINES",
        "SEPA_REMITTANCE_BOTH",
    }
    assert result["transactions"][0]["non_eea_agent"] is True


def test_minimal_valid_pacs008() -> None:
    assert rules(check_sepa_sct(pacs())) == []


# --- Amount, charges, service level ------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "rule"),
    [
        ('<IntrBkSttlmAmt Ccy="EUR">0.00</IntrBkSttlmAmt>', "SEPA_AMOUNT_RANGE"),
        ('<IntrBkSttlmAmt Ccy="EUR">1000000000.00</IntrBkSttlmAmt>', "SEPA_AMOUNT_RANGE"),
        ('<IntrBkSttlmAmt Ccy="EUR">1.001</IntrBkSttlmAmt>', "SEPA_AMOUNT_DECIMALS"),
        ('<IntrBkSttlmAmt Ccy="GBP">10.00</IntrBkSttlmAmt>', "SEPA_CURRENCY"),
        ('<IntrBkSttlmAmt Ccy="EUR">ten</IntrBkSttlmAmt>', "SEPA_AMOUNT_FORMAT"),
        ("", "SEPA_AMOUNT_MISSING"),
    ],
)
def test_amount_rules(amount: str, rule: str) -> None:
    assert rules(check_sepa_sct(pacs(amount=amount))) == [rule]


def test_amount_limits_are_inclusive() -> None:
    assert rules(check_sepa_sct(pacs(amount='<IntrBkSttlmAmt Ccy="EUR">0.01</IntrBkSttlmAmt>'))) == []
    assert rules(check_sepa_sct(pacs(amount='<IntrBkSttlmAmt Ccy="EUR">999999999.99</IntrBkSttlmAmt>'))) == []


@pytest.mark.parametrize("charges", ["<ChrgBr>SHAR</ChrgBr>", "<ChrgBr>DEBT</ChrgBr>", ""])
def test_pacs008_charge_bearer_must_be_slev(charges: str) -> None:
    assert rules(check_sepa_sct(pacs(charges=charges))) == ["SEPA_CHARGE_BEARER"]


def test_pain001_without_charge_bearer_gets_a_recommendation_only() -> None:
    xml = sample("pain001-valid").replace("<ChrgBr>SLEV</ChrgBr>", "")

    result = check_sepa_sct(xml)

    assert set(rules(result)) == {"SEPA_CHARGE_BEARER_RECOMMENDED"}
    assert result["compliant"] is True


def test_service_level_can_come_from_the_transaction() -> None:
    xml = pacs(pmt_id=VALID_TX["pmt_id"] + "<PmtTpInf><SvcLvl><Cd>SEPA</Cd></SvcLvl></PmtTpInf>").replace(
        "<PmtTpInf><SvcLvl><Cd>SEPA</Cd></SvcLvl></PmtTpInf></GrpHdr>", "</GrpHdr>"
    )

    assert rules(check_sepa_sct(xml)) == []


def test_missing_service_level() -> None:
    xml = pacs().replace("<PmtTpInf><SvcLvl><Cd>SEPA</Cd></SvcLvl></PmtTpInf>", "")

    assert rules(check_sepa_sct(xml)) == ["SEPA_SERVICE_LEVEL_MISSING"]


# --- References and characters ----------------------------------------------------------------


@pytest.mark.parametrize("msg_id", ["/MSG", "MSG/", "MS//G", "MSG_1", "MSGé"])
def test_reference_format(msg_id: str) -> None:
    assert rules(check_sepa_sct(pacs(msg_id=msg_id))) == ["SEPA_REFERENCE_FORMAT"]


def test_non_latin_names_are_warnings_not_errors() -> None:
    result = check_sepa_sct(pacs(creditor="<Cdtr><Nm>Société Générale Démo</Nm></Cdtr>"))

    assert rules(result) == ["SEPA_CHARACTER_SET"]
    assert result["compliant"] is True


def test_name_rules() -> None:
    assert rules(check_sepa_sct(pacs(creditor=f"<Cdtr><Nm>{'x' * 71}</Nm></Cdtr>"))) == ["SEPA_NAME_TOO_LONG"]
    assert rules(check_sepa_sct(pacs(creditor="<Cdtr/>"))) == ["SEPA_NAME_MISSING"]
    assert rules(check_sepa_sct(pacs(creditor=""))) == ["SEPA_PARTY_MISSING"]


# --- Accounts and agents --------------------------------------------------------------------------


def test_account_rules() -> None:
    other = "<CdtrAcct><Id><Othr><Id>12345</Id></Othr></Id></CdtrAcct>"

    assert rules(check_sepa_sct(pacs(creditor_account=other))) == ["SEPA_ACCOUNT_NOT_IBAN"]
    assert rules(check_sepa_sct(pacs(creditor_account=""))) == ["SEPA_ACCOUNT_MISSING"]
    us_iban = "<CdtrAcct><Id><IBAN>BR6699999A03000010009795493C1</IBAN></Id></CdtrAcct>"
    assert rules(check_sepa_sct(pacs(creditor_account=us_iban))) == ["SEPA_IBAN_OUTSIDE_SEPA"]


def test_agent_rules() -> None:
    clearing = "<CdtrAgt><FinInstnId><ClrSysMmbId><MmbId>123</MmbId></ClrSysMmbId></FinInstnId></CdtrAgt>"

    assert rules(check_sepa_sct(pacs(creditor_agent=clearing))) == ["SEPA_AGENT_NOT_BIC"]
    assert rules(check_sepa_sct(pacs(creditor_agent="<CdtrAgt><FinInstnId><BICFI>DEMOUS33</BICFI></FinInstnId></CdtrAgt>"))) == [
        "SEPA_BIC_OUTSIDE_SEPA"
    ]


# --- Addresses --------------------------------------------------------------------------------------


def debtor_with(address: str) -> str:
    return f"<Dbtr><Nm>Debtor Name</Nm><PstlAdr>{address}</PstlAdr></Dbtr>"


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("<StrtNm>Rue X</StrtNm><TwnNm>Paris</TwnNm><Ctry>FR</Ctry>", []),
        ("<TwnNm>Paris</TwnNm><Ctry>FR</Ctry><AdrLine>12 Rue X</AdrLine>", []),
        ("<AdrLine>12 Rue X</AdrLine><AdrLine>Paris</AdrLine>", ["SEPA_ADDRESS_UNSTRUCTURED"]),
        ("<AdrLine>12 Rue X</AdrLine><Ctry>FR</Ctry>", ["SEPA_ADDRESS_UNSTRUCTURED"]),
        ("<StrtNm>Rue X</StrtNm><Ctry>FR</Ctry>", ["SEPA_ADDRESS_TOWN_MISSING"]),
        ("<TwnNm>Paris</TwnNm><AdrLine>12 Rue X</AdrLine>", ["SEPA_ADDRESS_COUNTRY_MISSING"]),
        ("<AdrLine>a</AdrLine><AdrLine>b</AdrLine><AdrLine>c</AdrLine>", ["SEPA_ADDRESS_UNSTRUCTURED", "SEPA_ADDRESS_TOO_MANY_LINES"]),
        (f"<TwnNm>{'x' * 36}</TwnNm><Ctry>FR</Ctry>", ["SEPA_ADDRESS_TOO_LONG"]),
    ],
)
def test_epc_address_formats(address: str, expected: list[str]) -> None:
    assert rules(check_sepa_sct(pacs(debtor=debtor_with(address)))) == expected


def test_enforcing_the_address_end_date() -> None:
    result = check_sepa_sct(pacs(debtor=debtor_with("<AdrLine>12 Rue X</AdrLine>")), enforce_unstructured_address_removal=True)

    assert result["compliant"] is False
    assert result["unstructured_address_end"]["status"] == "deferred"
    assert result["unstructured_address_end"]["enforced"] is True


def test_non_eea_agent_requires_debtor_address_and_country() -> None:
    swiss_agent = "<DbtrAgt><FinInstnId><BICFI>DEMOCHZZXXX</BICFI></FinInstnId></DbtrAgt>"

    assert rules(check_sepa_sct(pacs(debtor_agent=swiss_agent))) == ["SEPA_DEBTOR_ADDRESS_REQUIRED"]
    unstructured_no_country = debtor_with("<AdrLine>Bahnhofstrasse 1, Zurich</AdrLine>")
    assert rules(check_sepa_sct(pacs(debtor_agent=swiss_agent, debtor=unstructured_no_country))) == [
        "SEPA_ADDRESS_UNSTRUCTURED",
        "SEPA_ADDRESS_COUNTRY_REQUIRED",
    ]
    structured = debtor_with("<TwnNm>Zurich</TwnNm><Ctry>CH</Ctry>")
    assert rules(check_sepa_sct(pacs(debtor_agent=swiss_agent, debtor=structured))) == []


def test_eea_agents_do_not_require_debtor_address() -> None:
    assert check_sepa_sct(pacs())["transactions"][0]["non_eea_agent"] is False


# --- Remittance information -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("remittance", "expected"),
    [
        ("<RmtInf><Ustrd>Invoice 1</Ustrd></RmtInf>", []),
        (f"<RmtInf><Ustrd>{'x' * 140}</Ustrd></RmtInf>", []),
        (f"<RmtInf><Ustrd>{'x' * 141}</Ustrd></RmtInf>", ["SEPA_REMITTANCE_TOO_LONG"]),
        ("<RmtInf><Ustrd>a</Ustrd><Ustrd>b</Ustrd></RmtInf>", ["SEPA_REMITTANCE_REPEATED"]),
        ("<RmtInf><Ustrd>a</Ustrd><Strd><AddtlRmtInf>b</AddtlRmtInf></Strd></RmtInf>", ["SEPA_REMITTANCE_BOTH"]),
        (f"<RmtInf><Strd><AddtlRmtInf>{'x' * 120}</AddtlRmtInf></Strd></RmtInf>", ["SEPA_REMITTANCE_TOO_LONG"]),
        ("<RmtInf><Strd><AddtlRmtInf>short</AddtlRmtInf></Strd></RmtInf>", []),
    ],
)
def test_remittance_rules(remittance: str, expected: list[str]) -> None:
    assert rules(check_sepa_sct(pacs(remittance=remittance))) == expected


# --- Message handling ---------------------------------------------------------------------------


def test_other_message_versions_get_a_warning() -> None:
    xml = pacs().replace("pacs.008.001.08", "pacs.008.001.02")

    result = check_sepa_sct(xml)

    assert rules(result) == ["SEPA_MESSAGE_VERSION"]
    assert result["compliant"] is True


def test_other_messages_are_out_of_scope() -> None:
    result = check_sepa_sct('<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt/></Document>')

    assert result["in_scope"] is False
    assert result["compliant"] is False


@pytest.mark.parametrize(
    ("xml", "kind"),
    [("<Document>", "malformed_xml"), ('<!DOCTYPE D [<!ENTITY a "A">]><Document>&a;</Document>', "unsupported_xml")],
)
def test_bad_xml(xml: str, kind: str) -> None:
    result = check_sepa_sct(xml)

    assert result["kind"] == kind
    assert result["compliant"] is False


def test_oversized_input_raises() -> None:
    with pytest.raises(ValueError, match="limit"):
        check_sepa_sct("x" * (MAX_XML_CHARS + 1))


def test_results_carry_sources_and_shape() -> None:
    result = check_sepa_sct(sample("pacs008-problems"))

    assert all(url.startswith("https://www.europeanpaymentscouncil.eu/") for url in result["sources"])
    for transaction in result["transactions"]:
        for item in transaction["findings"]:
            assert set(item) == {"rule", "severity", "message", "xpath", "suggestion"}
            assert item["severity"] in {"error", "warning", "info"}
