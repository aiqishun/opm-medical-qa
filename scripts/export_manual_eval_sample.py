#!/usr/bin/env python
"""Export a random batch-QA sample for manual qualitative evaluation.

This script does not compute accuracy. It creates annotation-ready JSONL and
Markdown files so a human can inspect topic relevance and routing quality.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from random import Random
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DEFAULT_INPUT = (
    PROJECT_ROOT / "experiments" / "results" / "real_medqa_high_confidence_batch_qa_results.jsonl"
)
DEFAULT_OUTPUT_JSONL = (
    PROJECT_ROOT / "experiments" / "manual_eval" / "high_confidence_sample_100.jsonl"
)
DEFAULT_OUTPUT_MD = (
    PROJECT_ROOT / "experiments" / "manual_eval" / "high_confidence_sample_100.md"
)
DEFAULT_SAMPLE_SIZE = 100
DEFAULT_SEED = 42

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_io import DataIOError, read_jsonl, write_jsonl  # noqa: E402


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Randomly sample batch QA results and export annotation templates "
            "for manual qualitative evaluation."
        )
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        type=Path,
        help="Input batch QA results JSONL.",
    )
    parser.add_argument(
        "--output-jsonl",
        default=DEFAULT_OUTPUT_JSONL,
        type=Path,
        help="Output JSONL file for manual annotations.",
    )
    parser.add_argument(
        "--output-md",
        default=DEFAULT_OUTPUT_MD,
        type=Path,
        help="Output Markdown checklist for manual annotations.",
    )
    parser.add_argument(
        "--sample-size",
        default=DEFAULT_SAMPLE_SIZE,
        type=_non_negative_int,
        help="Number of records to sample. Defaults to 100.",
    )
    parser.add_argument(
        "--seed",
        default=DEFAULT_SEED,
        type=int,
        help="Random seed for deterministic sampling. Defaults to 42.",
    )
    return parser


def sample_records(
    records: Sequence[Mapping[str, Any]],
    sample_size: int,
    seed: int,
) -> list[Mapping[str, Any]]:
    """Return up to ``sample_size`` records sampled deterministically."""

    if sample_size <= 0 or not records:
        return []
    if sample_size >= len(records):
        return list(records)
    return Random(seed).sample(list(records), sample_size)


def build_manual_eval_row(record: Mapping[str, Any]) -> dict[str, Any]:
    """Convert one batch result row into an annotation-ready row."""

    row = {
        "question": record.get("question"),
        "matched_topic": record.get("matched_topic"),
        "status": record.get("status"),
        "answer": record.get("answer"),
        "graph_path": record.get("graph_path"),
        "manual_is_cardiology_relevant": None,
        "manual_topic_correct": None,
        "manual_expected_topic": None,
        "manual_notes": None,
    }

    if "id" in record:
        row = {"id": record.get("id"), **row}

    if isinstance(record.get("matched_terms"), list):
        row["matched_terms"] = list(record["matched_terms"])

    if isinstance(record.get("filter_confidence"), str):
        row["filter_confidence"] = record["filter_confidence"]

    return row


def build_manual_eval_rows(
    records: Sequence[Mapping[str, Any]],
    sample_size: int,
    seed: int,
) -> list[dict[str, Any]]:
    """Sample ``records`` and return annotation-ready rows."""

    return [build_manual_eval_row(record) for record in sample_records(records, sample_size, seed)]


def render_markdown(
    rows: Sequence[Mapping[str, Any]],
    *,
    input_path: Path,
    output_jsonl: Path,
    sample_size: int,
    seed: int,
) -> str:
    """Render a human-readable manual evaluation checklist."""

    lines = [
        "# Manual Evaluation Sample",
        "",
        "> Qualitative/manual assessment template. This file does not contain "
        "automatic accuracy metrics, does not claim medical correctness, and is "
        "not a full MedQA evaluation.",
        "",
        "## Metadata",
        "",
        f"- Input: `{input_path}`",
        f"- Annotation JSONL: `{output_jsonl}`",
        f"- Requested sample size: {sample_size}",
        f"- Actual sampled records: {len(rows)}",
        f"- Random seed: {seed}",
        "",
        "## Annotation Guide",
        "",
        "- `manual_is_cardiology_relevant`: mark whether the question is truly cardiology-related.",
        "- `manual_topic_correct`: mark whether the routed topic is appropriate.",
        "- `manual_expected_topic`: write the expected topic if routing is wrong or too broad.",
        "- `manual_notes`: add short qualitative notes about ambiguity or failure mode.",
        "",
        "## Records",
        "",
    ]

    for index, row in enumerate(rows, start=1):
        rid = row.get("id") or "—"
        terms = _format_terms(row.get("matched_terms"))
        confidence = row.get("filter_confidence") or "not available"
        lines.extend(
            [
                f"### {index}. {rid}",
                "",
                f"- **Question:** {row.get('question') or ''}",
                f"- **Matched topic:** {row.get('matched_topic') or '(none)'}",
                f"- **Status:** {row.get('status') or '(missing)'}",
                f"- **Matched terms:** {terms}",
                f"- **Filter confidence:** {confidence}",
                f"- **Graph path:** {row.get('graph_path') or '(none)'}",
                f"- **Answer:** {_truncate(row.get('answer') or '')}",
                "",
                "- [ ] Cardiology relevant: yes",
                "- [ ] Cardiology relevant: no",
                "- [ ] Topic correct: yes",
                "- [ ] Topic correct: no",
                "- Expected topic:",
                "- Notes:",
                "",
            ]
        )

    return "\n".join(lines)


def export_manual_eval_sample(
    *,
    input_path: Path,
    output_jsonl: Path,
    output_md: Path,
    sample_size: int,
    seed: int,
) -> dict[str, Any]:
    """Read batch results and write JSONL + Markdown manual eval files."""

    records = list(read_jsonl(input_path))
    rows = build_manual_eval_rows(records, sample_size, seed)
    written = write_jsonl(output_jsonl, rows)

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(
        render_markdown(
            rows,
            input_path=input_path,
            output_jsonl=output_jsonl,
            sample_size=sample_size,
            seed=seed,
        ),
        encoding="utf-8",
    )

    return {
        "input_records": len(records),
        "sampled_records": written,
        "input_path": input_path,
        "output_jsonl": output_jsonl,
        "output_md": output_md,
    }


def _format_terms(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "_not available_"
    return ", ".join(f"`{term}`" for term in value)


def _truncate(text: str, max_chars: int = 220) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""

    args = _build_parser().parse_args(argv)

    try:
        summary = export_manual_eval_sample(
            input_path=args.input,
            output_jsonl=args.output_jsonl,
            output_md=args.output_md,
            sample_size=args.sample_size,
            seed=args.seed,
        )
    except DataIOError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"error: could not write manual evaluation sample: {error}", file=sys.stderr)
        return 1

    print(f"Read {summary['input_records']} records from: {summary['input_path']}")
    print(f"Sampled records: {summary['sampled_records']}")
    print(f"Wrote JSONL to: {summary['output_jsonl']}")
    print(f"Wrote Markdown to: {summary['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
