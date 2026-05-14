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

HIGH_CONFIDENCE_DISEASE_TERMS: tuple[str, ...] = (
    "myocardial infarction",
    "heart failure",
    "angina",
    "coronary artery disease",
    "endocarditis",
    "myocarditis",
    "pericarditis",
    "cardiomyopathy",
    "atrial fibrillation",
    "cardiac arrest",
    "aortic stenosis",
    "mitral regurgitation",
    "mitral valve prolapse",
    "mitral prolapse",
    "patent ductus arteriosus",
    "pda",
    "tetralogy of fallot",
    "tof",
    "coarctation of the aorta",
    "aortic coarctation",
    "coarctation",
    "pulmonary embolism",
    "pulmonary embolus",
)

HIGH_CONFIDENCE_ECG_TERMS: tuple[str, ...] = ("ecg", "ekg")
HIGH_CONFIDENCE_ECG_CONTEXT_TERMS: tuple[str, ...] = (
    "st elevation",
    "atrial fibrillation",
    "ventricular tachycardia",
    "qt prolongation",
    "absent p waves",
)

HIGH_CONFIDENCE_MURMUR_TERMS: tuple[str, ...] = ("murmur",)
HIGH_CONFIDENCE_MURMUR_CONTEXT_TERMS: tuple[str, ...] = (
    "aortic stenosis",
    "mitral regurgitation",
    "valve",
    "cyanosis",
    "congenital heart disease",
    "pda",
    "vsd",
    "tetralogy of fallot",
)

FILTER_MODE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "broad": CARDIOLOGY_KEYWORDS,
    "strict": STRICT_CARDIOLOGY_KEYWORDS,
    "high_confidence": HIGH_CONFIDENCE_DISEASE_TERMS,
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
            "triggers; 'high_confidence' adds context rules for ECG/EKG and "
            "murmur mentions. Defaults to broad."
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

    return _matched_terms_in_text(record_text(record), keywords)


def high_confidence_matched_terms(record: Mapping[str, Any]) -> list[str]:
    """Return high-confidence cardiology terms for ``record``.

    Disease/topic terms can select a record directly. Generic ECG/EKG and
    murmur mentions only select a record when paired with more specific context
    terms, reducing false positives from incidental exam or vital-sign text.
    """

    text = record_text(record)
    matched = _matched_terms_in_text(text, HIGH_CONFIDENCE_DISEASE_TERMS)

    ecg_terms = _matched_terms_in_text(text, HIGH_CONFIDENCE_ECG_TERMS)
    ecg_context = _matched_terms_in_text(text, HIGH_CONFIDENCE_ECG_CONTEXT_TERMS)
    if ecg_terms and ecg_context:
        matched.extend(ecg_terms)
        matched.extend(ecg_context)

    murmur_terms = _matched_terms_in_text(text, HIGH_CONFIDENCE_MURMUR_TERMS)
    murmur_context = _matched_terms_in_text(text, HIGH_CONFIDENCE_MURMUR_CONTEXT_TERMS)
    if murmur_terms and murmur_context:
        matched.extend(murmur_terms)
        matched.extend(murmur_context)

    return _deduplicate_terms(matched)


def _matched_terms_in_text(text: str, keywords: Iterable[str]) -> list[str]:
    """Return keywords found in already-normalized searchable text."""

    seen: set[str] = set()
    matched: list[str] = []
    for keyword in keywords:
        normalized = keyword.lower()
        if normalized and normalized in text and normalized not in seen:
            matched.append(keyword)
            seen.add(normalized)
    return matched


def _deduplicate_terms(terms: Iterable[str]) -> list[str]:
    """Deduplicate terms while preserving first occurrence order."""

    seen: set[str] = set()
    deduplicated: list[str] = []
    for term in terms:
        normalized = term.lower()
        if normalized not in seen:
            deduplicated.append(term)
            seen.add(normalized)
    return deduplicated


def filter_cardiology_records(
    records: Iterable[Mapping[str, Any]],
    keywords: Iterable[str] = CARDIOLOGY_KEYWORDS,
    filter_confidence: str = "broad",
) -> list[dict[str, Any]]:
    """Return cardiology-related records with matched keyword evidence."""

    keyword_tuple = tuple(keywords)
    filtered: list[dict[str, Any]] = []
    for record in records:
        if filter_confidence == "high_confidence":
            matched_terms = high_confidence_matched_terms(record)
        else:
            matched_terms = matched_terms_for_record(record, keyword_tuple)
        if matched_terms:
            output_record = dict(record)
            output_record["matched_terms"] = matched_terms
            output_record["filter_confidence"] = filter_confidence
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

    filtered = filter_cardiology_records(
        records,
        keywords,
        filter_confidence="custom" if args.keyword else args.filter_mode,
    )
    count = write_jsonl(args.output, filtered)

    print(f"Read from: {args.input}")
    print(f"Wrote to: {args.output}")
    print(f"Filter mode: {args.filter_mode}")
    print(f"Cardiology examples: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
