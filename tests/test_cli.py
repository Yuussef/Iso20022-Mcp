from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str]:
    code = main(list(args))
    return code, capsys.readouterr().out


def test_valid_cbpr_message_with_summary(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, str(EXAMPLES / "cbpr" / "pacs008-valid.xml"), "--summary")

    assert code == 0
    assert out.splitlines()[0] == "* Atelier Demo SARL pays Example Trading Pte Ltd 25000.00 USD"
    assert "banks: DEMOFRPPXXX -> DEMOUS33XXX -> DEMOSGSGXXX" in out
    assert "PASS meets CBPR+ pacs.008 rules" in out


def test_auto_profile_picks_sepa_for_pain001(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, str(EXAMPLES / "sepa" / "pain001-valid.xml"))

    assert code == 0
    assert "EPC SEPA Credit Transfer rules" in out


def test_findings_exit_with_1(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, str(EXAMPLES / "sepa" / "pacs008-problems.xml"), "--profile", "sepa")

    assert code == 1
    assert out.startswith("FAIL breaks EPC SEPA Credit Transfer rules")
    assert "[ERROR] SEPA_CHARGE_BEARER" in out
    assert "at /Document/" in out


def test_address_profile_and_enforcement(capsys: pytest.CaptureFixture[str]) -> None:
    sample = str(EXAMPLES / "postal-address" / "hybrid.xml")

    assert run(capsys, sample, "--profile", "address")[0] == 0
    unstructured = str(EXAMPLES / "postal-address" / "problems.xml")
    assert run(capsys, unstructured, "--profile", "address")[0] == 1


def test_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, str(EXAMPLES / "sepa" / "pacs008-valid.xml"), "--json", "--summary")
    payload = json.loads(out)

    assert code == 0
    assert payload["profile"] == "sepa"
    assert payload["result"]["compliant"] is True
    assert payload["summary"]["kind"] == "payment_summary"


@pytest.mark.parametrize(
    ("args", "code", "text"),
    [
        (("--iban", "DE89 3704 0044 0532 0130 00"), 0, "PASS valid"),
        (("--iban", "DE00"), 1, "FAIL invalid"),
        (("--bic", "DEUTDEFF"), 0, "PASS valid DEUTDEFF"),
    ],
)
def test_identifiers(capsys: pytest.CaptureFixture[str], args: tuple[str, ...], code: int, text: str) -> None:
    result, out = run(capsys, *args)

    assert result == code
    assert text in out
    assert "does not prove" in out


def test_mt103_conversion(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "--mt103", str(EXAMPLES / "mt103" / "legacy-free-text.txt"))

    assert code == 1  # the legacy MT103 has no UETR
    assert "MISSING" in out and "UNMAPPED" in out
    assert "<Document" in out
    assert "not a certified Swift translation" in out


def test_unreadable_inputs_exit_with_2(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    broken = tmp_path / "broken.xml"
    broken.write_text("<Document>", encoding="utf-8")
    not_mt = tmp_path / "note.txt"
    not_mt.write_text("hello", encoding="utf-8")

    assert run(capsys, str(broken))[0] == 2
    assert run(capsys, str(tmp_path / "missing.xml"))[0] == 2
    assert run(capsys, "--mt103", str(not_mt))[0] == 2
    assert run(capsys)[0] == 2


def test_output_is_plain_ascii(capsys: pytest.CaptureFixture[str]) -> None:
    _, out = run(capsys, str(EXAMPLES / "cbpr" / "pacs008-problems.xml"), "--summary")

    # Findings may quote message content, but the tool's own markers stay ASCII for any console.
    assert all(line.split(" ", 1)[0].isascii() for line in out.splitlines() if line)
