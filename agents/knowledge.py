"""
Knowledge retrieval for the chatbot: embeds a question and returns the closest
passages from kb_chunks (RBI Ombudsman scheme clauses plus the NovaPay help
guide).

Query embeddings use fastembed's ONNX build of all-MiniLM-L6-v2, which is the
same model ingest_kb.py used with sentence-transformers, so the vectors line up
with what is already stored (checked: cosine 1.0) and the API image does not
need torch. If the embedder fails for any reason, retrieval falls back to
Postgres full-text search rather than failing the chat turn.
"""
from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from models import KBChunk, KBDocument

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_model = None
_model_lock = threading.Lock()


@dataclass
class Passage:
    id: str
    label: str      # short citation, e.g. "RB-IOS 2026, Clause 6"
    text: str       # chunk body without the bracketed header
    score: float    # cosine similarity for vector search, ts_rank for the fallback
    method: str     # "vector" or "fulltext"


def _embedder():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from fastembed import TextEmbedding

                _model = TextEmbedding(EMBEDDING_MODEL, cache_dir=os.environ.get("FASTEMBED_CACHE_PATH"))
    return _model


def embed_query(query: str) -> list[float]:
    return [float(x) for x in next(iter(_embedder().embed([query])))]


_HEADER = re.compile(r"^\[(.+?)\]\s*(.*)$", re.DOTALL)
_CLAUSE = re.compile(r"Clause\s+(\d+[A-Za-z]?)")


def _split_chunk(chunk_text: str) -> tuple[str, str]:
    m = _HEADER.match(chunk_text)
    return (m.group(1), m.group(2).strip()) if m else ("", chunk_text.strip())


def _label(header: str) -> str:
    source = header.split(" -- ")[0].strip() or "Knowledge base"
    clause = _CLAUSE.search(header)
    if clause:
        return f"{source}, Clause {clause.group(1)}"
    topic = header.split(" -- ", 1)[1].strip() if " -- " in header else ""
    if len(topic) > 60:
        topic = topic[:57].rstrip() + "..."
    return f"{source}: {topic}" if topic else source


def _to_passage(chunk_id, chunk_text: str, score: float, method: str) -> Passage:
    header, body = _split_chunk(chunk_text)
    return Passage(id=str(chunk_id), label=_label(header), text=body, score=score, method=method)


def search(session: Session, query: str, org_id, k: int = 4) -> list[Passage]:
    try:
        vec = embed_query(query)
    except Exception:
        return _fulltext_search(session, query, org_id, k)

    distance = KBChunk.embedding.cosine_distance(vec)
    rows = session.execute(
        select(KBChunk.id, KBChunk.chunk_text, distance)
        .join(KBDocument, KBDocument.id == KBChunk.document_id)
        .where(KBDocument.org_id == org_id)
        .order_by(distance)
        .limit(k)
    ).all()
    return [_to_passage(r[0], r[1], 1.0 - float(r[2]), "vector") for r in rows]


def _fulltext_search(session: Session, query: str, org_id, k: int) -> list[Passage]:
    rows = session.execute(
        text(
            """
            select c.id, c.chunk_text,
                   ts_rank(to_tsvector('english', c.chunk_text), plainto_tsquery('english', :q)) as rank
            from kb_chunks c join kb_documents d on d.id = c.document_id
            where d.org_id = :org and to_tsvector('english', c.chunk_text) @@ plainto_tsquery('english', :q)
            order by rank desc limit :k
            """
        ),
        {"q": query, "org": str(org_id), "k": k},
    ).all()
    return [_to_passage(r[0], r[1], float(r[2]), "fulltext") for r in rows]
