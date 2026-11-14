from __future__ import annotations

from pathlib import Path

import pytest

from app.services.postal_address import check_postal_addresses
from app.services.xml_safety import MAX_XML_CHARS

SAMPLES = Path(__file__).resolve().parents[1] / "examples" / "postal-address"
NS = "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"


def sample(name: str) -> str:
    return (SAMPLES / f"{name}.xml").read_text(encoding="utf-8")


def message(body: str, namespace: str = NS) -> str:
    return f'<Document xmlns="{namespace}"><FIToFICstmrCdtTrf><CdtTrfTxInf>{body}</CdtTrfTxInf></FIToFICstmrCdtTrf></Document>'


def party(role: str, address: str) -> str:
    return f"<{role}><Nm>Demo</Nm><PstlAdr>{address}</PstlAdr></{role}>"


def rules(result: dict) -> list[tuple[str, str]]:
    return [(finding["rule"], finding["severity"]) for address in result["addresses"] for finding in address["findings"]]


# --- Bundled samples -------------------------------------------------------------------


def test_structured_sample_is_compliant() -> None:
    result = check_postal_addresses(sample("structured"))

    assert result["kind"] == "postal_address_check"
    assert result["message_id"] == "pacs.008.001.08"
    assert result["compliant"] is True
    assert result["summary"] == {"addresses": 2, "structured": 2, "hybrid": 0, "unstructured": 0, "errors": 0, "warnings": 0}
    assert [(a["role"], a["role_label"]) for a in result["addresses"]] == [("Dbtr", "Debtor"), ("Cdtr", "Creditor")]


def test_hybrid_sample_is_compliant_with_one_duplication_warning() -> None:
    result = check_postal_addresses(sample("hybrid"))

    assert result["compliant"] is True
    assert result["summary"]["hybrid"] == 2
    assert rules(result) == [("CBPR_ADDR_DUPLICATED_IN_LINE", "warning")]


def test_problems_sample_reports_every_issue() -> None:
    result = check_postal_addresses(sample("problems"))

    assert result["compliant"] is False
    by_role = {address["role"]: [f["rule"] for f in address["findings"]] for address in result["addresses"]}
    assert by_role == {
        "Dbtr": ["CBPR_ADDR_UNSTRUCTURED"],
        "CdtrAgt": ["CBPR_ADDR_UNSTRUCTURED", "CBPR_ADDR_AGENT_HAS_BIC"],
        "Cdtr": ["CBPR_ADDR_COUNTRY_FORMAT", "CBPR_ADDR_POSTCODE_IN_TOWN"],
        "UltmtCdtr": ["CBPR_ADDR_COUNTRY_MISSING", "CBPR_ADDR_TOO_MANY_LINES"],
    }


# --- Classification and the deferred removal -------------------------------------------------


def test_unstructured_is_a_warning_while_removal_is_deferred() -> None:
    result = check_postal_addresses(message(party("Dbtr", "<AdrLine>1 Main St</AdrLine><AdrLine>Paris</AdrLine>")))

    address = result["addresses"][0]
    assert address["format"] == "unstructured"
    assert rules(result) == [("CBPR_ADDR_UNSTRUCTURED", "warning")]
    assert result["compliant"] is True
    assert result["unstructured_removal"]["status"] == "deferred"
    assert result["unstructured_removal"]["originally_planned"] == "2026-11-14"
    assert result["unstructured_removal"]["enforced"] is False


def test_enforcing_removal_turns_unstructured_into_an_error() -> None:
    result = check_postal_addresses(message(party("Dbtr", "<AdrLine>1 Main St, Paris</AdrLine>")), enforce_unstructured_removal=True)

    assert rules(result) == [("CBPR_ADDR_UNSTRUCTURED", "error")]
    assert result["compliant"] is False
    assert result["unstructured_removal"]["enforced"] is True


def test_unstructured_party_suggestion_explains_hybrid_option() -> None:
    result = check_postal_addresses(message(party("Cdtr", "<AdrLine>1 Main St</AdrLine>")))

    assert "<TwnNm>" in result["addresses"][0]["findings"][0]["suggestion"]


def test_agent_with_bic_is_told_the_address_can_go() -> None:
    xml = message(
        "<CdtrAgt><FinInstnId><BICFI>DEMODEFFXXX</BICFI>"
        "<PstlAdr><AdrLine>Bankstrasse 1</AdrLine></PstlAdr></FinInstnId></CdtrAgt>"
    )

    address = check_postal_addresses(xml)["addresses"][0]

    assert address["role"] == "CdtrAgt"
    assert address["role_label"] == "Creditor agent"
    assert address["agent_bic"] == "DEMODEFFXXX"
    assert "BIC DEMODEFFXXX alone" in address["findings"][0]["suggestion"]
    assert address["findings"][1]["rule"] == "CBPR_ADDR_AGENT_HAS_BIC"


def test_agent_without_bic_has_no_bic_hint() -> None:
    xml = message("<IntrmyAgt1><FinInstnId><Nm>Bank</Nm><PstlAdr><TwnNm>Paris</TwnNm><Ctry>FR</Ctry></PstlAdr></FinInstnId></IntrmyAgt1>")

    result = check_postal_addresses(xml)

    assert result["addresses"][0]["agent_bic"] is None
    assert rules(result) == []


# --- Mandatory elements, limits and formats ---------------------------------------------------


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("<StrtNm>Main St</StrtNm><Ctry>FR</Ctry>", ["CBPR_ADDR_TOWN_MISSING"]),
        ("<TwnNm>Paris</TwnNm>", ["CBPR_ADDR_COUNTRY_MISSING"]),
        ("", ["CBPR_ADDR_TOWN_MISSING", "CBPR_ADDR_COUNTRY_MISSING"]),
        ("<TwnNm> </TwnNm><Ctry>FR</Ctry>", ["CBPR_ADDR_TOWN_MISSING"]),
        ("<TwnNm>Paris</TwnNm><AdrLine>1 Main St</AdrLine>", ["CBPR_ADDR_COUNTRY_MISSING"]),
    ],
)
def test_town_and_country_are_mandatory_in_structured_and_hybrid(address: str, expected: list[str]) -> None:
    result = check_postal_addresses(message(party("Dbtr", address)))

    assert [rule for rule, _ in rules(result)] == expected
    assert result["compliant"] is False


def test_hybrid_allows_two_lines_but_not_three() -> None:
    two = "<TwnNm>Paris</TwnNm><Ctry>FR</Ctry><AdrLine>a</AdrLine><AdrLine>b</AdrLine>"
    three = two + "<AdrLine>c</AdrLine>"

    assert rules(check_postal_addresses(message(party("Dbtr", two)))) == []
    assert rules(check_postal_addresses(message(party("Dbtr", three)))) == [("CBPR_ADDR_TOO_MANY_LINES", "error")]


@pytest.mark.parametrize(("element", "limit"), [("TwnNm", 35), ("PstCd", 16), ("StrtNm", 70), ("BldgNb", 16)])
def test_structured_element_length_limits(element: str, limit: int) -> None:
    def build(length: int) -> str:
        values = {"TwnNm": "Paris", element: "x" * length}
        parts = "".join(f"<{name}>{value}</{name}>" for name, value in values.items())
        return message(party("Dbtr", parts + "<Ctry>FR</Ctry>"))

    assert rules(check_postal_addresses(build(limit))) == []
    finding = check_postal_addresses(build(limit + 1))["addresses"][0]["findings"][0]
    assert finding["rule"] == "CBPR_ADDR_TOO_LONG"
    assert finding["xpath"].endswith(f"/PstlAdr/{element}")


def test_address_line_length_limit() -> None:
    xml = message(party("Dbtr", f"<TwnNm>Paris</TwnNm><Ctry>FR</Ctry><AdrLine>{'x' * 71}</AdrLine>"))

    assert rules(check_postal_addresses(xml)) == [("CBPR_ADDR_TOO_LONG", "error")]


@pytest.mark.parametrize("country", ["fr", "FRA", "France", "F1"])
def test_country_must_be_two_upper_case_letters(country: str) -> None:
    xml = message(party("Dbtr", f"<TwnNm>Paris</TwnNm><Ctry>{country}</Ctry>"))

    assert rules(check_postal_addresses(xml)) == [("CBPR_ADDR_COUNTRY_FORMAT", "error")]


def test_post_code_inside_town_name_is_flagged() -> None:
    xml = message(party("Dbtr", "<TwnNm>75001 Paris</TwnNm><Ctry>FR</Ctry>"))

    finding = check_postal_addresses(xml)["addresses"][0]["findings"][0]
    assert (finding["rule"], finding["severity"]) == ("CBPR_ADDR_POSTCODE_IN_TOWN", "warning")
    assert "<PstCd>" in finding["suggestion"]


def test_town_duplication_matches_whole_words_only() -> None:
    duplicated = "<TwnNm>Nice</TwnNm><Ctry>FR</Ctry><AdrLine>3 Rue X, NICE</AdrLine>"
    not_duplicated = "<TwnNm>Nice</TwnNm><Ctry>FR</Ctry><AdrLine>Niceville Building</AdrLine>"

    assert rules(check_postal_addresses(message(party("Dbtr", duplicated)))) == [("CBPR_ADDR_DUPLICATED_IN_LINE", "warning")]
    assert rules(check_postal_addresses(message(party("Dbtr", not_duplicated)))) == []


# --- Message handling ------------------------------------------------------------------------


def test_xpaths_index_repeated_transactions() -> None:
    tx = party("Dbtr", "<TwnNm>Paris</TwnNm><Ctry>FR</Ctry>")
    transactions = f"<CdtTrfTxInf>{tx}</CdtTrfTxInf>" * 2
    xml = f'<Document xmlns="{NS}"><FIToFICstmrCdtTrf>{transactions}</FIToFICstmrCdtTrf></Document>'

    paths = [address["xpath"] for address in check_postal_addresses(xml)["addresses"]]

    assert paths == [
        "/Document/FIToFICstmrCdtTrf/CdtTrfTxInf[1]/Dbtr/PstlAdr",
        "/Document/FIToFICstmrCdtTrf/CdtTrfTxInf[2]/Dbtr/PstlAdr",
    ]


def test_message_id_is_read_past_a_business_application_header() -> None:
    xml = (
        "<Envelope>"
        '<AppHdr xmlns="urn:iso:std:iso:20022:tech:xsd:head.001.001.02"><MsgDefIdr>pacs.008.001.08</MsgDefIdr></AppHdr>'
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.009.001.08"><X/></Document>'
        "</Envelope>"
    )

    assert check_postal_addresses(xml)["message_id"] == "pacs.009.001.08"


@pytest.mark.parametrize("message_id", ["camt.053.001.08", "camt.054.001.08", "admi.024.001.01"])
def test_reporting_messages_are_out_of_scope(message_id: str) -> None:
    xml = message(party("Dbtr", "<AdrLine>1 Main St</AdrLine>"), namespace=f"urn:iso:std:iso:20022:tech:xsd:{message_id}")

    result = check_postal_addresses(xml, enforce_unstructured_removal=True)

    assert result["in_scope"] is False
    assert result["addresses"] == []
    assert result["compliant"] is True


def test_message_without_addresses_is_compliant() -> None:
    result = check_postal_addresses(message("<DbtrAgt><FinInstnId><BICFI>DEMOFRPPXXX</BICFI></FinInstnId></DbtrAgt>"))

    assert result["summary"]["addresses"] == 0
    assert result["compliant"] is True


def test_unknown_namespace_is_still_checked() -> None:
    result = check_postal_addresses("<Doc><Dbtr><PstlAdr><TwnNm>Paris</TwnNm></PstlAdr></Dbtr></Doc>")

    assert result["message_id"] is None
    assert rules(result) == [("CBPR_ADDR_COUNTRY_MISSING", "error")]


@pytest.mark.parametrize(
    ("xml", "kind", "code"),
    [
        ("<Document><Dbtr>", "malformed_xml", "XML_SYNTAX_ERROR"),
        (
            '<!DOCTYPE D [<!ENTITY a "A">]><Document><Dbtr><PstlAdr><TwnNm>&a;</TwnNm></PstlAdr></Dbtr></Document>',
            "unsupported_xml",
            "DTD_NOT_ALLOWED",
        ),
    ],
)
def test_unsafe_or_broken_xml_is_rejected(xml: str, kind: str, code: str) -> None:
    result = check_postal_addresses(xml)

    assert result["kind"] == kind
    assert result["errors"][0]["code"] == code
    assert result["compliant"] is False
    assert result["addresses"] == []


def test_oversized_input_raises() -> None:
    with pytest.raises(ValueError, match="limit"):
        check_postal_addresses("x" * (MAX_XML_CHARS + 1))


def test_every_finding_has_the_documented_shape() -> None:
    result = check_postal_addresses(sample("problems"))

    for address in result["addresses"]:
        assert set(address) == {"role", "role_label", "xpath", "format", "agent_bic", "findings"}
        for finding in address["findings"]:
            assert set(finding) == {"rule", "severity", "message", "xpath", "suggestion"}
            assert finding["severity"] in {"error", "warning", "info"}
            assert finding["xpath"].startswith("/Document/")
    assert all(url.startswith("https://") for url in result["sources"])
