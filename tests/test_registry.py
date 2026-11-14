from __future__ import annotations

from pathlib import Path

import pytest

from app.services.registry import schema_path, supported_messages
from tests.conftest import DEMO_MESSAGE_ID, write_registry


def test_demo_schema_is_listed_as_available_and_synthetic(schema_dir: Path) -> None:
    result = supported_messages()

    assert result["messages"] == [
        {"message_id": DEMO_MESSAGE_ID, "title": "Synthetic demo", "available": True, "synthetic": True}
    ]
    # A synthetic schema alone does not count as a configured ISO message.
    assert result["configured"] is False


def test_real_schema_marks_registry_configured(schema_dir: Path) -> None:
    (schema_dir / "pacs.008.001.08.xsd").write_text((schema_dir / "demo-payment.xsd").read_text(), encoding="utf-8")
    write_registry(schema_dir, {"pacs.008.001.08": {"title": "Test", "file": "pacs.008.001.08.xsd"}})

    assert supported_messages()["configured"] is True


def test_demo_schema_path_resolves_inside_schema_dir(schema_dir: Path) -> None:
    assert schema_path(DEMO_MESSAGE_ID) == schema_dir / "demo-payment.xsd"


@pytest.mark.parametrize("message_id", ["pacs.008.001.08", "not-an-id", "PACS.008.001.08", "../demo.000.001.01", ""])
def test_unknown_or_malformed_ids_have_no_schema(schema_dir: Path, message_id: str) -> None:
    assert schema_path(message_id) is None


@pytest.mark.parametrize(
    "file_name",
    [
        "../demo-payment.xsd",  # path traversal out of the schema directory
        "nested/demo-payment.xsd",  # subdirectories are not allowed
        "registry.json",  # wrong suffix
        "missing.xsd",  # registered but not present on disk
    ],
)
def test_unsafe_or_missing_schema_files_are_rejected(schema_dir: Path, file_name: str) -> None:
    (schema_dir / "nested").mkdir()
    (schema_dir / "nested" / "demo-payment.xsd").write_text("<x/>", encoding="utf-8")
    (schema_dir.parent / "demo-payment.xsd").write_text("<x/>", encoding="utf-8")
    write_registry(schema_dir, {"pacs.008.001.08": {"title": "Test", "file": file_name}})

    assert schema_path("pacs.008.001.08") is None
    assert supported_messages()["messages"][0]["available"] is False


@pytest.mark.parametrize("content", ["{not json", "[]", '"a string"'])
def test_corrupt_registry_is_treated_as_empty(schema_dir: Path, content: str) -> None:
    (schema_dir / "registry.json").write_text(content, encoding="utf-8")

    assert supported_messages() == {"messages": [], "configured": False}
    assert schema_path(DEMO_MESSAGE_ID) is None


def test_missing_registry_is_treated_as_empty(schema_dir: Path) -> None:
    (schema_dir / "registry.json").unlink()

    assert supported_messages() == {"messages": [], "configured": False}


def test_invalid_registry_entries_are_skipped(schema_dir: Path) -> None:
    write_registry(
        schema_dir,
        {
            DEMO_MESSAGE_ID: {"title": 123, "file": "demo-payment.xsd"},
            "bad id": {"title": "Skipped", "file": "demo-payment.xsd"},
            "pacs.008.001.08": "not an object",
        },
    )

    messages = supported_messages()["messages"]
    assert [item["message_id"] for item in messages] == [DEMO_MESSAGE_ID]
    assert messages[0]["title"] == DEMO_MESSAGE_ID  # non-string title falls back to the ID
