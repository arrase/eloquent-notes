"""Unit tests for eloquent_notes.search (semantic search with cached embeddings)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

from eloquent_notes import config, notes
from eloquent_notes.search import DOCUMENT_PROMPT, QUERY_PROMPT, SemanticIndex

CFG: dict[str, Any] = {
    "ai": {"ollama_url": "http://localhost:11434", "request_timeout": 30},
    "search": {"embedding_model": "embed", "keep_alive": "5m", "min_similarity": 0.5},
}

# Toy embedding space: each note title maps to a direction.
VECTORS = {
    "Backups": [1.0, 0.0, 0.0],
    "Groceries": [0.0, 1.0, 0.0],
    "Holidays": [0.0, 0.0, 2.0],
}
QUERIES = {
    "copias de seguridad": [0.9, 0.1, 0.0],
    "food": [0.2, 1.0, 0.0],
    "mixed": [1.0, 0.95, 0.0],
    "leaning": [1.0, 0.8, 0.0],
}


def fake_embed(
    ollama_url: str,
    model: str,
    texts: list[str],
    keep_alive: str,
    timeout: int,
) -> list[list[float]]:
    del ollama_url, model, keep_alive, timeout
    vectors = []
    for text in texts:
        if text.startswith("task: search result | query: "):
            vectors.append(QUERIES[text.removeprefix("task: search result | query: ")])
        else:
            title = text.removeprefix("title: ").split(" | ")[0]
            vectors.append(VECTORS[title])
    return vectors


@pytest.fixture
def note_list(tmp_path: Path) -> list[notes.Note]:
    created = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)
    result = []
    for title in VECTORS:
        note = notes.Note(tmp_path / "notes" / f"{title}.md", title, created, "note", [], f"About {title}")
        notes.save_note(note)
        result.append(note)
    return result


def test_search_ranks_by_similarity_and_applies_threshold(tmp_path: Path, note_list: list[notes.Note]) -> None:
    index = SemanticIndex(str(tmp_path / "cache.npz"))

    with patch("eloquent_notes.search.llm.embed", side_effect=fake_embed) as mock_embed:
        results = index.search(note_list, "copias de seguridad", CFG)

    assert [note.title for note in results] == ["Backups"]
    first_call = mock_embed.call_args_list[0].kwargs
    assert first_call["texts"] == [DOCUMENT_PROMPT.format(n.title, n.body) for n in note_list]
    assert first_call["model"] == "embed"
    assert first_call["keep_alive"] == "5m"
    assert first_call["timeout"] == 30
    assert mock_embed.call_args_list[1].kwargs["texts"] == [QUERY_PROMPT.format("copias de seguridad")]


def test_results_must_be_close_to_the_best_match(tmp_path: Path, note_list: list[notes.Note]) -> None:
    index = SemanticIndex(str(tmp_path / "cache.npz"))

    with patch("eloquent_notes.search.llm.embed", side_effect=fake_embed):
        mixed = index.search(note_list, "mixed", CFG)
        leaning = index.search(note_list, "leaning", CFG)

    # Both notes clear min_similarity; only the near-tie keeps the runner-up
    assert [note.title for note in mixed] == ["Backups", "Groceries"]
    assert [note.title for note in leaning] == ["Backups"]


def test_search_reuses_cache_across_instances(tmp_path: Path, note_list: list[notes.Note]) -> None:
    cache_path = str(tmp_path / "cache" / "embeddings.npz")
    with (
        patch("eloquent_notes.search.llm.embed", side_effect=fake_embed),
        patch("eloquent_notes.search.config.atomic_write", wraps=config.atomic_write) as mock_atomic,
    ):
        SemanticIndex(cache_path).search(note_list, "food", CFG)

    mock_atomic.assert_called_once()
    assert mock_atomic.call_args.args[0] == cache_path
    assert isinstance(mock_atomic.call_args.args[1], bytes)

    with patch("eloquent_notes.search.llm.embed", side_effect=fake_embed) as mock_embed:
        results = SemanticIndex(cache_path).search(note_list, "food", CFG)

    assert [note.title for note in results] == ["Groceries"]
    # Only the query is embedded: every note vector came from the cache
    assert mock_embed.call_count == 1


def test_search_reembeds_only_changed_notes(tmp_path: Path, note_list: list[notes.Note]) -> None:
    index = SemanticIndex(str(tmp_path / "cache.npz"))
    with patch("eloquent_notes.search.llm.embed", side_effect=fake_embed):
        index.search(note_list, "food", CFG)

    note_list[1].body = "Changed body"
    with patch("eloquent_notes.search.llm.embed", side_effect=fake_embed) as mock_embed:
        index.search(note_list, "food", CFG)

    assert mock_embed.call_args_list[0].kwargs["texts"] == [DOCUMENT_PROMPT.format("Groceries", "Changed body")]


def test_changing_embedding_model_reembeds_everything(tmp_path: Path, note_list: list[notes.Note]) -> None:
    index = SemanticIndex(str(tmp_path / "cache.npz"))
    with patch("eloquent_notes.search.llm.embed", side_effect=fake_embed):
        index.search(note_list, "food", CFG)

    other_cfg: dict[str, Any] = {**CFG, "search": {**CFG["search"], "embedding_model": "other"}}
    with patch("eloquent_notes.search.llm.embed", side_effect=fake_embed) as mock_embed:
        index.search(note_list, "food", other_cfg)

    assert len(mock_embed.call_args_list[0].kwargs["texts"]) == 3


def test_deleted_notes_are_dropped_from_cache(tmp_path: Path, note_list: list[notes.Note]) -> None:
    cache_path = tmp_path / "cache.npz"
    index = SemanticIndex(str(cache_path))
    with patch("eloquent_notes.search.llm.embed", side_effect=fake_embed):
        index.search(note_list, "food", CFG)
        results = index.search(note_list[1:], "food", CFG)

    assert [note.title for note in results] == ["Groceries"]
    with np.load(cache_path) as cache:
        assert sorted(cache["names"]) == ["Groceries.md", "Holidays.md"]

    assert index.search([], "food", CFG) == []
    assert not cache_path.exists()


def test_search_without_notes_skips_ollama(tmp_path: Path) -> None:
    with patch("eloquent_notes.search.llm.embed") as mock_embed:
        assert SemanticIndex(str(tmp_path / "cache.npz")).search([], "anything", CFG) == []
    mock_embed.assert_not_called()


def test_search_propagates_ollama_errors(tmp_path: Path, note_list: list[notes.Note]) -> None:
    index = SemanticIndex(str(tmp_path / "cache.npz"))

    with patch("eloquent_notes.search.llm.embed", side_effect=ConnectionError("down")), pytest.raises(ConnectionError):
        index.search(note_list, "food", CFG)
