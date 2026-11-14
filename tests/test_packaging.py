from __future__ import annotations

import json
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_skill_zip  # noqa: E402


def pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_console_scripts_point_to_real_functions() -> None:
    from app.cli import main as cli_main
    from app.mcp_server.server import main as server_main

    scripts = pyproject()["project"]["scripts"]
    assert scripts == {"iso20022-mcp": "app.mcp_server.server:main", "iso20022-check": "app.cli:main"}
    assert callable(cli_main) and callable(server_main)


def test_wheel_bundles_every_knowledge_note_and_reference_file() -> None:
    included = pyproject()["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    sources = json.loads((ROOT / "data" / "knowledge" / "sources.json").read_text(encoding="utf-8"))

    for source in sources:
        assert f"data/knowledge/{source['file']}" in included, f"{source['file']} is missing from the wheel"
    assert "data/knowledge/sources.json" in included
    assert included["data/reference"] == "app/data/reference"
    for path in included:
        assert (ROOT / path).exists(), path


def test_data_dir_resolves_in_a_checkout() -> None:
    from app.paths import DATA_DIR, REFERENCE_DIR

    assert DATA_DIR == ROOT / "data"
    assert (REFERENCE_DIR / "iban_registry.json").is_file()


def test_skill_front_matter_and_zip(tmp_path: Path) -> None:
    output = build_skill_zip.build(output=tmp_path / "skill.zip")

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        skill = archive.read("iso20022-payment-reviewer/SKILL.md").decode("utf-8")
    assert names == ["iso20022-payment-reviewer/SKILL.md", "iso20022-payment-reviewer/LICENSE"]
    assert skill.startswith("---\nname: iso20022-payment-reviewer\ndescription: ")
    assert "iso20022-check" in skill


def test_skill_builder_refuses_secrets_and_missing_front_matter(tmp_path: Path) -> None:
    skill = tmp_path / "bad-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("no front matter\naws_secret_access_key = x\n", encoding="utf-8")
    (skill / ".env").write_text("TOKEN=1", encoding="utf-8")

    problems = build_skill_zip.check_skill(skill)

    assert any("front matter" in problem for problem in problems)
    assert any("credential pattern" in problem for problem in problems)
    assert any(".env" in problem for problem in problems)
    with pytest.raises(SystemExit):
        build_skill_zip.build(skill, tmp_path / "out.zip")
