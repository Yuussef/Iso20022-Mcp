"""Run the starter evaluation set in data/evaluations/starter.jsonl as regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.knowledge_search import search_documents
from app.services.registry import schema_path

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    json.loads(line)
    for line in (ROOT / "data" / "evaluations" / "starter.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]


def _cases(kind: str) -> list:
    return [pytest.param(case, id=case["id"]) for case in CASES if case["kind"] == kind]


def test_every_case_kind_is_covered() -> None:
    assert {case["kind"] for case in CASES} <= {"retrieval", "validation-configuration"}


@pytest.mark.parametrize("case", _cases("retrieval"))
def test_retrieval_case(case: dict) -> None:
    returned = {result["source_id"] for result in search_documents(case["query"], case.get("message_id"))["results"]}

    assert set(case["expected_source_ids"]) <= returned


@pytest.mark.parametrize("case", _cases("validation-configuration"))
def test_validation_configuration_case(case: dict) -> None:
    if schema_path(case["message_id"]) is not None:
        pytest.skip(f"A local XSD for {case['message_id']} is installed; this case only applies without one.")
    payload = json.loads((ROOT / case["fixture"]).read_text(encoding="utf-8"))

    response = TestClient(app).post("/api/v1/validate", json=payload)

    assert response.status_code == case["expected_http_status"]
