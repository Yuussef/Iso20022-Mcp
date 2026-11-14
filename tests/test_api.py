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
