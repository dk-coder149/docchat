"""RAG ka retrieval hissa: ChromaDB mein chunks store, search aur delete karna.

Har chunk ke saath metadata (user_id, document_id, filename) jata hai,
taaki ek user ko kabhi dusre user ke documents na mile.
"""
import logging

import chromadb

from app.config import settings

logger = logging.getLogger(__name__)

_client = None
_collection = None
_embedding_fn = None  # None = ChromaDB ka default embedding model


def configure(embedding_fn=None) -> None:
    """Testing ke liye: nakli embedding function lagana. Purana collection reset ho jata hai."""
    global _client, _collection, _embedding_fn
    _client = None
    _collection = None
    _embedding_fn = embedding_fn


def get_collection():
    """Collection ek baar banta hai, phir wahi use hota hai."""
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=settings.chroma_path)
        kwargs = {"embedding_function": _embedding_fn} if _embedding_fn is not None else {}
        _collection = _client.get_or_create_collection("docchat", **kwargs)
    return _collection


def add_chunks(user_id: int, document_id: int, filename: str, chunks: list[str]) -> None:
    collection = get_collection()
    batch = 100  # bade document ko tukdon mein add karo
    for i in range(0, len(chunks), batch):
        part = chunks[i : i + batch]
        collection.add(
            ids=[f"{document_id}-{i + j}" for j in range(len(part))],
            documents=part,
            metadatas=[
                {"user_id": user_id, "document_id": document_id, "filename": filename}
                for _ in part
            ],
        )


def search(user_id: int, query: str, top_k: int, document_id: int | None = None) -> list[dict]:
    """Sirf is user ke (aur chaho to ek hi document ke) sabse milte-julte chunks."""
    where: dict = {"user_id": user_id}
    if document_id is not None:
        where = {"$and": [{"user_id": user_id}, {"document_id": document_id}]}

    res = get_collection().query(query_texts=[query], n_results=top_k, where=where)
    docs = res["documents"][0] if res.get("documents") else []
    metas = res["metadatas"][0] if res.get("metadatas") else []
    return [
        {"text": text, "document_id": meta["document_id"], "filename": meta["filename"]}
        for text, meta in zip(docs, metas)
    ]


def delete_document_chunks(document_id: int) -> None:
    get_collection().delete(where={"document_id": document_id})
