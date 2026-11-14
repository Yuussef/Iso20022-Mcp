from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import DEMO_MESSAGE_ID, DEMO_XML

mcp = pytest.importorskip("mcp", reason="install the optional `ai` extra to test the MCP server")

from mcp import Client  # noqa: E402

from app.mcp_server.server import mcp as paydoc_mcp  # noqa: E402

pytestmark = pytest.mark.anyio


async def test_server_exposes_the_four_tools() -> None:
    async with Client(paydoc_mcp) as client:
        tools = await client.list_tools()

    assert {tool.name for tool in tools.tools} == {
        "list_supported_messages",
        "validate_message",
        "search_iso_documents",
        "explain_validation_error",
        "check_cbpr_postal_addresses",
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
