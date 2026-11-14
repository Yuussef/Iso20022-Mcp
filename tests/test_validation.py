from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.registry import SchemaUnavailableError
from app.services.validation import MAX_XML_CHARS, SchemaConfigurationError, validate_message
from tests.conftest import DEMO_MESSAGE_ID, DEMO_XML


def test_demo_xml_is_valid(schema_dir: Path) -> None:
    result = validate_message(DEMO_MESSAGE_ID, DEMO_XML)

    assert result == {
        "message_id": DEMO_MESSAGE_ID,
        "valid": True,
        "kind": "xsd_validation",
        "errors": [],
        "errors_truncated": False,
    }


@pytest.mark.parametrize(
    "xml",
    [
        # Amount is not an xs:decimal
        "<DemoPayment>\n<MessageId>T</MessageId>\n<Amount>abc</Amount>\n<Currency>EUR</Currency>\n</DemoPayment>",
        # Elements out of sequence order
        "<DemoPayment>\n<Amount>1</Amount>\n<MessageId>T</MessageId>\n<Currency>EUR</Currency>\n</DemoPayment>",
        # Required element missing
        "<DemoPayment>\n<MessageId>T</MessageId>\n<Amount>1</Amount>\n</DemoPayment>",
        # Wrong root element
        "<OtherPayment/>",
    ],
)
def test_schema_violations_return_structured_diagnostics(schema_dir: Path, xml: str) -> None:
    result = validate_message(DEMO_MESSAGE_ID, xml)

    assert result["valid"] is False
    assert result["kind"] == "xsd_validation"
    assert result["errors"], "expected at least one diagnostic"
    for error in result["errors"]:
        assert set(error) == {"code", "message", "line", "column", "xpath"}
        assert error["code"] and error["message"]
        assert isinstance(error["line"], int)
    assert result["errors_truncated"] is False


def test_invalid_amount_reports_offending_line(schema_dir: Path) -> None:
    xml = "<DemoPayment>\n<MessageId>T</MessageId>\n<Amount>abc</Amount>\n<Currency>EUR</Currency>\n</DemoPayment>"

    error = validate_message(DEMO_MESSAGE_ID, xml)["errors"][0]

    assert error["line"] == 3
    assert "Amount" in error["message"]


@pytest.mark.parametrize("xml", ["<DemoPayment>", "not xml at all", "<a><b></a>"])
def test_malformed_xml_is_reported_without_raising(schema_dir: Path, xml: str) -> None:
    result = validate_message(DEMO_MESSAGE_ID, xml)

    assert result["valid"] is False
    assert result["kind"] == "malformed_xml"
    assert result["errors"][0]["code"] == "XML_SYNTAX_ERROR"
    assert len(result["errors"][0]["message"]) <= 500


# Known bug: entities are correctly left unexpanded by the parser, but lxml then raises
# XMLSchemaValidateError ("Internal error in XML Schema validation") on the unresolved
# entity reference. validate_message does not catch it, so the API answers HTTP 500
# instead of a structured invalid result. Remove these markers once that is handled.
ENTITY_BUG = pytest.mark.xfail(
    strict=True,
    reason="validate_message does not catch XMLSchemaValidateError for unresolved entity references",
)


@ENTITY_BUG
def test_external_entities_are_never_expanded(schema_dir: Path, tmp_path: Path) -> None:
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("TOP-SECRET-VALUE", encoding="utf-8")
    xml = (
        f'<!DOCTYPE DemoPayment [<!ENTITY xxe SYSTEM "{secret_file.as_uri()}">]>'
        "<DemoPayment><MessageId>&xxe;</MessageId><Amount>1</Amount><Currency>EUR</Currency></DemoPayment>"
    )

    result = validate_message(DEMO_MESSAGE_ID, xml)

    assert "TOP-SECRET-VALUE" not in json.dumps(result)


@ENTITY_BUG
def test_entity_expansion_bomb_is_not_expanded(schema_dir: Path) -> None:
    xml = (
        '<!DOCTYPE DemoPayment [<!ENTITY a "AAAAAAAAAA">'
        '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;"><!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]>'
        "<DemoPayment><MessageId>&c;</MessageId><Amount>1</Amount><Currency>EUR</Currency></DemoPayment>"
    )

    result = validate_message(DEMO_MESSAGE_ID, xml)

    assert "A" * 100 not in json.dumps(result)


def test_oversized_input_is_rejected_before_parsing(schema_dir: Path) -> None:
    with pytest.raises(ValueError, match="limit"):
        validate_message(DEMO_MESSAGE_ID, "x" * (MAX_XML_CHARS + 1))


def test_unregistered_message_raises_schema_unavailable(schema_dir: Path) -> None:
    with pytest.raises(SchemaUnavailableError):
        validate_message("pacs.008.001.08", DEMO_XML)


def test_broken_xsd_raises_configuration_error(schema_dir: Path) -> None:
    (schema_dir / "demo-payment.xsd").write_text("<xs:schema this is not valid", encoding="utf-8")

    with pytest.raises(SchemaConfigurationError):
        validate_message(DEMO_MESSAGE_ID, DEMO_XML)


def test_error_list_is_capped_at_100(schema_dir: Path) -> None:
    (schema_dir / "demo-payment.xsd").write_text(
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        '<xs:element name="Root"><xs:complexType><xs:sequence>'
        '<xs:element name="N" type="xs:int" maxOccurs="unbounded"/>'
        "</xs:sequence></xs:complexType></xs:element></xs:schema>",
        encoding="utf-8",
    )
    xml = "<Root>" + "<N>x</N>" * 150 + "</Root>"

    result = validate_message(DEMO_MESSAGE_ID, xml)

    assert len(result["errors"]) == 100
    assert result["errors_truncated"] is True
