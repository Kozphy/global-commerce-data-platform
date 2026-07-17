from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sklearn.feature_extraction.text import HashingVectorizer, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from banking_ai.models import Evidence


@dataclass(frozen=True)
class PolicyDocument:
    document_id: str
    title: str
    content: str


@dataclass(frozen=True)
class PolicyChunk:
    document_id: str
    chunk_id: str
    title: str
    text: str


class PolicyStore(Protocol):
    def search(self, query: str, top_k: int = 4) -> list[Evidence]: ...


def chunk_document(document: PolicyDocument, max_chars: int = 900) -> list[PolicyChunk]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", document.content) if p.strip()]
    chunks: list[PolicyChunk] = []
    buffer = ""

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        index = len(chunks)
        chunks.append(
            PolicyChunk(
                document_id=document.document_id,
                chunk_id=f"{document.document_id}-chunk-{index}",
                title=document.title,
                text=buffer.strip(),
            )
        )
        buffer = ""

    for paragraph in paragraphs:
        if buffer and len(buffer) + len(paragraph) + 2 > max_chars:
            flush()
        if len(paragraph) > max_chars:
            for sentence in re.split(r"(?<=[.!?。！？])\s+", paragraph):
                if buffer and len(buffer) + len(sentence) + 1 > max_chars:
                    flush()
                buffer = f"{buffer} {sentence}".strip()
        else:
            buffer = f"{buffer}\n\n{paragraph}".strip()
    flush()
    return chunks


def load_policy_documents(directory: Path) -> list[PolicyDocument]:
    documents: list[PolicyDocument] = []
    if not directory.exists():
        return documents
    for path in sorted(directory.glob("*.md")):
        documents.append(
            PolicyDocument(
                document_id=path.stem,
                title=path.stem.replace("_", " ").title(),
                content=path.read_text(encoding="utf-8"),
            )
        )
    return documents


class TfidfPolicyStore:
    def __init__(self, documents: list[PolicyDocument]) -> None:
        self.chunks = [chunk for document in documents for chunk in chunk_document(document)]

    def search(self, query: str, top_k: int = 4) -> list[Evidence]:
        if not self.chunks:
            return []
        corpus = [chunk.text for chunk in self.chunks]
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        matrix = vectorizer.fit_transform([*corpus, query])
        scores = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
        ranked = scores.argsort()[::-1][:top_k]
        return [
            Evidence(
                document_id=self.chunks[int(index)].document_id,
                chunk_id=self.chunks[int(index)].chunk_id,
                title=self.chunks[int(index)].title,
                text=self.chunks[int(index)].text,
                score=max(0.0, min(1.0, float(scores[index]))),
            )
            for index in ranked
            if scores[index] > 0
        ]


class QdrantPolicyStore:
    """Qdrant-backed policy retrieval with deterministic local hashing vectors."""

    vector_size = 384

    def __init__(
        self,
        documents: list[PolicyDocument],
        *,
        url: str | None = None,
        api_key: str | None = None,
        collection: str = "bank_policy_chunks",
    ) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, PointStruct, VectorParams

        self.collection = collection
        self.vectorizer = HashingVectorizer(
            n_features=self.vector_size,
            alternate_sign=False,
            norm="l2",
            ngram_range=(1, 2),
        )
        self.client = QdrantClient(url=url, api_key=api_key) if url else QdrantClient(":memory:")
        if not self.client.collection_exists(collection):
            self.client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )
        chunks = [chunk for document in documents for chunk in chunk_document(document)]
        if chunks:
            vectors = self.vectorizer.transform([chunk.text for chunk in chunks]).toarray()
            points = [
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id)),
                    vector=vector.tolist(),
                    payload={
                        "document_id": chunk.document_id,
                        "chunk_id": chunk.chunk_id,
                        "title": chunk.title,
                        "text": chunk.text,
                    },
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
            self.client.upsert(collection_name=collection, wait=True, points=points)

    def search(self, query: str, top_k: int = 4) -> list[Evidence]:
        vector = self.vectorizer.transform([query]).toarray()[0].tolist()
        points = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            with_payload=True,
            limit=top_k,
        ).points
        evidence: list[Evidence] = []
        for point in points:
            payload = point.payload or {}
            evidence.append(
                Evidence(
                    document_id=str(payload.get("document_id", "unknown")),
                    chunk_id=str(payload.get("chunk_id", point.id)),
                    title=str(payload.get("title", "Policy")),
                    text=str(payload.get("text", "")),
                    score=max(0.0, min(1.0, float(point.score))),
                )
            )
        return evidence


def build_policy_store(
    documents: list[PolicyDocument], *, url: str | None = None, api_key: str | None = None
) -> PolicyStore:
    try:
        return QdrantPolicyStore(documents, url=url, api_key=api_key)
    except (ImportError, RuntimeError, ValueError):
        return TfidfPolicyStore(documents)
