"""Offline IBAN (ISO 13616) and BIC (ISO 9362) checks.

IBAN lengths and structures come from the IBAN Registry that Swift publishes as
registration authority (data/reference/iban_registry.json). SEPA membership comes
from EPC409-09 (data/reference/sepa_countries.json). These checks prove that an
identifier is well formed; they cannot prove that an account or a bank exists,
which needs a directory such as SwiftRef.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from app.paths import REFERENCE_DIR

MAX_IDENTIFIER_CHARS = 100

BIC_PATTERN = re.compile(r"^([A-Z0-9]{4})([A-Z]{2})([A-Z0-9]{2})([A-Z0-9]{3})?$")
STRUCTURE_TOKEN = re.compile(r"(\d+)!([nace])")
TOKEN_CLASSES = {"n": "[0-9]", "a": "[A-Z]", "c": "[A-Za-z0-9]", "e": " "}

LIMITATION = "Format and checksum only; this does not prove that the account or bank exists."


@lru_cache(maxsize=1)
def iban_registry() -> dict[str, Any]:
    return json.loads((REFERENCE_DIR / "iban_registry.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def sepa_countries() -> dict[str, Any]:
    return json.loads((REFERENCE_DIR / "sepa_countries.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _bban_pattern(structure: str) -> re.Pattern[str]:
    # The structure starts with the country code and "2!n" for the check digits; the rest is the BBAN.
    tokens = STRUCTURE_TOKEN.findall(structure[2:])
    bban_tokens = tokens[1:]
    return re.compile("^" + "".join(f"{TOKEN_CLASSES[kind]}{{{count}}}" for count, kind in bban_tokens) + "$")


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _mod97(value: str) -> int:
    rearranged = value[4:] + value[:4]
    digits = "".join(str(int(char, 36)) for char in rearranged)
    remainder = 0
    for start in range(0, len(digits), 9):
        remainder = int(str(remainder) + digits[start : start + 9]) % 97
    return remainder


def validate_iban(value: str) -> dict[str, Any]:
    """Validate an IBAN's characters, country, length, national structure and ISO 7064 mod-97 check digits."""
    raw = value[:MAX_IDENTIFIER_CHARS]
    iban = re.sub(r"\s+", "", raw).upper()
    registry = iban_registry()
    country = iban[:2]
    entry = registry["countries"].get(country)
    result: dict[str, Any] = {
        "input": raw,
        "iban": iban,
        "print_format": " ".join(iban[i : i + 4] for i in range(0, len(iban), 4)),
        "valid": False,
        "country": country or None,
        "country_name": entry["name"] if entry else None,
        "sepa": country in sepa_countries()["iban_country_codes"],
        "errors": [],
        "limitation": LIMITATION,
        "source": {"registry": registry["source"], "retrieved": registry["retrieved"], "url": registry["url"]},
    }
    errors = result["errors"]

    if not iban:
        errors.append(_error("IBAN_EMPTY", "No IBAN was provided."))
        return result
    if not re.fullmatch(r"[A-Z0-9]+", iban):
        errors.append(_error("IBAN_CHARACTERS", "An IBAN contains only letters and digits (spaces are ignored)."))
        return result
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}", iban[:4]):
        errors.append(_error("IBAN_PREFIX", "An IBAN starts with a two-letter country code followed by two check digits."))
        return result
    if entry is None:
        errors.append(_error("IBAN_COUNTRY_UNKNOWN", f"{country} has no national IBAN format in the IBAN Registry."))
        return result
    if len(iban) != entry["length"]:
        errors.append(_error("IBAN_LENGTH", f"A {entry['name']} IBAN has {entry['length']} characters; this one has {len(iban)}."))
        return result
    if not _bban_pattern(entry["structure"]).fullmatch(iban[4:]):
        errors.append(_error("IBAN_STRUCTURE", f"The account part does not match the {country} format {entry['structure'][4:]}."))
    if _mod97(iban) != 1:
        errors.append(_error("IBAN_CHECKSUM", "The check digits are wrong (ISO 7064 mod-97); the IBAN has a typo."))

    result["valid"] = not errors
    return result


def validate_bic(value: str) -> dict[str, Any]:
    """Validate a BIC's ISO 9362 format and describe its parts."""
    raw = value[:MAX_IDENTIFIER_CHARS]
    bic = raw.strip()
    sepa = sepa_countries()
    result: dict[str, Any] = {
        "input": raw,
        "bic": bic,
        "valid": False,
        "party_prefix": None,
        "country": None,
        "location": None,
        "branch": None,
        "is_primary_office": None,
        "is_test_bic": None,
        "sepa": None,
        "errors": [],
        "limitation": LIMITATION,
    }
    errors = result["errors"]
    if not bic:
        errors.append(_error("BIC_EMPTY", "No BIC was provided."))
        return result
    if bic != bic.upper():
        errors.append(_error("BIC_CASE", "A BIC is written in upper case."))
        bic = bic.upper()
    match = BIC_PATTERN.fullmatch(bic)
    if match is None:
        errors.append(
            _error("BIC_FORMAT", "A BIC has 8 or 11 characters: 4 party prefix, 2-letter country code, 2 location, optional 3 branch.")
        )
        return result

    prefix, country, location, branch = match.groups()
    result.update(
        {
            "bic": bic,
            "party_prefix": prefix,
            "country": country,
            "location": location,
            "branch": branch or "XXX",
            "is_primary_office": branch in (None, "XXX"),
            # ISO 9362: a "0" as second location character marks a test and training BIC.
            "is_test_bic": location[1] == "0",
            "sepa": country in sepa["bic_country_codes"],
        }
    )
    result["valid"] = not errors
    return result
