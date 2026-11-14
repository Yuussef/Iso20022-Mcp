from __future__ import annotations

import pytest

from app.services.identifiers import iban_registry, sepa_countries, validate_bic, validate_iban


def codes(result: dict) -> list[str]:
    return [error["code"] for error in result["errors"]]


# --- Reference data --------------------------------------------------------------------------


def test_every_registry_example_iban_is_valid() -> None:
    failing = [code for code, entry in iban_registry()["countries"].items() if not validate_iban(entry["example"])["valid"]]

    assert failing == []
    assert len(iban_registry()["countries"]) == 89


def test_registry_entries_are_consistent() -> None:
    for code, entry in iban_registry()["countries"].items():
        assert entry["structure"].startswith(code)
        assert entry["example"].startswith(code)
        assert len(entry["example"]) == entry["length"]


def test_sepa_scope_matches_epc409_09_v8() -> None:
    sepa = sepa_countries()

    assert sepa["issued"] == "2025-12-24"
    # 27 EU + 3 EEA + 11 non-EEA countries, plus Gibraltar's own IBAN code.
    assert len(sepa["iban_country_codes"]) == 42
    assert {"AL", "MD", "ME", "MK", "RS", "CH", "GB"} <= set(sepa["iban_country_codes"])
    assert set(sepa["non_eea_bic_country_codes"]) <= set(sepa["bic_country_codes"])
    assert "DE" not in sepa["non_eea_bic_country_codes"]


# --- IBAN ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["DE89370400440532013000", "DE89 3704 0044 0532 0130 00", "de89370400440532013000", " FR14 2004 1010 0505 0001 3M02 606 "],
)
def test_valid_ibans_in_any_layout(value: str) -> None:
    result = validate_iban(value)

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["sepa"] is True


def test_iban_print_format_and_country() -> None:
    result = validate_iban("DE89370400440532013000")

    assert result["print_format"] == "DE89 3704 0044 0532 0130 00"
    assert result["country_name"] == "Germany"
    assert "does not prove" in result["limitation"]


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("", "IBAN_EMPTY"),
        ("DE89-3704-0044", "IBAN_CHARACTERS"),
        ("1234370400440532013000", "IBAN_PREFIX"),
        ("XX89370400440532013000", "IBAN_COUNTRY_UNKNOWN"),
        ("DE8937040044053201300", "IBAN_LENGTH"),
        ("DE89370400440532013001", "IBAN_CHECKSUM"),
    ],
)
def test_invalid_ibans(value: str, code: str) -> None:
    result = validate_iban(value)

    assert result["valid"] is False
    assert codes(result)[0] == code


def test_iban_with_letters_where_digits_are_required_breaks_the_structure() -> None:
    # Germany is 8!n10!n; a letter in the account part breaks the national structure.
    assert "IBAN_STRUCTURE" in codes(validate_iban("DE89370400440532013A00"))


def test_valid_iban_outside_sepa() -> None:
    result = validate_iban("AE070331234567890123456")

    assert result["valid"] is True
    assert result["sepa"] is False


def test_long_input_is_truncated() -> None:
    assert len(validate_iban("D" * 10_000)["input"]) == 100


# --- BIC -------------------------------------------------------------------------------------


def test_bic8_and_bic11() -> None:
    bic8 = validate_bic("DEUTDEFF")
    bic11 = validate_bic("DEUTDEFF500")

    assert bic8["valid"] and bic11["valid"]
    assert (bic8["party_prefix"], bic8["country"], bic8["location"], bic8["branch"]) == ("DEUT", "DE", "FF", "XXX")
    assert bic8["is_primary_office"] is True
    assert bic11["branch"] == "500" and bic11["is_primary_office"] is False
    assert bic8["sepa"] is True


def test_test_bic_is_flagged() -> None:
    assert validate_bic("DEMOFR20XXX")["is_test_bic"] is True
    assert validate_bic("DEMOFRPPXXX")["is_test_bic"] is False


@pytest.mark.parametrize(
    ("value", "code"), [("", "BIC_EMPTY"), ("deutdeff", "BIC_CASE"), ("DEUT1EFF", "BIC_FORMAT"), ("DEUTDEFF5", "BIC_FORMAT")]
)
def test_invalid_bics(value: str, code: str) -> None:
    result = validate_bic(value)

    assert result["valid"] is False
    assert code in codes(result)


def test_bic_outside_sepa() -> None:
    assert validate_bic("DEMOUS33XXX")["sepa"] is False


def test_territory_bic_codes_are_sepa() -> None:
    # EPC409-09 lists Guernsey, Jersey, Isle of Man and French territories with their own BIC country codes.
    assert all(validate_bic(f"DEMO{code}22XXX")["sepa"] for code in ("GG", "JE", "IM", "GP", "PM"))
