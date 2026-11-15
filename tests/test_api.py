from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import DEMO_MESSAGE_ID, DEMO_XML

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "paydoc-ai"}


def test_messages_lists_demo_schema(schema_dir: Path) -> None:
    response = client.get("/api/v1/messages")

    assert response.status_code == 200
    assert response.json()["messages"][0]["message_id"] == DEMO_MESSAGE_ID


def test_validate_demo_xml(schema_dir: Path) -> None:
    response = client.post("/api/v1/validate", json={"message_id": DEMO_MESSAGE_ID, "xml": DEMO_XML})

    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_validate_invalid_xml_is_still_http_200(schema_dir: Path) -> None:
    response = client.post("/api/v1/validate", json={"message_id": DEMO_MESSAGE_ID, "xml": "<DemoPayment/>"})

    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_validate_xml_with_entities_is_http_200_not_500(schema_dir: Path) -> None:
    xml = '<!DOCTYPE D [<!ENTITY a "A">]><DemoPayment><MessageId>&a;</MessageId><Amount>1</Amount><Currency>EUR</Currency></DemoPayment>'

    response = client.post("/api/v1/validate", json={"message_id": DEMO_MESSAGE_ID, "xml": xml})

    assert response.status_code == 200
    assert response.json()["kind"] == "unsupported_xml"


def test_validate_unregistered_schema_returns_409(schema_dir: Path) -> None:
    response = client.post("/api/v1/validate", json={"message_id": "pacs.008.001.08", "xml": "<Document/>"})

    assert response.status_code == 409
    assert "registry.json" in response.json()["detail"]


def test_validate_broken_schema_returns_500(schema_dir: Path) -> None:
    (schema_dir / "demo-payment.xsd").write_text("<broken", encoding="utf-8")

    response = client.post("/api/v1/validate", json={"message_id": DEMO_MESSAGE_ID, "xml": DEMO_XML})

    assert response.status_code == 500


@pytest.mark.parametrize(
    "payload",
    [
        {"message_id": "not-an-id", "xml": "<a/>"},
        {"message_id": DEMO_MESSAGE_ID, "xml": ""},
        {"message_id": DEMO_MESSAGE_ID},
        {"message_id": DEMO_MESSAGE_ID, "xml": "x" * 1_000_001},
    ],
)
def test_validate_rejects_invalid_requests(schema_dir: Path, payload: dict) -> None:
    assert client.post("/api/v1/validate", json=payload).status_code == 422


def test_search() -> None:
    response = client.post("/api/v1/search", json={"query": "message version and schema", "limit": 5})

    assert response.status_code == 200
    assert response.json()["results"][0]["source_id"] == "iso20022-catalogue-overview"


@pytest.mark.parametrize("payload", [{"query": "x"}, {"query": "valid query", "limit": 0}, {"query": "valid query", "limit": 11}])
def test_search_rejects_invalid_requests(payload: dict) -> None:
    assert client.post("/api/v1/search", json=payload).status_code == 422


def test_ask_is_disabled_without_bedrock_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)

    response = client.post("/api/v1/ask", json={"question": "What is pacs.008?"})

    assert response.status_code == 503
    assert "BEDROCK_MODEL_ID" in response.json()["detail"]


def _address_sample(name: str) -> str:
    return (Path(__file__).resolve().parents[1] / "examples" / "postal-address" / f"{name}.xml").read_text(encoding="utf-8")


def test_postal_address_check_endpoint() -> None:
    response = client.post("/api/v1/checks/postal-address", json={"xml": _address_sample("problems")})

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "postal_address_check"
    assert body["compliant"] is False
    assert body["summary"]["unstructured"] == 2


def test_postal_address_check_enforce_flag() -> None:
    xml = _address_sample("problems")

    relaxed = client.post("/api/v1/checks/postal-address", json={"xml": xml}).json()
    enforced = client.post("/api/v1/checks/postal-address", json={"xml": xml, "enforce_unstructured_removal": True}).json()

    assert enforced["summary"]["errors"] == relaxed["summary"]["errors"] + 2
    assert enforced["unstructured_removal"]["enforced"] is True


def test_postal_address_check_handles_entities_without_500() -> None:
    xml = '<!DOCTYPE D [<!ENTITY a "A">]><Document><Dbtr><PstlAdr><TwnNm>&a;</TwnNm></PstlAdr></Dbtr></Document>'

    response = client.post("/api/v1/checks/postal-address", json={"xml": xml})

    assert response.status_code == 200
    assert response.json()["kind"] == "unsupported_xml"


@pytest.mark.parametrize("payload", [{"xml": ""}, {}, {"xml": "x" * 1_000_001}, {"xml": "<a/>", "enforce_unstructured_removal": "maybe"}])
def test_postal_address_check_rejects_invalid_requests(payload: dict) -> None:
    assert client.post("/api/v1/checks/postal-address", json=payload).status_code == 422


def _sepa_sample(name: str) -> str:
    return (Path(__file__).resolve().parents[1] / "examples" / "sepa" / f"{name}.xml").read_text(encoding="utf-8")


def test_sepa_check_endpoint() -> None:
    valid = client.post("/api/v1/checks/sepa-sct", json={"xml": _sepa_sample("pacs008-valid")}).json()
    problems = client.post("/api/v1/checks/sepa-sct", json={"xml": _sepa_sample("pacs008-problems")}).json()

    assert valid["compliant"] is True
    assert problems["compliant"] is False
    assert problems["summary"]["errors"] >= 10


def test_sepa_check_enforce_flag() -> None:
    xml = _sepa_sample("pacs008-problems")

    relaxed = client.post("/api/v1/checks/sepa-sct", json={"xml": xml}).json()
    enforced = client.post("/api/v1/checks/sepa-sct", json={"xml": xml, "enforce_unstructured_address_removal": True}).json()

    assert enforced["summary"]["errors"] == relaxed["summary"]["errors"] + 1


@pytest.mark.parametrize(
    ("kind", "value", "valid"),
    [("iban", "DE89 3704 0044 0532 0130 00", True), ("iban", "DE00", False), ("bic", "DEUTDEFF", True)],
)
def test_identifier_endpoints(kind: str, value: str, valid: bool) -> None:
    response = client.post(f"/api/v1/identifiers/{kind}", json={"value": value})

    assert response.status_code == 200
    assert response.json()["valid"] is valid


@pytest.mark.parametrize("payload", [{"value": ""}, {}, {"value": "x" * 101}])
def test_identifier_endpoints_reject_invalid_requests(payload: dict) -> None:
    assert client.post("/api/v1/identifiers/iban", json=payload).status_code == 422


def _cbpr_sample(name: str) -> str:
    return (Path(__file__).resolve().parents[1] / "examples" / "cbpr" / f"{name}.xml").read_text(encoding="utf-8")


def test_cbpr_check_endpoint() -> None:
    valid = client.post("/api/v1/checks/cbpr-pacs008", json={"xml": _cbpr_sample("pacs008-valid")}).json()
    problems = client.post("/api/v1/checks/cbpr-pacs008", json={"xml": _cbpr_sample("pacs008-problems")}).json()

    assert valid["compliant"] is True
    assert problems["compliant"] is False
    assert problems["postal_addresses"]["kind"] == "postal_address_check"


def test_payment_summary_endpoint() -> None:
    response = client.post("/api/v1/summaries/payment", json={"xml": _cbpr_sample("pacs008-valid")})

    assert response.status_code == 200
    assert response.json()["transactions"][0]["agent_chain"][-1]["role"] == "CdtrAgt"


@pytest.mark.parametrize("endpoint", ["/api/v1/checks/cbpr-pacs008", "/api/v1/summaries/payment"])
def test_cbpr_endpoints_reject_empty_xml(endpoint: str) -> None:
    assert client.post(endpoint, json={"xml": ""}).status_code == 422


def test_mt103_conversion_endpoint() -> None:
    mt = (Path(__file__).resolve().parents[1] / "examples" / "mt103" / "structured-parties.txt").read_text(encoding="utf-8")

    response = client.post("/api/v1/convert/mt103", json={"mt": mt})

    assert response.status_code == 200
    assert response.json()["cbpr_check"]["compliant"] is True


@pytest.mark.parametrize(("mt", "status"), [("not an mt103", 422), ("", 422), ("x" * 20_001, 422)])
def test_mt103_conversion_rejects_bad_input(mt: str, status: int) -> None:
    assert client.post("/api/v1/convert/mt103", json={"mt": mt}).status_code == status


def _example(name: str) -> str:
    return (Path(__file__).resolve().parents[1] / "examples" / name).read_text(encoding="utf-8")


def test_status_endpoint_with_original() -> None:
    response = client.post(
        "/api/v1/explain/status",
        json={"xml": _example("status/pacs002-cbpr-reject.xml"), "original_xml": _example("cbpr/pacs008-valid.xml")},
    )

    assert response.status_code == 200
    assert response.json()["transactions"][0]["match"]["matched_by"] == "uetr"


@pytest.mark.parametrize("payload", [{"xml": ""}, {"xml": "<a/>", "scheme": "swift"}])
def test_status_endpoint_rejects_invalid_requests(payload: dict) -> None:
    assert client.post("/api/v1/explain/status", json=payload).status_code == 422


def test_read_endpoint() -> None:
    response = client.post("/api/v1/read", json={"xml": _example("read/camt053-statement.xml")})

    assert response.status_code == 200
    assert response.json()["message_name"] == "BankToCustomerStatement"
