"""
KB ingestion for the RAG answer agent: extracts, chunks, embeds, and stores
regulatory source documents (currently RB-IOS 2026) into kb_documents/kb_chunks.

Chunking strategy (deliberately clause-based, not fixed-token windows):
    A legal scheme's unit of meaning is the numbered clause ("10. Grounds for
    maintainability of a Complaint"), not an arbitrary N-character window --
    slicing mid-clause risks separating a rule from the condition that
    governs it. So this script:
      1. Splits the document into its five chapters + the Annex's guidance
         section (hardcoded titles -- there are only six and re-deriving them
         from multi-line PDF headers is fragile for zero benefit).
      2. Within each, splits on top-level numbered clause headings
         ("N. Title").
      3. If a clause's text exceeds CHUNK_CHAR_LIMIT (some, like clause 14
         "Resolution of Complaints", run 4-5x longer than the rest), it is
         further split on that clause's own "(N)" sub-clause markers, greedily
         grouped back up toward the limit so we don't over-fragment.
    Every chunk is prefixed with its chapter/clause context (e.g.
    "[RB-IOS 2026 -- Chapter IV, Clause 10: Grounds for maintainability of a
    Complaint]") so it reads as a self-contained unit when retrieved in
    isolation, without needing neighboring chunks for context.

    CHUNK_CHAR_LIMIT=1000 is chosen against the embedding model's limit, not
    arbitrarily: all-MiniLM-L6-v2 truncates at 256 word-piece tokens (~ 900-
    1100 English characters). Anything longer gets silently truncated by the
    model, which would quietly throw away the end of a chunk without any
    warning -- worse than a slightly-too-eager split.

    The Annex's "Part B" (the blank fillable complaint form -- name, address,
    checkboxes) is excluded: it's a form template with no answerable content,
    just noise for retrieval.

Usage:
    python ingest_kb.py --reset   # delete existing chunks for this title, then re-ingest
    python ingest_kb.py           # add without deleting (will duplicate if re-run)
"""
from __future__ import annotations

import argparse
import os
import re

import pypdf
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session

load_dotenv()
from models import Org, KBDocument, KBChunk

PDF_PATH = "data/kb/rbios_2026.pdf"
DOC_TITLE = "Reserve Bank - Integrated Ombudsman Scheme, 2026"
DOC_SOURCE = "RBI RB-IOS 2026 (via SBI mirror of official RBI notification)"
ORG_NAME = "NovaPay Bank"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # 384-dim, matches kb_chunks.embedding column
CHUNK_CHAR_LIMIT = 1000

# Chapter titles are hardcoded rather than parsed from the PDF: they span
# inconsistent line breaks in the source text, and there are only six of them.
CHAPTERS = [
    ("I", "PRELIMINARY"),
    ("II", "OFFICES UNDER THE RESERVE BANK - INTEGRATED OMBUDSMAN SCHEME, 2026"),
    ("III", "POWERS AND FUNCTIONS OF THE RBI OMBUDSMAN/ RBI DEPUTY OMBUDSMAN"),
    ("IV", "PROCEDURE FOR REDRESSAL OF GRIEVANCE UNDER THE SCHEME"),
    ("V", "MISCELLANEOUS"),
]

CLAUSE_HEADING_RE = re.compile(r"(?m)^[ \t]*(\d{1,2})\.[ \t]+([^\n]+)")
NUMBER_RE = re.compile(r"(?m)^[ \t]*\((\d{1,2})\)[ \t]+")
LETTER_RE = re.compile(r"(?m)^[ \t]*\(([a-z])\)[ \t]+")
PAGE_NUMBER_LINE_RE = re.compile(r"(?m)^[ \t]*\d{1,3}[ \t]*\n")


def extract_raw_text(pdf_path: str) -> str:
    reader = pypdf.PdfReader(pdf_path)
    text = "\n".join(page.extract_text() for page in reader.pages)
    return PAGE_NUMBER_LINE_RE.sub("", text)


def split_clauses(section_text: str) -> list[tuple[str, str, str]]:
    """Returns (clause_number, clause_title, clause_body) for each top-level
    numbered heading found in section_text."""
    matches = list(CLAUSE_HEADING_RE.finditer(section_text))
    clauses = []
    for i, m in enumerate(matches):
        num, title = m.group(1), m.group(2).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)
        body = section_text[body_start:body_end].strip()
        clauses.append((num, title, body))
    return clauses


def split_by_marker(text: str, pattern: re.Pattern) -> list[str] | None:
    """Splits text at each occurrence of pattern. Returns None if the pattern
    doesn't occur at least twice (i.e. it wouldn't actually shrink anything)."""
    matches = list(pattern.finditer(text))
    if len(matches) < 2:
        return None
    segments = []
    lead = text[:matches[0].start()].strip()
    if lead:
        segments.append(lead)
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        segments.append(text[m.start():end].strip())
    return segments


def chunk_body(body: str, limit: int) -> list[str]:
    """Recursively shrinks an over-limit clause body, then greedily regroups
    the pieces back up toward the limit.

    Two marker levels exist because the scheme nests them differently
    depending on clause: some clauses (e.g. 14, "Resolution of Complaints")
    have several independent top-level "(N)" sub-clauses, each already
    small. Others (e.g. 3, "Definitions", or 10, "Grounds for
    maintainability") wrap everything in a single "(1)" and do their real
    subdivision with lettered "(a)(b)(c)..." points -- splitting only on
    "(N)" there would find nothing to split on and leave one giant piece.
    So: try numbered markers first, and only fall back to lettered markers
    for whichever segment is still too long after that (never the reverse --
    that would separate a numbered condition from the lettered items it's
    the parent of).
    """
    if len(body) <= limit:
        return [body]

    segments = split_by_marker(body, NUMBER_RE) or split_by_marker(body, LETTER_RE)
    if segments is None:
        # No structural marker to split on at all (rare) -- hard slice rather
        # than silently handing the model an over-limit chunk that gets
        # truncated with no warning.
        return [body[i:i + limit] for i in range(0, len(body), limit)]

    expanded = []
    for seg in segments:
        expanded.extend(chunk_body(seg, limit) if len(seg) > limit else [seg])

    grouped, current = [], ""
    for seg in expanded:
        if current and len(current) + len(seg) + 1 <= limit:
            current = f"{current}\n{seg}"
        else:
            if current:
                grouped.append(current)
            current = seg
    if current:
        grouped.append(current)
    return grouped


def make_chunks(header: str, body: str, chunks: list[str]) -> None:
    # Reserve room in the char budget for the header itself plus a
    # "(part N/M)" suffix (~15 chars is enough for any realistic M) --
    # otherwise a piece sized to fit CHUNK_CHAR_LIMIT on its own pushes the
    # final chunk (header + piece) over the model's real truncation point.
    budget = CHUNK_CHAR_LIMIT - len(header) - 15
    pieces = chunk_body(body, budget)
    for j, piece in enumerate(pieces, start=1):
        suffix = f" (part {j}/{len(pieces)})" if len(pieces) > 1 else ""
        chunks.append(f"{header}{suffix}\n{piece}")


ANNEX_HEADING_RE = re.compile(r"(?m)^Annex[ \t]*$")


def build_chunks(raw_text: str) -> list[str]:
    chapter_positions = [(roman, title, raw_text.find(f"CHAPTER {roman}")) for roman, title in CHAPTERS]
    # A plain raw_text.find("Annex") is wrong here: the word "Annex" also appears
    # inline mid-sentence in clause 11 ("...shall be in such format as specified
    # in Annex."), long before the real Annex section -- matching that instead of
    # the actual heading silently duplicated clauses 12-20 under a second,
    # mislabeled "Annex, Guidance item N" identity (caught by seeing duplicate
    # top-3 retrieval hits for the same clause text during the retrieval sanity
    # check). Anchoring to a line that is *only* "Annex" avoids the false match.
    annex_match = ANNEX_HEADING_RE.search(raw_text)
    annex_start = annex_match.start() if annex_match else len(raw_text)
    part_b_start = raw_text.find("Part B:")
    if part_b_start == -1:
        part_b_start = len(raw_text)

    bounds = [pos for _, _, pos in chapter_positions] + [annex_start, part_b_start]
    chunks: list[str] = []

    for idx, (roman, title, start) in enumerate(chapter_positions):
        end = bounds[idx + 1]
        section_text = raw_text[start:end]
        for num, clause_title, body in split_clauses(section_text):
            header = f"[RB-IOS 2026 -- Chapter {roman} ({title}), Clause {num}: {clause_title}]"
            make_chunks(header, body, chunks)

    # Annex Part A: informative guidance (real content: 30/90-day filing
    # windows, compensation caps, required documents) -- Part B (the blank
    # fillable form) is excluded by the annex_start..part_b_start slice.
    annex_text = raw_text[annex_start:part_b_start]
    for num, item_title, body in split_clauses(annex_text):
        header = f"[RB-IOS 2026 -- Annex, Guidance item {num}: {item_title}]"
        make_chunks(header, body, chunks)

    return chunks


def get_or_create_org(session: Session) -> Org:
    org = session.scalar(select(Org).where(Org.name == ORG_NAME))
    if org is None:
        raise SystemExit(f"Org '{ORG_NAME}' not found -- run seed_data.py first.")
    return org


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="delete existing chunks/doc row for this title first")
    args = parser.parse_args()

    print(f"Extracting text from {PDF_PATH} ...")
    raw_text = extract_raw_text(PDF_PATH)
    chunks = build_chunks(raw_text)
    print(f"Built {len(chunks)} chunks (char lengths: min={min(len(c) for c in chunks)}, "
          f"max={max(len(c) for c in chunks)}, avg={sum(len(c) for c in chunks) // len(chunks)}).")

    print(f"Loading embedding model {EMBEDDING_MODEL} ...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    embeddings = model.encode(chunks, show_progress_bar=True, normalize_embeddings=True)

    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        org = get_or_create_org(session)

        if args.reset:
            existing = session.scalar(select(KBDocument).where(
                KBDocument.org_id == org.id, KBDocument.title == DOC_TITLE
            ))
            if existing:
                session.execute(delete(KBChunk).where(KBChunk.document_id == existing.id))
                session.delete(existing)
                session.commit()
                print("Reset: removed previous version of this document's chunks.")

        doc = KBDocument(org_id=org.id, title=DOC_TITLE, source=DOC_SOURCE)
        session.add(doc)
        session.commit()

        kb_chunks = [
            KBChunk(document_id=doc.id, chunk_index=i, chunk_text=chunk_text, embedding=embedding.tolist())
            for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings))
        ]
        session.add_all(kb_chunks)
        session.commit()
        print(f"Inserted {len(kb_chunks)} chunks into kb_chunks for document '{DOC_TITLE}'.")


if __name__ == "__main__":
    main()
