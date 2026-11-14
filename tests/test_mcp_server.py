from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import DEMO_MESSAGE_ID, DEMO_XML

mcp = pytest.importorskip("mcp", reason="install the optional `ai` extra to test the MCP server")

from mcp import Client  # noqa: E402

from app.mcp_server.server import mcp as paydoc_mcp  # noqa: E402

pytestmark = pytest.mark.anyio


async def test_server_exposes_all_tools() -> None:
    async with Client(paydoc_mcp) as client:
        tools = await client.list_tools()

    assert {tool.name for tool in tools.tools} == {
        "list_supported_messages",
        "validate_message",
        "search_iso_documents",
        "explain_validation_error",
        "check_cbpr_postal_addresses",
        "check_sepa_sct",
        "validate_iban",
        "validate_bic",
        "check_cbpr_pacs008",
        "summarize_payment",
    }


async def test_validate_message_tool_matches_service(schema_dir: Path) -> None:
    async with Client(paydoc_mcp) as client:
        result = await client.call_tool("validate_message", {"message_id": DEMO_MESSAGE_ID, "xml": DEMO_XML})

    assert result.structured_content["valid"] is True
    assert result.structured_content["kind"] == "xsd_validation"


async def test_validate_message_tool_reports_missing_schema(schema_dir: Path) -> None:
    async with Client(paydoc_mcp) as client:
        result = await client.call_tool("validate_message", {"message_id": "pacs.008.001.08", "xml": "<Document/>"})

    assert result.structured_content["valid"] is False
    assert result.structured_content["kind"] == "schema_unavailable"


async def test_search_tool_clamps_limit() -> None:
    async with Client(paydoc_mcp) as client:
        result = await client.call_tool("search_iso_documents", {"query": "message version schema", "limit": 500})

    results = result.structured_content["results"]
    assert 1 <= len(results) <= 10
    assert results[0]["source_id"] == "iso20022-catalogue-overview"


async def test_postal_address_tool_reports_findings() -> None:
    xml = (Path(__file__).resolve().parents[1] / "examples" / "postal-address" / "problems.xml").read_text(encoding="utf-8")

    async with Client(paydoc_mcp) as client:
        result = await client.call_tool("check_cbpr_postal_addresses", {"xml": xml, "enforce_unstructured_removal": True})

    content = result.structured_content
    assert content["compliant"] is False
    assert content["unstructured_removal"]["status"] == "deferred"
    assert {address["role"] for address in content["addresses"]} == {"Dbtr", "CdtrAgt", "Cdtr", "UltmtCdtr"}


async def test_postal_address_tool_rejects_oversized_input() -> None:
    async with Client(paydoc_mcp) as client:
        result = await client.call_tool("check_cbpr_postal_addresses", {"xml": "x" * 1_000_001})

    assert result.structured_content["kind"] == "invalid_input"


async def test_sepa_tools() -> None:
    xml = (Path(__file__).resolve().parents[1] / "examples" / "sepa" / "pacs008-problems.xml").read_text(encoding="utf-8")

    async with Client(paydoc_mcp) as client:
        sepa = await client.call_tool("check_sepa_sct", {"xml": xml})
        iban = await client.call_tool("validate_iban", {"iban": "DE89370400440532013000"})
        bic = await client.call_tool("validate_bic", {"bic": "DEMOCHZZXXX"})

    assert sepa.structured_content["compliant"] is False
    assert sepa.structured_content["unstructured_address_end"]["status"] == "deferred"
    assert iban.structured_content["valid"] is True
    assert bic.structured_content["country"] == "CH"


async def test_sepa_tool_rejects_oversized_input() -> None:
    async with Client(paydoc_mcp) as client:
        result = await client.call_tool("check_sepa_sct", {"xml": "x" * 1_000_001})

    assert result.structured_content["kind"] == "invalid_input"


async def test_cbpr_and_summary_tools() -> None:
    xml = (Path(__file__).resolve().parents[1] / "examples" / "cbpr" / "pacs008-problems.xml").read_text(encoding="utf-8")

    async with Client(paydoc_mcp) as client:
        check = await client.call_tool("check_cbpr_pacs008", {"xml": xml})
        summary = await client.call_tool("summarize_payment", {"xml": xml})

    assert check.structured_content["compliant"] is False
    assert len(summary.structured_content["transactions"]) == 2
