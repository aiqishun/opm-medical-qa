#!/usr/bin/env python
"""Inspect the schema of a local MedQA-style JSONL file.

The real MedQA dataset is not bundled with this repository. This script is a
safe, read-only helper for users who have a local JSONL file and want to inspect
its top-level fields before running prototype preprocessing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DEFAULT_INPUT = PROJECT_ROOT / "data" / "raw" / "medqa_full.jsonl"
FIELD_NAMES: tuple[str, ...] = ("question", "options", "answer", "answer_idx")
MAX_TEXT_LENGTH = 120

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_io import DataIOError, read_jsonl  # noqa: E402


def _non_negative_int(value: str) -> int:
    """Parse a non-negative integer for argparse."""

    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect a local MedQA-style JSONL file without printing full records."
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        type=Path,
        help="Path to a local MedQA JSONL file. Defaults to data/raw/medqa_full.jsonl.",
    )
    parser.add_argument(
        "--max-preview",
        default=3,
        type=_non_negative_int,
        help="Number of redacted records to preview. Defaults to 3.",
    )
    return parser


def truncate_text(value: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Return a safely shortened version of text for terminal display."""

    compact = " ".join(value.split())
    if len(compact) <= max_length:
        return compact
    return compact[: max_length - 3].rstrip() + "..."


def preview_value(value: Any) -> Any:
    """Redact a JSON value by truncating long strings recursively."""

    if isinstance(value, str):
        return truncate_text(value)
    if isinstance(value, Mapping):
        return {str(key): preview_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [preview_value(item) for item in value[:5]]
    return value


def preview_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a small redacted preview of one record."""

    return {str(key): preview_value(value) for key, value in record.items()}


def inspect_records(
    records: Sequence[Mapping[str, Any]],
    max_preview: int = 3,
) -> dict[str, Any]:
    """Inspect already-loaded records.

    This helper is mainly useful for tests. The CLI uses ``inspect_jsonl`` so it
    can stream records from disk.
    """

    observed_fields: set[str] = set()
    field_counts = {field: 0 for field in FIELD_NAMES}
    previews: list[dict[str, Any]] = []

    for record in records:
        observed_fields.update(str(key) for key in record.keys())
        for field in FIELD_NAMES:
            if field in record:
                field_counts[field] += 1
        if len(previews) < max_preview:
            previews.append(preview_record(record))

    return {
        "record_count": len(records),
        "observed_fields": sorted(observed_fields),
        "field_counts": field_counts,
        "previews": previews,
    }


def inspect_jsonl(path: Path, max_preview: int = 3) -> dict[str, Any]:
    """Inspect a JSONL file while keeping only a small preview in memory."""

    observed_fields: set[str] = set()
    field_counts = {field: 0 for field in FIELD_NAMES}
    previews: list[dict[str, Any]] = []
    record_count = 0

    for record in read_jsonl(path):
        record_count += 1
        observed_fields.update(str(key) for key in record.keys())
        for field in FIELD_NAMES:
            if field in record:
                field_counts[field] += 1
        if len(previews) < max_preview:
            previews.append(preview_record(record))

    return {
        "record_count": record_count,
        "observed_fields": sorted(observed_fields),
        "field_counts": field_counts,
        "previews": previews,
    }


def format_report(path: Path, summary: Mapping[str, Any]) -> str:
    """Format an inspection summary for terminal output."""

    field_counts = summary["field_counts"]
    observed_fields = summary["observed_fields"]
    previews = summary["previews"]

    lines = [
        f"Input: {path}",
        f"Records: {summary['record_count']}",
        "",
        "Observed top-level fields:",
    ]

    if observed_fields:
        lines.extend(f"- {field}" for field in observed_fields)
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "Field coverage:",
            f"- question: {field_counts['question']}",
            f"- options: {field_counts['options']}",
            f"- answer: {field_counts['answer']}",
            f"- answer_idx: {field_counts['answer_idx']}",
            "",
            f"Redacted preview (first {len(previews)} records):",
        ]
    )

    if not previews:
        lines.append("- (none)")
    else:
        for index, preview in enumerate(previews, start=1):
            lines.append(f"Record {index}:")
            lines.append(json.dumps(preview, ensure_ascii=False, indent=2))

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""

    args = _build_parser().parse_args(argv)

    try:
        summary = inspect_jsonl(args.input, max_preview=args.max_preview)
    except (DataIOError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(format_report(args.input, summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
