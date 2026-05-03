#!/usr/bin/env python
"""Prepare a tiny cardiology-focused MedQA JSONL sample.

This is a placeholder preprocessing script for research prototyping. It filters
JSONL records with simple cardiology keywords and writes the matching records
to ``data/processed/medqa_cardiology_sample.jsonl``. The full MedQA dataset is
not bundled with this repository.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DEFAULT_INPUT = PROJECT_ROOT / "data" / "raw" / "medqa_sample.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "medqa_cardiology_sample.jsonl"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_io import DataIOError, read_jsonl, write_jsonl  # noqa: E402


CARDIOLOGY_KEYWORDS: tuple[str, ...] = (
    "heart",
    "cardiac",
    "coronary",
    "myocardial",
    "hypertension",
    "arrhythmia",
    "angina",
    "infarction",
    "valve",
    "cardiomyopathy",
    "artery",
    "blood pressure",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Filter a MedQA-style JSONL file for cardiology examples."
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        type=Path,
        help="Input JSONL file. Defaults to data/raw/medqa_sample.jsonl.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        type=Path,
        help="Output JSONL file for filtered cardiology examples.",
    )
    parser.add_argument(
        "--keyword",
        action="append",
        default=None,
        help=(
            "Override the default cardiology keyword list. Pass once per keyword "
            "to filter on a custom vocabulary."
        ),
    )
    return parser


def record_text(record: Mapping[str, Any]) -> str:
    """Collect searchable text from common MedQA fields, lowercased."""

    parts: list[str] = [
        str(record.get("question", "")),
        str(record.get("answer", "")),
        str(record.get("answer_idx", "")),
        str(record.get("explanation", "")),
    ]

    options = record.get("options")
    if isinstance(options, dict):
        parts.extend(str(value) for value in options.values())
    elif isinstance(options, list):
        parts.extend(str(value) for value in options)

    return " ".join(parts).lower()


def is_cardiology_related(
    record: Mapping[str, Any],
    keywords: Iterable[str] = CARDIOLOGY_KEYWORDS,
) -> bool:
    """Return True when ``record`` mentions any of ``keywords``."""

    text = record_text(record)
    return any(keyword.lower() in text for keyword in keywords)


def filter_cardiology_records(
    records: Iterable[Mapping[str, Any]],
    keywords: Iterable[str] = CARDIOLOGY_KEYWORDS,
) -> list[dict[str, Any]]:
    """Return only the records that look cardiology-related."""

    keyword_tuple = tuple(keywords)
    return [dict(record) for record in records if is_cardiology_related(record, keyword_tuple)]


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""

    args = _build_parser().parse_args(argv)
    keywords = tuple(args.keyword) if args.keyword else CARDIOLOGY_KEYWORDS

    try:
        records = list(read_jsonl(args.input))
    except DataIOError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    filtered = filter_cardiology_records(records, keywords)
    count = write_jsonl(args.output, filtered)

    print(f"Read from: {args.input}")
    print(f"Wrote to: {args.output}")
    print(f"Cardiology examples: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
