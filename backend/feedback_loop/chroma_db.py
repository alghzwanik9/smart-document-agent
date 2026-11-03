"""The vectors of the user's corrections, in a ChromaDB collection kept on disk next to the other data.

What is embedded is the value the system got wrong; the corrected value and the field travel as metadata. Only the
embedding function (a local ONNX model by default, downloaded once) ever sees the text: nothing is sent to a service.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("feedback_loop.chroma_db")

COLLECTION = "corrections"


@dataclass(frozen=True)
class Neighbour:
    vector_id: str
    field_name: str
    original_value: str
    corrected_value: str
    distance: float


class CorrectionStore:
    """`embedding_function` is Chroma's callable (a list of texts to a list of vectors); None means Chroma's default."""

    def __init__(self, path: Path, embedding_function=None):
        self._path = path
        self._embedding_function = embedding_function
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:    # lazy: importing and opening Chroma costs seconds the tests never need
            import chromadb
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

            self._path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self._path))
            self._collection = client.get_or_create_collection(
                COLLECTION, metadata={"hnsw:space": "cosine"},
                embedding_function=self._embedding_function or DefaultEmbeddingFunction(),
            )
        return self._collection

    def upsert(self, vector_id: str, field_name: str, original_value: str, corrected_value: str) -> None:
        self.collection.upsert(
            ids=[vector_id], documents=[original_value],
            metadatas=[{"field_name": field_name, "corrected_value": corrected_value}],
        )

    def delete(self, vector_ids: list[str]) -> None:
        if vector_ids:
            self.collection.delete(ids=vector_ids)

    def count(self) -> int:
        return self.collection.count()

    def everything(self) -> list[Neighbour]:
        """Every stored correction, at distance 0: the caller decides which ones apply."""
        reply = self.collection.get(include=["documents", "metadatas"])
        return [Neighbour(vector_id, metadata["field_name"], document, metadata["corrected_value"], 0.0)
                for vector_id, document, metadata in zip(reply["ids"], reply["documents"], reply["metadatas"])]

    def nearest(self, texts: list[str], per_text: int) -> list[Neighbour]:
        """For each text its `per_text` nearest corrections; a correction found by several texts keeps its best distance."""
        total = self.count()
        if not texts or total == 0:
            return []
        reply = self.collection.query(query_texts=texts, n_results=min(per_text, total),
                                      include=["documents", "metadatas", "distances"])
        best: dict[str, Neighbour] = {}
        for ids, documents, metadatas, distances in zip(reply["ids"], reply["documents"], reply["metadatas"],
                                                        reply["distances"]):
            for vector_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
                found = Neighbour(vector_id, metadata["field_name"], document, metadata["corrected_value"], distance)
                if vector_id not in best or distance < best[vector_id].distance:
                    best[vector_id] = found
        return sorted(best.values(), key=lambda n: n.distance)
