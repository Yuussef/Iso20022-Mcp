from __future__ import annotations

from pathlib import Path

import pytest

from app.services.payment_summary import summarize_payment

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def read(name: str) -> str:
    return (EXAMPLES / name).read_text(encoding="utf-8")


def test_pacs008_summary() -> None:
    result = summarize_payment(read("cbpr/pacs008-valid.xml"))
    transaction = result["transactions"][0]

    assert (result["kind"], result["message_id"], result["message_type"]) == ("payment_summary", "pacs.008.001.08", "pacs.008")
    assert result["group"] == {
        "message_identification": "DEMO-CBPR-0001",
        "created": "2026-11-14T10:00:00+00:00",
        "number_of_transactions": "1",
    }
    assert transaction["uetr"] == "3f2b8c4e-9a1d-4e7b-8c2f-5d6a7b8c9d0e"
    assert transaction["interbank_settlement_amount"] == {"currency": "USD", "value": "25000.00"}
    assert transaction["settlement_date"] == "2026-11-16"
    assert transaction["charge_bearer"] == "SHAR"
    assert transaction["purpose"] == "GDDS"
    assert transaction["debtor"]["name"] == "Atelier Demo SARL"
    assert transaction["debtor"]["address"] == "Rue de la Demo, 12, 75001, Paris, FR"
    assert transaction["debtor_account"] == "FR1420041010050500013M02606"
    assert transaction["creditor_account"] == "0123456789"
    assert transaction["creditor"]["address"] == "Singapore, 10 Sample Road, 05-01, SG"
    assert [agent["role"] for agent in transaction["agent_chain"]] == ["InstgAgt", "DbtrAgt", "IntrmyAgt1", "InstdAgt", "CdtrAgt"]
    assert transaction["agent_chain"][-1]["bic"] == "DEMOSGSGXXX"
    assert transaction["remittance"] == {"unstructured": ["Invoice INV-2026-311"], "references": []}


def test_pain001_summary_uses_payment_information_level() -> None:
    result = summarize_payment(read("sepa/pain001-valid.xml"))

    assert result["message_type"] == "pain.001"
    assert len(result["transactions"]) == 2
    first = result["transactions"][0]
    assert first["debtor"]["name"] == "Atelier Demo SARL"
    assert first["debtor_account"] == "FR1420041010050500013M02606"
    assert first["instructed_amount"] == {"currency": "EUR", "value": "980.00"}
    assert first["charge_bearer"] == "SLEV"
    assert first["service_level"] == "SEPA"
    assert first["requested_execution_date"] == "2026-11-16"
    assert [agent["role"] for agent in first["agent_chain"]] == ["DbtrAgt"]


def test_structured_remittance_references() -> None:
    result = summarize_payment(read("sepa/pacs008-problems.xml"))

    assert result["transactions"][0]["remittance"]["references"] == ["RF18539007547034"]


def test_unknown_message_has_no_transactions() -> None:
    result = summarize_payment("<Document><Other/></Document>")

    assert result["message_type"] is None
    assert result["transactions"] == []


@pytest.mark.parametrize(("xml", "kind"), [("<Doc>", "malformed_xml"), ('<!DOCTYPE D [<!ENTITY a "A">]><D>&a;</D>', "unsupported_xml")])
def test_bad_xml(xml: str, kind: str) -> None:
    assert summarize_payment(xml)["kind"] == kind
