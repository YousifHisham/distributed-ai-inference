from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.logging_config import setup_logging

logger = setup_logging("rag")


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    source: str
    chunk_id: str
    score: float


class HashEmbeddingFunction:
    """Small local embedding function so ChromaDB works offline during demos."""

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def __call__(self, input: list[str]) -> list[list[float]]:  # Chroma expects this parameter name.
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class ChromaRetriever:
    def __init__(
        self,
        docs_dir: str | Path = "rag/knowledge_base",
        db_dir: str | Path = ".chroma",
        collection_name: str = "project_knowledge",
        chunk_chars: int = 700,
    ):
        self.docs_dir = Path(docs_dir)
        self.db_dir = Path(db_dir)
        self.collection_name = collection_name
        self.chunk_chars = chunk_chars
        self.embedding_function = HashEmbeddingFunction()
        self._collection: Any | None = None
        self._fallback_chunks: list[RetrievedChunk] = []
        self.backend = "memory"

    def initialize(self) -> None:
        chunks = self._load_chunks()
        self._fallback_chunks = chunks
        if not chunks:
            logger.warning(f"No RAG documents found in {self.docs_dir}")
            return

        try:
            os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
            logging.getLogger("chromadb").setLevel(logging.CRITICAL)
            logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)
            import chromadb
            from chromadb.config import Settings

            self.db_dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(
                path=str(self.db_dir),
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function,
            )
            self._collection.upsert(
                ids=[chunk.chunk_id for chunk in chunks],
                documents=[chunk.text for chunk in chunks],
                metadatas=[{"source": chunk.source} for chunk in chunks],
            )
            self.backend = "chromadb"
            logger.info(
                f"RAG initialized with ChromaDB collection '{self.collection_name}' "
                f"({len(chunks)} chunks)"
            )
        except Exception as exc:
            self._collection = None
            self.backend = "memory"
            logger.warning(f"ChromaDB unavailable; using in-memory RAG fallback: {exc}")

    def retrieve(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        if not query.strip():
            return []

        if self._collection is not None:
            result = self._collection.query(
                query_texts=[query],
                n_results=max(top_k, 1),
                include=["documents", "metadatas", "distances"],
            )
            documents = result.get("documents", [[]])[0]
            metadatas = result.get("metadatas", [[]])[0]
            distances = result.get("distances", [[]])[0]
            ids = result.get("ids", [[]])[0]
            return [
                RetrievedChunk(
                    text=doc,
                    source=(meta or {}).get("source", "unknown"),
                    chunk_id=ids[index] if index < len(ids) else f"chunk-{index}",
                    score=1.0 / (1.0 + float(distances[index])) if index < len(distances) else 0.0,
                )
                for index, (doc, meta) in enumerate(zip(documents, metadatas))
            ]

        return self._retrieve_from_memory(query, top_k)

    def build_prompt(self, query: str, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return query

        context = "\n\n".join(
            f"Source: {chunk.source}\n{chunk.text}" for chunk in chunks
        )
        return (
            "Use the retrieved context to answer the user question. "
            "If the context is not relevant, say so briefly and answer from general knowledge.\n\n"
            f"Retrieved context:\n{context}\n\n"
            f"User question:\n{query}\n\n"
            "Answer:"
        )

    def _retrieve_from_memory(self, query: str, top_k: int) -> list[RetrievedChunk]:
        query_vector = self.embedding_function([query])[0]
        scored = [
            (self._cosine_similarity(query_vector, self.embedding_function([chunk.text])[0]), chunk)
            for chunk in self._fallback_chunks
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievedChunk(
                text=chunk.text,
                source=chunk.source,
                chunk_id=chunk.chunk_id,
                score=score,
            )
            for score, chunk in scored[:top_k]
            if score > 0
        ]

    def _load_chunks(self) -> list[RetrievedChunk]:
        chunks: list[RetrievedChunk] = []
        if not self.docs_dir.exists():
            return chunks

        for path in sorted(self.docs_dir.glob("*.txt")):
            text = path.read_text(encoding="utf-8").strip()
            for index, chunk in enumerate(self._split_text(text)):
                chunks.append(
                    RetrievedChunk(
                        text=chunk,
                        source=path.name,
                        chunk_id=f"{path.stem}-{index}",
                        score=0.0,
                    )
                )
        return chunks

    def _split_text(self, text: str) -> list[str]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(current) + len(paragraph) + 2 <= self.chunk_chars:
                current = f"{current}\n\n{paragraph}".strip()
            else:
                if current:
                    chunks.append(current)
                current = paragraph
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        return sum(a * b for a, b in zip(left, right))
