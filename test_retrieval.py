"""
One-off sanity check for the RAG pipeline: embeds a handful of realistic
customer questions and prints the top-3 nearest kb_chunks by cosine distance,
so we can eyeball whether ingestion actually retrieves the right clause
before wiring this into any agent.

Usage:
    python test_retrieval.py
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

load_dotenv()
from models import KBChunk

QUERIES = [
    "What happens if my complaint isn't resolved within 30 days?",
    "How much compensation can the RBI Ombudsman award me?",
    "Can I appeal if I'm not happy with the Ombudsman's decision?",
    "My bank never replied to my complaint, what do I do next?",
    "What kind of complaints are not accepted by the RBI Ombudsman?",
]


def main() -> None:
    model = SentenceTransformer("all-MiniLM-L6-v2")
    engine = create_engine(os.environ["DATABASE_URL"])

    lines = []
    with Session(engine) as session:
        for query in QUERIES:
            query_embedding = model.encode(query, normalize_embeddings=True).tolist()
            results = session.scalars(
                select(KBChunk)
                .order_by(KBChunk.embedding.cosine_distance(query_embedding))
                .limit(3)
            ).all()

            lines.append(f"\n=== Query: {query}")
            lines.append(f"    (got {len(results)} results)")
            for rank, chunk in enumerate(results, start=1):
                header, _, body = chunk.chunk_text.partition("\n")
                preview = body[:160].replace("\n", " ")
                lines.append(f"  [{rank}] {header}\n      {preview}...")

    with open("retrieval_results.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {len(lines)} lines to retrieval_results.txt")


if __name__ == "__main__":
    main()
