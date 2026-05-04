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

STRICT_CARDIOLOGY_KEYWORDS: tuple[str, ...] = (
    "myocardial infarction",
    "angina",
    "coronary artery disease",
    "heart failure",
    "arrhythmia",
    "cardiac arrest",
    "valvular disease",
    "murmur",
    "ecg",
    "ekg",
    "echocardiography",
    "atrial fibrillation",
    "ventricular tachycardia",
    "myocarditis",
    "pericarditis",
    "cardiomyopathy",
    "endocarditis",
)

FILTER_MODE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "broad": CARDIOLOGY_KEYWORDS,
    "strict": STRICT_CARDIOLOGY_KEYWORDS,
}


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
    parser.add_argument(
        "--filter-mode",
        choices=sorted(FILTER_MODE_KEYWORDS),
        default="broad",
        help=(
            "Keyword preset to use when --keyword is not provided. 'broad' "
            "keeps the original inclusive behavior; 'strict' uses more "
            "topic-specific cardiology terms and avoids generic vital-sign "
            "triggers. Defaults to broad."
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

    return bool(matched_terms_for_record(record, keywords))


def matched_terms_for_record(
    record: Mapping[str, Any],
    keywords: Iterable[str] = CARDIOLOGY_KEYWORDS,
) -> list[str]:
    """Return the keywords that caused ``record`` to be selected."""

    text = record_text(record)
    seen: set[str] = set()
    matched: list[str] = []
    for keyword in keywords:
        normalized = keyword.lower()
        if normalized and normalized in text and normalized not in seen:
            matched.append(keyword)
            seen.add(normalized)
    return matched


def filter_cardiology_records(
    records: Iterable[Mapping[str, Any]],
    keywords: Iterable[str] = CARDIOLOGY_KEYWORDS,
) -> list[dict[str, Any]]:
    """Return cardiology-related records with matched keyword evidence."""

    keyword_tuple = tuple(keywords)
    filtered: list[dict[str, Any]] = []
    for record in records:
        matched_terms = matched_terms_for_record(record, keyword_tuple)
        if matched_terms:
            output_record = dict(record)
            output_record["matched_terms"] = matched_terms
            filtered.append(output_record)
    return filtered


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""

    args = _build_parser().parse_args(argv)
    keywords = (
        tuple(args.keyword)
        if args.keyword
        else FILTER_MODE_KEYWORDS[args.filter_mode]
    )

    try:
        records = list(read_jsonl(args.input))
    except DataIOError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    filtered = filter_cardiology_records(records, keywords)
    count = write_jsonl(args.output, filtered)

    print(f"Read from: {args.input}")
    print(f"Wrote to: {args.output}")
    print(f"Filter mode: {args.filter_mode}")
    print(f"Cardiology examples: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
