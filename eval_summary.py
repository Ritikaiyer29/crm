"""
Aggregates every result logged to eval_log.csv (by any number of separate
run_eval.py invocations -- each --offset resume, each rate-limit-interrupted
run) into one cumulative report.

Dedup is by (ticket_id, model), keeping the latest logged row: if a ticket
was ever evaluated twice for the same model (e.g. overlapping --offset
ranges from a run before ordering was made deterministic), the newer result
wins rather than double-counting it.

Usage:
    python eval_summary.py                          # default model
    python eval_summary.py --model openai/gpt-oss-20b
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from agents.triage_agent import GROQ_MODEL
from run_eval import LOG_PATH, print_report

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=GROQ_MODEL)
    args = parser.parse_args()

    if not LOG_PATH.exists():
        raise SystemExit(f"{LOG_PATH} doesn't exist yet -- run run_eval.py at least once first.")

    latest_by_ticket: dict[str, dict] = {}
    with LOG_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["model"] != args.model:
                continue
            latest_by_ticket[row["ticket_id"]] = row  # later rows overwrite earlier ones for the same ticket

    rows = list(latest_by_ticket.values())
    if not rows:
        raise SystemExit(f"No logged results for model {args.model} in {LOG_PATH}.")

    correct = 0
    no_match = 0
    per_category_total: Counter[str] = Counter()
    per_category_correct: Counter[str] = Counter()
    confusion: Counter[tuple[str, str]] = Counter()
    confidence_correct: list[float] = []
    confidence_incorrect: list[float] = []

    for row in rows:
        truth_name = row["truth_category"]
        predicted_name = row["predicted_category"]
        is_correct = row["correct"] == "True"
        confidence = float(row["confidence"])

        per_category_total[truth_name] += 1
        if predicted_name == "(NO MATCH)":
            no_match += 1
        if is_correct:
            correct += 1
            per_category_correct[truth_name] += 1
            confidence_correct.append(confidence)
        else:
            confusion[(truth_name, predicted_name)] += 1
            confidence_incorrect.append(confidence)

    print(f"Aggregated {len(rows)} unique ticket evaluations for model {args.model} "
          f"from {LOG_PATH} (across all runs so far).\n")

    print_report(
        model=args.model,
        evaluated=len(rows),
        intended_total=800,  # the full seeded dataset size
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
