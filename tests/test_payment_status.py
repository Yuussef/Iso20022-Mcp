from __future__ import annotations

from pathlib import Path

import pytest

from app.services.payment_status import epc_codes, explain_payment_status, iso_codes
from app.services.xml_safety import MAX_XML_CHARS

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
NS002 = "urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10"
NS004 = "urn:iso:std:iso:20022:tech:xsd:pacs.004.001.09"
SEPA_REF = "<OrgnlTxRef><PmtTpInf><SvcLvl><Cd>SEPA</Cd></SvcLvl></PmtTpInf></OrgnlTxRef>"
ORIGINATOR = "<Orgtr><Id><OrgId><AnyBIC>DEMODEFFXXX</AnyBIC></OrgId></Id></Orgtr>"


def read(name: str) -> str:
    return (EXAMPLES / name).read_text(encoding="utf-8")


def rules(result: dict) -> list[str]:
    found = [item["rule"] for item in result["message_findings"]]
    return found + [item["rule"] for transaction in result["transactions"] for item in transaction["findings"]]


def pacs002(tx: str, group: str = "<OrgnlMsgId>M1</OrgnlMsgId><OrgnlMsgNmId>pacs.008.001.08</OrgnlMsgNmId>") -> str:
    return (
        f'<Document xmlns="{NS002}"><FIToFIPmtStsRpt><GrpHdr><MsgId>S1</MsgId></GrpHdr>'
        f"<OrgnlGrpInfAndSts>{group}</OrgnlGrpInfAndSts><TxInfAndSts>{tx}</TxInfAndSts></FIToFIPmtStsRpt></Document>"
    )


def sepa_reject(code: str = "AC01", status: str = "RJCT", extra: str = "") -> str:
    return pacs002(
        f"<StsId>ST1</StsId><OrgnlEndToEndId>E2E</OrgnlEndToEndId><OrgnlTxId>TX</OrgnlTxId><TxSts>{status}</TxSts>"
        f"<StsRsnInf>{ORIGINATOR}<Rsn><Cd>{code}</Cd></Rsn></StsRsnInf>{extra}{SEPA_REF}"
    )


def sepa_return(code: str = "AC04", returned: str = "100.00", original: str = "100.00", currency: str = "EUR", bearer: str = "SLEV") -> str:
    return (
        f'<Document xmlns="{NS004}"><PmtRtr><GrpHdr><MsgId>R1</MsgId></GrpHdr><TxInf><RtrId>RT1</RtrId>'
        "<OrgnlGrpInf><OrgnlMsgId>M1</OrgnlMsgId><OrgnlMsgNmId>pacs.008.001.08</OrgnlMsgNmId></OrgnlGrpInf>"
        "<OrgnlEndToEndId>E2E</OrgnlEndToEndId><OrgnlTxId>TX</OrgnlTxId>"
        f'<OrgnlIntrBkSttlmAmt Ccy="EUR">{original}</OrgnlIntrBkSttlmAmt>'
        f'<RtrdIntrBkSttlmAmt Ccy="{currency}">{returned}</RtrdIntrBkSttlmAmt>'
        f"<ChrgBr>{bearer}</ChrgBr><RtrRsnInf>{ORIGINATOR}<Rsn><Cd>{code}</Cd></Rsn></RtrRsnInf></TxInf></PmtRtr></Document>"
    )


# --- Reference data ---------------------------------------------------------------------------


def test_iso_code_sets_are_complete_enough() -> None:
    data = iso_codes()
    sets = data["code_sets"]

    assert data["release"] == "2Q2026"
    assert len(sets["ExternalStatusReason1Code"]["codes"]) > 300
    assert len(sets["ExternalReturnReason1Code"]["codes"]) > 100
    assert sets["ExternalStatusReason1Code"]["codes"]["AC01"] == "Account number is invalid or missing."
    assert "insufficient" in sets["ExternalStatusReason1Code"]["codes"]["AM04"]
    assert {"RJCT", "ACSC", "ACCP", "PDNG"} <= set(sets["ExternalPaymentTransactionStatus1Code"]["codes"])
    assert "PART" in sets["ExternalPaymentGroupStatus1Code"]["codes"]


def test_epc_lists_are_subsets_of_iso_lists() -> None:
    iso = iso_codes()["code_sets"]
    epc = epc_codes()

    assert set(epc["reject_pacs002"]) <= set(iso["ExternalStatusReason1Code"]["codes"])
    assert set(epc["return_pacs004"]) <= set(iso["ExternalReturnReason1Code"]["codes"])
    assert "AM04" not in epc["reject_pacs002"]  # insufficient funds is not an inter-PSP SCT reject reason


# --- Samples ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "original", "scheme", "matched_by"),
    [
        ("pacs002-sepa-reject.xml", "sepa/pacs008-valid.xml", "sepa", "end_to_end_id"),
        ("pacs004-sepa-return.xml", "sepa/pacs008-valid.xml", "sepa", "end_to_end_id"),
        ("pacs002-cbpr-reject.xml", "cbpr/pacs008-valid.xml", "cbpr", "uetr"),
    ],
)
def test_samples_are_valid_and_match_their_original(status: str, original: str, scheme: str, matched_by: str) -> None:
    result = explain_payment_status(read(f"status/{status}"), read(original))

    assert result["kind"] == "payment_status_explanation"
    assert result["scheme"] == scheme
    assert result["compliant"] is True
    assert rules(result) == []
    assert result["match"] == {"original_transactions": 1, "matched": 1}
    assert result["transactions"][0]["match"]["matched_by"] == matched_by


def test_sepa_reject_explains_the_reason() -> None:
    reason = explain_payment_status(read("status/pacs002-sepa-reject.xml"))["transactions"][0]["reasons"][0]

    assert reason["code"] == "AC01"
    assert reason["meaning"] == "Account number is invalid or missing."
    assert reason["scheme_meaning"] == "Account identifier incorrect (i.e. invalid IBAN)"
    assert reason["originator"] == "DEMODEFFXXX"


def test_return_shows_amounts() -> None:
    transaction = explain_payment_status(read("status/pacs004-sepa-return.xml"))["transactions"][0]

    assert transaction["status"]["code"] == "RETURNED"
    assert transaction["returned_amount"] == {"currency": "EUR", "value": "1250.50"}
    assert transaction["reasons"][0]["scheme_meaning"] == "Account closed"


def test_pain002_partial_with_original() -> None:
    result = explain_payment_status(read("status/pain002-partial.xml"), read("sepa/pain001-valid.xml"))

    assert result["message_type"] == "pain.002"
    assert result["group"]["status"]["code"] == "PART"
    assert [transaction["status"]["code"] for transaction in result["transactions"]] == ["ACCP", "RJCT"]
    assert result["transactions"][1]["reasons"][0]["code"] == "AM04"
    assert result["match"]["matched"] == 2


def test_problem_sample() -> None:
    result = explain_payment_status(read("status/pacs002-sepa-problems.xml"))

    assert result["compliant"] is False
    assert set(rules(result)) == {
        "SEPA_GROUP_STATUS",
        "REASON_UNKNOWN_CODE",
        "SEPA_TX_STATUS",
        "SEPA_REASON_COUNT",
        "SEPA_ORIGINATOR_MISSING",
        "SEPA_REASON_NOT_ALLOWED",
        "SEPA_ORIGINAL_REFERENCE",
        "SEPA_ORIGINAL_MESSAGE_NAME",
        "SEPA_IDENTIFICATION_MISSING",
    }


# --- SEPA rules ---------------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["AC01", "AM05", "RC01", "TM01", "FF01"])
def test_allowed_sepa_reject_reasons(code: str) -> None:
    assert rules(explain_payment_status(sepa_reject(code))) == []


@pytest.mark.parametrize("code", ["AM04", "AC04", "MD07"])
def test_reasons_not_allowed_in_a_sepa_reject(code: str) -> None:
    assert rules(explain_payment_status(sepa_reject(code))) == ["SEPA_REASON_NOT_ALLOWED"]


@pytest.mark.parametrize("code", ["AC04", "MD07", "FOCR", "MS02", "BE04"])
def test_allowed_sepa_return_reasons(code: str) -> None:
    assert rules(explain_payment_status(sepa_return(code))) == []


def test_return_amount_currency_and_bearer() -> None:
    assert rules(explain_payment_status(sepa_return(returned="90.00"))) == ["SEPA_RETURN_AMOUNT"]
    assert "SEPA_CURRENCY" in rules(explain_payment_status(sepa_return(currency="USD")))
    # Without SLEV or a SEPA service level the scheme is not detected as SEPA, so force it.
    assert rules(explain_payment_status(sepa_return(bearer="SHAR"), scheme="sepa")) == ["SEPA_CHARGE_BEARER"]
    assert rules(explain_payment_status(sepa_return(code="AM04"))) == ["SEPA_REASON_NOT_ALLOWED"]


def test_sepa_reject_without_reason_is_an_error() -> None:
    xml = pacs002(f"<StsId>S</StsId><OrgnlEndToEndId>E</OrgnlEndToEndId><OrgnlTxId>T</OrgnlTxId><TxSts>RJCT</TxSts>{SEPA_REF}")

    result = explain_payment_status(xml)

    assert rules(result) == ["REJECT_WITHOUT_REASON"]
    assert result["transactions"][0]["findings"][0]["severity"] == "error"


# --- CBPR+ and generic rules --------------------------------------------------------------------


def test_cbpr_original_uetr_rules() -> None:
    upper = pacs002("<OrgnlEndToEndId>E</OrgnlEndToEndId><OrgnlUETR>3F2B8C4E-9A1D-4E7B-8C2F-5D6A7B8C9D0E</OrgnlUETR><TxSts>ACSC</TxSts>")
    missing = pacs002("<OrgnlEndToEndId>E</OrgnlEndToEndId><TxSts>ACSC</TxSts>")

    assert rules(explain_payment_status(upper)) == ["CBPR_ORIGINAL_UETR_FORMAT"]
    assert rules(explain_payment_status(missing, scheme="cbpr")) == ["CBPR_ORIGINAL_UETR_MISSING"]


def test_cbpr_reject_without_reason_is_only_a_warning() -> None:
    xml = pacs002("<OrgnlUETR>3f2b8c4e-9a1d-4e7b-8c2f-5d6a7b8c9d0e</OrgnlUETR><TxSts>RJCT</TxSts>")

    result = explain_payment_status(xml)

    assert rules(result) == ["REJECT_WITHOUT_REASON"]
    assert result["compliant"] is True


def test_group_rejected_but_transaction_accepted() -> None:
    xml = pacs002("<OrgnlEndToEndId>E</OrgnlEndToEndId><TxSts>ACCP</TxSts>", group="<OrgnlMsgId>M</OrgnlMsgId><GrpSts>RJCT</GrpSts>")

    assert "GROUP_REJECTED_TRANSACTION_NOT" in rules(explain_payment_status(xml, scheme="generic"))


def test_unknown_status_and_missing_references() -> None:
    result = explain_payment_status(pacs002("<TxSts>WXYZ</TxSts>"), scheme="generic")

    assert set(rules(result)) == {"STATUS_UNKNOWN_CODE", "NO_ORIGINAL_REFERENCE"}


# --- Matching with the original ------------------------------------------------------------------


def test_status_that_matches_nothing() -> None:
    xml = pacs002("<OrgnlEndToEndId>OTHER</OrgnlEndToEndId><OrgnlUETR>3f2b8c4e-9a1d-4e7b-8c2f-5d6a7b8c9d0f</OrgnlUETR><TxSts>ACSC</TxSts>")

    result = explain_payment_status(xml, read("cbpr/pacs008-valid.xml"))

    assert "ORIGINAL_NOT_FOUND" in rules(result)
    assert result["match"]["matched"] == 0


def test_return_with_a_different_original_amount() -> None:
    xml = (
        read("status/pacs004-sepa-return.xml")
        .replace('<OrgnlIntrBkSttlmAmt Ccy="EUR">1250.50', '<OrgnlIntrBkSttlmAmt Ccy="EUR">1200.00')
        .replace('<RtrdIntrBkSttlmAmt Ccy="EUR">1250.50', '<RtrdIntrBkSttlmAmt Ccy="EUR">1200.00')
    )

    assert rules(explain_payment_status(xml, read("sepa/pacs008-valid.xml"))) == ["ORIGINAL_AMOUNT_MISMATCH"]


def test_unreadable_original() -> None:
    result = explain_payment_status(read("status/pacs002-cbpr-reject.xml"), "<broken")

    assert "ORIGINAL_UNREADABLE" in rules(result)


# --- Input handling ---------------------------------------------------------------------------------


def test_other_messages_are_out_of_scope() -> None:
    result = explain_payment_status(read("cbpr/pacs008-valid.xml"))

    assert result["in_scope"] is False
    assert "read_iso20022_message" in result["note"]


@pytest.mark.parametrize(("xml", "kind"), [("<Doc>", "malformed_xml"), ('<!DOCTYPE D [<!ENTITY a "A">]><D>&a;</D>', "unsupported_xml")])
def test_bad_xml(xml: str, kind: str) -> None:
    assert explain_payment_status(xml)["kind"] == kind


def test_bad_scheme_and_size() -> None:
    with pytest.raises(ValueError, match="scheme"):
        explain_payment_status(sepa_reject(), scheme="swift")
    with pytest.raises(ValueError, match="limit"):
        explain_payment_status("x" * (MAX_XML_CHARS + 1))
