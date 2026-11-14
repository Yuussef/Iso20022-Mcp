from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.mt103 import MAX_MT_CHARS, Mt103Error, convert_mt103
from app.services.payment_summary import summarize_payment
from app.services.xml_safety import parse_untrusted_xml
from app.services.xml_tools import descendant, text

SAMPLES = Path(__file__).resolve().parents[1] / "examples" / "mt103"
CREATED = datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)


def sample(name: str) -> str:
    return (SAMPLES / f"{name}.txt").read_text(encoding="utf-8")


def convert(message: str) -> dict:
    return convert_mt103(message, created_at=CREATED)


def tx(result: dict):
    root = parse_untrusted_xml(result["xml"])
    return descendant(root, "FIToFICstmrCdtTrf", "CdtTrfTxInf")


def statuses(result: dict) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for item in result["report"]:
        found.setdefault(item["field"], set()).add(item["status"])
    return found


def minimal(**fields: str) -> str:
    base = {"20": "REF-1", "23B": "CRED", "32A": "261116EUR100,", "50K": "DEBTOR NAME", "59": "CREDITOR NAME", "71A": "SHA"}
    base.update(fields)
    return "{4:\n" + "\n".join(f":{tag}:{value}" for tag, value in base.items() if value) + "\n-}"


# --- Samples ----------------------------------------------------------------------------------


def test_structured_sample_converts_to_a_compliant_pacs008() -> None:
    result = convert(sample("structured-parties"))
    transaction = tx(result)

    assert result["kind"] == "mt103_conversion"
    assert result["cbpr_check"]["compliant"] is True
    assert text(descendant(transaction, "PmtId", "InstrId")) == "DEMO-REF-0001"
    assert text(descendant(transaction, "PmtId", "EndToEndId")) == "PO-2026-7781"
    assert text(descendant(transaction, "PmtId", "UETR")) == "7b1e2f3a-4c5d-4e6f-8a9b-0c1d2e3f4a5b"
    assert text(descendant(transaction, "IntrBkSttlmAmt")) == "25000.00"
    assert descendant(transaction, "IntrBkSttlmAmt").get("Ccy") == "USD"
    assert text(descendant(transaction, "IntrBkSttlmDt")) == "2026-11-16"
    assert text(descendant(transaction, "ChrgBr")) == "SHAR"
    assert text(descendant(transaction, "Dbtr", "PstlAdr", "TwnNm")) == "PARIS"
    assert text(descendant(transaction, "Dbtr", "PstlAdr", "Ctry")) == "FR"
    assert text(descendant(transaction, "DbtrAcct", "Id", "IBAN")) == "FR1420041010050500013M02606"
    assert text(descendant(transaction, "CdtrAcct", "Id", "Othr", "Id")) == "0123456789"
    assert text(descendant(transaction, "InstrForCdtrAgt", "InstrInf")) == "PLEASE ADVISE BENEFICIARY"
    assert text(descendant(transaction, "InstgAgt", "FinInstnId", "BICFI")) == "DEMOFRPPXXX"
    assert text(descendant(transaction, "InstdAgt", "FinInstnId", "BICFI")) == "DEMOUS33XXX"


def test_legacy_sample_shows_what_is_missing_for_cbpr() -> None:
    result = convert(sample("legacy-free-text"))
    found = statuses(result)

    assert found["121"] == {"missing"}
    assert found["77B"] == {"unmapped"}
    assert {"unstructured", "truncated"} <= found["50K"]
    assert "defaulted" in found["71G"]
    assert text(descendant(tx(result), "PmtId", "EndToEndId")) == "NOTPROVIDED"
    assert text(descendant(tx(result), "IntrBkSttlmAmt")) == "1500000"
    check = result["cbpr_check"]
    assert check["compliant"] is False
    rules = [finding["rule"] for transaction in check["transactions"] for finding in transaction["findings"]]
    assert rules == ["CBPR_UETR_MISSING"]


def test_draft_can_be_summarised() -> None:
    summary = summarize_payment(convert(sample("structured-parties"))["xml"])

    transaction = summary["transactions"][0]
    assert transaction["debtor"]["name"] == "ATELIER DEMO SARL"
    assert [agent["role"] for agent in transaction["agent_chain"]] == ["InstgAgt", "DbtrAgt", "InstdAgt", "CdtrAgt"]


def test_result_carries_disclaimer_and_sources() -> None:
    result = convert(sample("structured-parties"))

    assert "not a certified" in result["disclaimer"]
    assert len(result["sources"]) == 3
    assert result["xml"].startswith('<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">')


# --- Field mapping ---------------------------------------------------------------------------------


@pytest.mark.parametrize(("code", "bearer"), [("OUR", "DEBT"), ("BEN", "CRED"), ("SHA", "SHAR")])
def test_charge_codes(code: str, bearer: str) -> None:
    assert text(descendant(tx(convert(minimal(**{"71A": code}))), "ChrgBr")) == bearer


def test_invalid_charge_code_is_reported() -> None:
    result = convert(minimal(**{"71A": "XYZ"}))

    assert statuses(result)["71A"] == {"missing"}
    assert descendant(tx(result), "ChrgBr") is None


@pytest.mark.parametrize(("value", "amount"), [("261116EUR100,", "100"), ("261116EUR100,5", "100.5"), ("261116EUR0,99", "0.99")])
def test_amount_with_comma_decimal_separator(value: str, amount: str) -> None:
    assert text(descendant(tx(convert(minimal(**{"32A": value}))), "IntrBkSttlmAmt")) == amount


def test_unreadable_32a_is_reported() -> None:
    assert statuses(convert(minimal(**{"32A": "16NOV26EUR100"})))["32A"] == {"missing"}


@pytest.mark.parametrize("tag", ["70", "72"])
def test_roc_reference_becomes_end_to_end_id(tag: str) -> None:
    result = convert(minimal(**{tag: "/ROC/CUST-REF-9//MORE"}))

    assert text(descendant(tx(result), "PmtId", "EndToEndId")) == "CUST-REF-9"


def test_field_72_codes_are_split_by_recipient() -> None:
    result = convert(minimal(**{"72": "/ACC/CALL BENEFICIARY\n/INS/DEMOFRPPXXX"}))

    assert text(descendant(tx(result), "InstrForCdtrAgt", "InstrInf")) == "CALL BENEFICIARY"
    assert text(descendant(tx(result), "InstrForNxtAgt", "InstrInf")) == "/INS/DEMOFRPPXXX"


def test_long_remittance_is_truncated_and_reported() -> None:
    lines = "\n".join(["A" * 35] * 4)
    result = convert(minimal(**{"70": lines}))

    assert len(text(descendant(tx(result), "RmtInf", "Ustrd"))) == 140
    assert statuses(result)["70"] == {"truncated"}


def test_party_identified_by_bic() -> None:
    result = convert(minimal(**{"50K": "", "50A": "/FR1420041010050500013M02606\nDEMOFRPPXXX", "59": "", "59A": "DEMODEFFXXX"}))
    transaction = tx(result)

    assert text(descendant(transaction, "Dbtr", "Id", "OrgId", "AnyBIC")) == "DEMOFRPPXXX"
    assert text(descendant(transaction, "Cdtr", "Id", "OrgId", "AnyBIC")) == "DEMODEFFXXX"


def test_missing_parties_get_notprovided() -> None:
    result = convert(minimal(**{"50K": "", "59": ""}))

    assert text(descendant(tx(result), "Dbtr", "Nm")) == "NOTPROVIDED"
    assert text(descendant(tx(result), "Cdtr", "Nm")) == "NOTPROVIDED"
    assert statuses(result)["50a"] == {"missing"} and statuses(result)["59a"] == {"missing"}


def test_agents_by_name_and_address() -> None:
    result = convert(minimal(**{"52D": "SAMPLE BANK\nMAIN STREET 1\nSAMPLE CITY", "56A": "DEMOUS33XXX"}))
    transaction = tx(result)

    assert text(descendant(transaction, "DbtrAgt", "FinInstnId", "Nm")) == "SAMPLE BANK"
    assert text(descendant(transaction, "IntrmyAgt1", "FinInstnId", "BICFI")) == "DEMOUS33XXX"
    assert statuses(result)["52D"] == {"unstructured"}


def test_exchange_rate_and_instructed_amount() -> None:
    result = convert(minimal(**{"33B": "USD110,", "36": "0,9091"}))

    assert text(descendant(tx(result), "InstdAmt")) == "110"
    assert text(descendant(tx(result), "XchgRate")) == "0.9091"


def test_bad_sender_reference_is_flagged() -> None:
    assert "warning" in statuses(convert(minimal(**{"20": "/TOO-LONG-REFERENCE-123"})))["20"]


def test_output_message_headers() -> None:
    message = "{1:F01DEMOGB2LAXXX0000000000}{2:O1031200261114DEMOFRPPAXXX00000000002611141200N}{4:\n:20:R\n:32A:261116EUR1,\n:71A:SHA\n-}"

    transaction = tx(convert(message))

    assert text(descendant(transaction, "InstgAgt", "FinInstnId", "BICFI")) == "DEMOFRPPXXX"
    assert text(descendant(transaction, "InstdAgt", "FinInstnId", "BICFI")) == "DEMOGB2LXXX"


def test_text_block_without_headers_is_accepted() -> None:
    assert convert(":20:REF\n:32A:261116EUR5,\n:71A:OUR")["kind"] == "mt103_conversion"


# --- Errors -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("message", ["hello", "{4:\n:23B:CRED\n-}", ""])
def test_not_an_mt103(message: str) -> None:
    with pytest.raises(Mt103Error):
        convert(message)


def test_oversized_input() -> None:
    with pytest.raises(ValueError, match="limit"):
        convert("x" * (MAX_MT_CHARS + 1))


def test_xml_special_characters_are_escaped() -> None:
    result = convert(minimal(**{"70": "<script>&</script>"}))

    assert text(descendant(tx(result), "RmtInf", "Ustrd")) == "<script>&</script>"
    assert "&lt;script&gt;" in result["xml"]
