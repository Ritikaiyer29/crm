"""
Eval harness: measures the triage agent's category-classification accuracy
against seeded_category_id, the immutable ground-truth label set at seed
time (never overwritten by the approval flow -- see schema.sql/models.py).

This calls classify_ticket() directly, not run_triage(): an eval pass over
hundreds of tickets has no business writing hundreds of phantom "pending
approval" rows into agent_actions.

What this reports, and why:
  - Overall accuracy: the headline number.
  - Per-category accuracy: some categories (especially "Other", the NCH
    taxonomy's genuine catch-all) are inherently harder to separate from
    their nearest neighbor even for a human -- see seed_data.py's
    DEFAULT_TEMPLATES comment. Reporting per-category numbers rather than
    only the overall average makes that visible instead of burying it.
  - Confusion pairs: which (true, predicted) category mix-ups actually
    happen, so a low score comes with an explanation, not just a number.
  - Confidence calibration: mean self-reported confidence on correct vs.
    incorrect predictions. A well-calibrated classifier should be less
    confident when it's wrong -- worth checking rather than assuming.

Groq enforces per-model daily token limits on the free tier, and a run over
hundreds of tickets can hit that mid-run (this happened on the first full
run against gpt-oss-120b: it failed with an unhandled RateLimitError at
ticket 101/800 and the original version of this script had no partial-
results handling, so all 100 already-classified tickets' data was lost with
it). This version catches that specifically, prints the report for whatever
was completed instead of losing it, and --model lets you point a run at a
different model (Groq tracks quota per-model, so this doubles as a way to
keep testing today instead of waiting for a reset).

Every per-ticket result is also appended to eval_log.csv as it happens (not
buffered until the end), separately from the in-memory summary this process
prints. That's what makes resuming across Groq's rolling daily limit
actually add up to a real full-dataset number instead of five disconnected
partial reports: run eval_summary.py afterward to aggregate every logged
result (deduped per ticket+model, keeping the latest) into one report,
regardless of how many separate --offset runs it took to get there.

Usage:
    python run_eval.py --limit 100                    # quick pilot run
    python run_eval.py                                 # full run, default model
    python run_eval.py --offset 189                    # resume after a partial run
    python run_eval.py --model openai/gpt-oss-20b       # full run, different model
    python eval_summary.py                             # aggregate every run so far
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from groq import RateLimitError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

load_dotenv()
from agents.triage_agent import GROQ_MODEL, classify_ticket
from models import GrievanceCategory, Ticket

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

LOG_PATH = Path("eval_log.csv")
LOG_FIELDS = ["ticket_id", "model", "truth_category", "predicted_category", "correct", "confidence", "evaluated_at"]


def _append_log(row: dict) -> None:
    is_new = not LOG_PATH.exists()
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def print_report(
    model: str,
    evaluated: int,
    intended_total: int,
    correct: int,
    no_match: int,
    per_category_total: Counter,
    per_category_correct: Counter,
    confusion: Counter,
    confidence_correct: list[float],
    confidence_incorrect: list[float],
) -> None:
    overall_accuracy = correct / evaluated if evaluated else 0.0

    print(f"\n{'=' * 70}")
    print(f"MODEL: {model}")
    if evaluated < intended_total:
        print(f"PARTIAL RUN: {evaluated}/{intended_total} tickets evaluated before stopping")
    print(f"OVERALL ACCURACY: {overall_accuracy:.2%}  ({correct}/{evaluated})")
    print(f"NO MATCH (model's category name matched nothing real): {no_match}")
    print(f"{'=' * 70}")

    print("\nPer-category accuracy (sorted by support):")
    for name, total_n in per_category_total.most_common():
        acc = per_category_correct[name] / total_n
        print(f"  {name:<58} {per_category_correct[name]:>4}/{total_n:<4} ({acc:.1%})")

    print("\nTop confusion pairs (true -> predicted):")
    for (truth, predicted), count in confusion.most_common(10):
        print(f"  {count:>3}x  {truth}  ->  {predicted}")

    if confidence_correct:
        print(f"\nMean self-reported confidence when correct:   {sum(confidence_correct)/len(confidence_correct):.3f}")
    if confidence_incorrect:
        print(f"Mean self-reported confidence when incorrect: {sum(confidence_incorrect)/len(confidence_incorrect):.3f}")


def _discover_api_keys() -> list[str]:
    """GROQ_API_KEY, then GROQ_API_KEY_2, GROQ_API_KEY_3, ... in that order,
    for whichever of those env vars are actually set. Multiple keys are
    separate Groq accounts/orgs with independent daily quotas -- rate limits
    are enforced per-org (confirmed from the org_id in every 429 we've hit),
    not per-key, so this only helps because each one is a different account."""
    keys = [os.environ["GROQ_API_KEY"]]
    i = 2
    while f"GROQ_API_KEY_{i}" in os.environ:
        keys.append(os.environ[f"GROQ_API_KEY_{i}"])
        i += 1
    return keys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="evaluate only the first N tickets (after --offset)")
    parser.add_argument("--offset", type=int, default=0,
                         help="skip the first N tickets -- for resuming across Groq's rolling daily "
                              "token limit without re-spending quota on tickets already evaluated")
    parser.add_argument("--model", default=GROQ_MODEL, help="Groq model to evaluate (default: production model)")
    args = parser.parse_args()

    api_keys = _discover_api_keys()
    key_index = 0
    if len(api_keys) > 1:
        print(f"Found {len(api_keys)} Groq API keys -- will rotate to the next one if the current one hits its daily limit.")

    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        categories = {c.id: c.category_name for c in session.scalars(select(GrievanceCategory)).all()}

        # Explicit, stable ordering is required (not just nice-to-have) for
        # --offset to correctly resume across separate invocations: Postgres
        # doesn't guarantee row order across queries without an ORDER BY, so
        # skipping "the first N" would be unsafe without one.
        # Real customer-submitted tickets (see api/routers/public.py) have no
        # ground truth -- seeded_category_id is NULL for those -- so exclude
        # them rather than silently scoring against a category they were
        # never actually labeled with.
        query = (
            select(Ticket)
            .where(Ticket.seeded_category_id.isnot(None))
            .order_by(Ticket.created_at, Ticket.id)
            .offset(args.offset)
        )
        if args.limit:
            query = query.limit(args.limit)
        tickets = session.scalars(query).all()

        print(f"Evaluating {len(tickets)} tickets against seeded_category_id, model={args.model}...\n")

        correct = 0
        no_match = 0
        evaluated = 0
        per_category_total: Counter[str] = Counter()
        per_category_correct: Counter[str] = Counter()
        confusion: Counter[tuple[str, str]] = Counter()
        confidence_correct: list[float] = []
        confidence_incorrect: list[float] = []

        try:
            i = 0
            while i < len(tickets):
                ticket = tickets[i]
                truth_name = categories[ticket.seeded_category_id]

                try:
                    classification = classify_ticket(
                        session, ticket, model=args.model, api_key=api_keys[key_index]
                    )
                except RateLimitError:
                    failed_key_num = key_index + 1
                    if key_index + 1 < len(api_keys):
                        key_index += 1
                        print(f"  Key {failed_key_num} hit its daily limit -- switching to key {key_index + 1} "
                              f"and retrying ticket {i + 1} (not skipping it).")
                        continue  # retry the same ticket (i unchanged) with the next key
                    raise  # all keys exhausted -- let the outer handler report what we have

                i += 1
                evaluated = i

                per_category_total[truth_name] += 1
                if classification.matched is None:
                    no_match += 1
                    predicted_name = "(NO MATCH)"
                else:
                    predicted_name = classification.matched.category_name

                is_correct = (
                    classification.matched is not None
                    and classification.matched.id == ticket.seeded_category_id
                )
                if is_correct:
                    correct += 1
                    per_category_correct[truth_name] += 1
                    confidence_correct.append(classification.confidence)
                else:
                    confusion[(truth_name, predicted_name)] += 1
                    confidence_incorrect.append(classification.confidence)

                # Written immediately, not batched -- so a mid-run crash still
                # leaves every ticket evaluated up to that point safely on disk.
                _append_log({
                    "ticket_id": str(ticket.id),
                    "model": args.model,
                    "truth_category": truth_name,
                    "predicted_category": predicted_name,
                    "correct": is_correct,
                    "confidence": classification.confidence,
                    "evaluated_at": datetime.now(timezone.utc).isoformat(),
                })

                if i % 50 == 0:
                    print(f"  ...{i}/{len(tickets)} done, running accuracy: {correct / i:.1%}")
        except RateLimitError as e:
            print(f"\nStopped early: Groq rate limit hit on model {args.model} after {evaluated} tickets.")
            print(f"  ({e})")
            print("Reporting results for what was actually completed, not discarding it.")

        print_report(
            model=args.model,
            evaluated=evaluated,
            intended_total=len(tickets),
            correct=correct,
            no_match=no_match,
            per_category_total=per_category_total,
            per_category_correct=per_category_correct,
            confusion=confusion,
            confidence_correct=confidence_correct,
            confidence_incorrect=confidence_incorrect,
        )


if __name__ == "__main__":
    main()
