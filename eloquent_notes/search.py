"""Semantic search over voice notes using cached Ollama embeddings.

Note vectors are computed lazily at query time and cached on disk, keyed by
file name and a digest of the embedding model plus the note text. Notes
edited outside the app, or a change of embedding model, therefore trigger
re-embedding on the next search without any explicit indexing step.
"""

import hashlib
import io
import threading
from pathlib import Path
from typing import Any

import numpy as np

from eloquent_notes import config, llm
from eloquent_notes.notes import Note

# EmbeddingGemma expects task-specific prompt prefixes.
QUERY_PROMPT = "task: search result | query: {}"
DOCUMENT_PROMPT = "title: {} | text: {}"

CACHE_PATH = str(Path(config.CACHE_DIR, "embeddings.npz"))

# Embedding similarities cluster in a narrow band (about 0.5-0.75 for
# EmbeddingGemma), so an absolute threshold alone either floods the results
# or drops good matches. Results must also be close to the best match.
RESULT_MARGIN = 0.05


def _unit(vectors: list[list[float]]) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)
    return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


class SemanticIndex:
    """Embedding cache and cosine-similarity ranking for notes."""

    def __init__(self, cache_path: str = CACHE_PATH) -> None:
        self._cache_path = cache_path
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[str, np.ndarray]] = {}
        if Path(cache_path).exists():
            with np.load(cache_path) as cache:
                self._entries = {
                    str(name): (str(digest), vector)
                    for name, digest, vector in zip(cache["names"], cache["digests"], cache["vectors"], strict=True)
                }

    def search(self, notes: list[Note], query: str, cfg: dict[str, Any]) -> list[Note]:
        """Return the notes that best match query, most similar first."""
        with self._lock:
            self._refresh(notes, cfg)
            if not notes:
                return []
            matrix = np.stack([self._entries[note.path.name][1] for note in notes])
        query_vector = _unit(self._embed([QUERY_PROMPT.format(query)], cfg))[0]
        scores = matrix @ query_vector
        cutoff = max(cfg["search"]["min_similarity"], float(scores.max()) - RESULT_MARGIN)
        ranked = sorted(zip(scores, notes, strict=True), key=lambda pair: pair[0], reverse=True)
        return [note for score, note in ranked if score >= cutoff]

    def _refresh(self, notes: list[Note], cfg: dict[str, Any]) -> None:
        """Embed notes that are new or changed and drop entries of deleted notes."""
        model = cfg["search"]["embedding_model"]
        documents = {note.path.name: DOCUMENT_PROMPT.format(note.title, note.body) for note in notes}
        digests = {
            name: hashlib.sha256(f"{model}\n{document}".encode()).hexdigest() for name, document in documents.items()
        }
        fresh = {name: entry for name, entry in self._entries.items() if digests.get(name) == entry[0]}
        dropped = len(fresh) != len(self._entries)
        stale = [name for name in digests if name not in fresh]
        if stale:
            vectors = _unit(self._embed([documents[name] for name in stale], cfg))
            fresh.update({name: (digests[name], vector) for name, vector in zip(stale, vectors, strict=True)})
        self._entries = fresh
        if stale or dropped:
            self._save()

    @staticmethod
    def _embed(texts: list[str], cfg: dict[str, Any]) -> list[list[float]]:
        return llm.embed(
            ollama_url=cfg["ai"]["ollama_url"],
            model=cfg["search"]["embedding_model"],
            texts=texts,
            keep_alive=cfg["search"]["keep_alive"],
            timeout=cfg["ai"]["request_timeout"],
        )

    def _save(self) -> None:
        if not self._entries:
            cache_file = Path(self._cache_path)
            if cache_file.exists():
                cache_file.unlink()
            return
        names = list(self._entries)
        buf = io.BytesIO()
        np.savez(
            buf,
            names=np.array(names),
            digests=np.array([self._entries[name][0] for name in names]),
            vectors=np.stack([self._entries[name][1] for name in names]),
        )
        config.atomic_write(self._cache_path, buf.getvalue())
