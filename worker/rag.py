import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_collection = None
_embedder = None

_CHUNK_SIZE = 500
_CHUNK_OVERLAP = 50
_COLLECTION_NAME = "knowledge"


def _chunk_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + _CHUNK_SIZE
        chunks.append(text[start:end])
        start += _CHUNK_SIZE - _CHUNK_OVERLAP
    return [c.strip() for c in chunks if c.strip()]


def init_rag(docs_dir: str = "rag/knowledge_base") -> None:
    global _collection, _embedder

    import chromadb
    from sentence_transformers import SentenceTransformer

    _embedder = SentenceTransformer("all-MiniLM-L6-v2")

    db_dir = os.getenv("RAG_DB_DIR", ".chroma")
    client = chromadb.PersistentClient(path=db_dir)
    _collection = client.get_or_create_collection(_COLLECTION_NAME)

    docs_path = Path(docs_dir)
    if not docs_path.exists():
        logger.warning("RAG docs dir %s not found — collection will be empty", docs_dir)
        return

    chunks = []
    ids = []
    for txt_file in sorted(docs_path.glob("*.txt")):
        text = txt_file.read_text(encoding="utf-8")
        file_chunks = _chunk_text(text)
        for i, chunk in enumerate(file_chunks):
            chunk_id = f"{txt_file.stem}_{i}"
            chunks.append(chunk)
            ids.append(chunk_id)

    if not chunks:
        logger.warning("No text chunks found in %s", docs_dir)
        return

    embeddings = _embedder.encode(chunks).tolist()
    _collection.upsert(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
    )
    logger.info("RAG initialized: %d chunks from %s", len(chunks), docs_dir)


def retrieve_context(query: str, n_results: int = 3) -> list[str]:
    if _collection is None or _embedder is None:
        return []
    query_embedding = _embedder.encode([query]).tolist()[0]
    results = _collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, _collection.count() or 1),
    )
    docs = results.get("documents", [[]])[0]
    ids = results.get("ids", [[]])[0]
    return ids if ids else []


def build_prompt(query: str) -> tuple[str, list[str]]:
    if _collection is None or _embedder is None:
        return query, []

    n_results = int(os.getenv("RAG_TOP_K", "3"))
    query_embedding = _embedder.encode([query]).tolist()[0]
    results = _collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, _collection.count() or 1),
    )
    docs = results.get("documents", [[]])[0]
    ids = results.get("ids", [[]])[0]

    if docs:
        context = "\n\n".join(docs)
        prompt = f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
    else:
        prompt = query

    return prompt, ids
