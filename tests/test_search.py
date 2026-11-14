from __future__ import annotations

from pathlib import Path

from app.services.knowledge_search import search_documents
from tests.conftest import write_sources

GENERAL_NOTE = "# Note\n\nSelect a message version and schema from the catalogue.\n\nUnrelated paragraph about lunch."
PACS_NOTE = "pacs.008 credit transfer notes about the charge bearer field."


def _source(source_id: str, file_name: str, message_id: str | None = None, url: str = "https://example.org/doc") -> dict:
    return {"id": source_id, "title": source_id.title(), "message_id": message_id, "url": url, "file": file_name}


def test_bundled_corpus_answers_version_question() -> None:
    result = search_documents("How do I select a message version and schema?")

    top = result["results"][0]
    assert top["source_id"] == "iso20022-catalogue-overview"
    assert top["source_url"].startswith("https://")
    assert top["score"] >= 1


def test_best_paragraph_is_returned_as_excerpt(knowledge_dir: Path) -> None:
    write_sources(knowledge_dir, [_source("general", "general.md")], {"general.md": GENERAL_NOTE})

    result = search_documents("message version schema")

    assert result["results"][0]["excerpt"] == "Select a message version and schema from the catalogue."
    assert result["results"][0]["score"] == 3


def test_stop_word_only_query_returns_nothing(knowledge_dir: Path) -> None:
    write_sources(knowledge_dir, [_source("general", "general.md")], {"general.md": GENERAL_NOTE})

    assert search_documents("what is the")["results"] == []


def test_message_id_filter_excludes_other_versions(knowledge_dir: Path) -> None:
    write_sources(
        knowledge_dir,
        [
            _source("pacs-v08", "v08.md", message_id="pacs.008.001.08"),
            _source("pacs-v10", "v10.md", message_id="pacs.008.001.10"),
            _source("generic", "generic.md"),
        ],
        {"v08.md": PACS_NOTE, "v10.md": PACS_NOTE, "generic.md": PACS_NOTE},
    )

    ids = {item["source_id"] for item in search_documents("charge bearer", "pacs.008.001.08")["results"]}

    assert ids == {"pacs-v08", "generic"}


def test_sources_outside_knowledge_dir_are_ignored(knowledge_dir: Path) -> None:
    (knowledge_dir.parent / "outside.md").write_text(PACS_NOTE, encoding="utf-8")
    write_sources(knowledge_dir, [_source("escape", "../outside.md"), _source("missing", "missing.md")], {})

    assert search_documents("charge bearer")["results"] == []


def test_non_http_urls_are_dropped(knowledge_dir: Path) -> None:
    write_sources(knowledge_dir, [_source("js", "note.md", url="javascript:alert(1)")], {"note.md": PACS_NOTE})

    assert search_documents("charge bearer")["results"][0]["source_url"] is None


def test_limit_is_respected(knowledge_dir: Path) -> None:
    sources = [_source(f"doc-{index}", f"doc{index}.md") for index in range(6)]
    write_sources(knowledge_dir, sources, {f"doc{index}.md": PACS_NOTE for index in range(6)})

    assert len(search_documents("charge bearer", limit=2)["results"]) == 2


def test_corrupt_manifest_returns_no_results(knowledge_dir: Path) -> None:
    (knowledge_dir / "sources.json").write_text("{broken", encoding="utf-8")

    assert search_documents("charge bearer") == {"query": "charge bearer", "results": []}
