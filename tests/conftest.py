from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.services import knowledge_search, registry

ROOT = Path(__file__).resolve().parents[1]
DEMO_XSD = ROOT / "data" / "schemas" / "demo-payment.xsd"
DEMO_MESSAGE_ID = "demo.000.001.01"
DEMO_XML = (ROOT / "examples" / "demo-payment.xml").read_text(encoding="utf-8")


@pytest.fixture
def schema_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated schema directory containing only the synthetic demo XSD."""
    directory = (tmp_path / "schemas").resolve()
    directory.mkdir()
    shutil.copy(DEMO_XSD, directory / "demo-payment.xsd")
    write_registry(
        directory,
        {DEMO_MESSAGE_ID: {"title": "Synthetic demo", "file": "demo-payment.xsd", "synthetic": True}},
    )
    monkeypatch.setattr(registry, "SCHEMA_DIR", directory)
    monkeypatch.setattr(registry, "SCHEMA_MANIFEST", directory / "registry.json")
    return directory


def write_registry(directory: Path, entries: object) -> None:
    (directory / "registry.json").write_text(json.dumps(entries), encoding="utf-8")


@pytest.fixture
def knowledge_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated, empty knowledge directory; tests write their own sources."""
    directory = (tmp_path / "knowledge").resolve()
    directory.mkdir()
    monkeypatch.setattr(knowledge_search, "KNOWLEDGE_DIR", directory)
    monkeypatch.setattr(knowledge_search, "SOURCE_MANIFEST", directory / "sources.json")
    return directory


def write_sources(directory: Path, sources: list[dict[str, object]], files: dict[str, str]) -> None:
    (directory / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
