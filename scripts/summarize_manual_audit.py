#!/usr/bin/env python
"""Summarize the structured manual audit CSV.

Reads ``annotations/manual_audit_baseline_v2.csv`` and prints:

- total number of samples
- distribution of ``cardiology_relevance``
- distribution of ``topic_correctness``
- distribution of ``matched_term_role``
- distribution of ``error_type``
- distribution of ``keep_for_cardiology_dataset``
- distribution of ``keep_for_error_analysis``
- rows that contain ``unclear`` values (which fields are unclear)

The script is read-only and qualitative. It does not make medical
claims and does not compute accuracy metrics.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROJECT_ROOT / "annotations" / "manual_audit_baseline_v2.csv"

DISTRIBUTION_COLUMNS = (
    "cardiology_relevance",
    "topic_correctness",
    "matched_term_role",
    "error_type",
    "keep_for_cardiology_dataset",
    "keep_for_error_analysis",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help=f"Path to the audit CSV (default: {DEFAULT_CSV}).",
    )
    return parser.parse_args()


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Audit CSV not found: {csv_path}")
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return rows


def print_distribution(label: str, values: list[str]) -> None:
    counter = Counter(values)
    print(f"\n## {label}")
    if not counter:
        print("(no rows)")
        return
    total = sum(counter.values())
    for value, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])):
        pct = 100.0 * count / total if total else 0.0
        print(f"  {value:<32s} {count:>3d}  ({pct:5.1f}%)")


def find_unclear_rows(rows: list[dict[str, str]]) -> list[tuple[str, list[str]]]:
    unclear: list[tuple[str, list[str]]] = []
    for row in rows:
        flagged = [col for col in DISTRIBUTION_COLUMNS if row.get(col, "") == "unclear"]
        if flagged:
            sample_id = row.get("sample_id", "<no id>")
            unclear.append((sample_id, flagged))
    return unclear


def main() -> int:
    args = parse_args()
    rows = load_rows(args.csv)

    print(f"# Manual audit summary  ({args.csv.relative_to(PROJECT_ROOT)})")
    print(f"\nTotal samples: {len(rows)}")

    for column in DISTRIBUTION_COLUMNS:
        print_distribution(column, [row.get(column, "") for row in rows])

    unclear = find_unclear_rows(rows)
    print("\n## Rows with `unclear` values")
    if not unclear:
        print("  (none)")
    else:
        for sample_id, fields in unclear:
            print(f"  {sample_id}: {', '.join(fields)}")
        print(f"\n  Total rows needing manual review: {len(unclear)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
