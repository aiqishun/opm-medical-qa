#!/usr/bin/env python
"""Sample and summarize a batch QA results JSONL for manual inspection.

This is a **qualitative** audit layer over the JSONL written by
``scripts/run_batch_qa.py``. It samples matched and fallback records,
counts matched-topic frequency, flags any topic that dominates more than
40% of matched cases, and writes a Markdown report. It is **not** an
accuracy evaluation, makes no medical claims, and ``matched`` here only
means a topic was returned by the matcher — not that it is clinically
correct.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from random import Random
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DEFAULT_INPUT = (
    PROJECT_ROOT / "experiments" / "results" / "real_medqa_batch_qa_results.jsonl"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "experiments" / "results" / "real_medqa_audit.md"
DEFAULT_SAMPLE_SIZE = 30
DEFAULT_SEED = 42

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_io import DataIOError, read_jsonl  # noqa: E402
from evaluation.audit import (  # noqa: E402
    STATUS_FALLBACK,
    STATUS_MATCHED,
    build_audit_markdown,
    filter_confidence_frequency,
    find_dominant_topic,
    sample_records,
    topic_frequency,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit a batch QA results JSONL: sample matched and fallback "
            "records and write a Markdown report for manual inspection."
        )
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        type=Path,
        help="Path to the batch QA results JSONL.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        type=Path,
        help="Path to write the Markdown audit report.",
    )
    parser.add_argument(
        "--sample-size",
        default=DEFAULT_SAMPLE_SIZE,
        type=int,
        help=(
            "Maximum number of records to randomly sample from each of the "
            "matched and fallback buckets (default: 30)."
        ),
    )
    parser.add_argument(
        "--seed",
        default=DEFAULT_SEED,
        type=int,
        help="Random seed for deterministic sampling (default: 42).",
    )
    return parser


def run_audit(
    input_path: Path,
    output_path: Path,
    sample_size: int,
    seed: int,
) -> dict:
    """Read ``input_path``, build the audit report, and write to ``output_path``.

    Returns a small dict of headline counts so the CLI can print them.

    Raises:
        DataIOError: if the input file is missing or malformed.
        ValueError: if ``sample_size`` is negative.
    """

    if sample_size < 0:
        raise ValueError(f"sample_size must be >= 0, got {sample_size}")

    records = list(read_jsonl(input_path))
    matched = [r for r in records if r.get("status") == STATUS_MATCHED]
    fallback = [r for r in records if r.get("status") == STATUS_FALLBACK]
    counts = topic_frequency(matched)
    confidence_counts = filter_confidence_frequency(records)
    dominance = find_dominant_topic(counts, len(matched))

    rng = Random(seed)
    # Always draw matched first so seed semantics stay stable across input
    # orderings — switching the order would change which records are picked.
    sampled_matched = sample_records(matched, sample_size, rng)
    sampled_fallback = sample_records(fallback, sample_size, rng)

    markdown = build_audit_markdown(
        input_path=input_path,
        total_records=len(records),
        matched_count=len(matched),
        fallback_count=len(fallback),
        topic_counts=counts,
        filter_confidence_counts=confidence_counts,
        sampled_matched=sampled_matched,
        sampled_fallback=sampled_fallback,
        dominance=dominance,
        sample_size=sample_size,
        seed=seed,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    return {
        "total_records": len(records),
        "matched": len(matched),
        "fallback": len(fallback),
        "sampled_matched": len(sampled_matched),
        "sampled_fallback": len(sampled_fallback),
        "dominance": dominance,
        "input_path": input_path,
        "output_path": output_path,
    }


def _print_summary(summary: dict) -> None:
    print(f"Read {summary['total_records']} records from: {summary['input_path']}")
    print(f"Matched: {summary['matched']}")
    print(f"Fallback: {summary['fallback']}")
    print(
        f"Sampled matched / fallback: "
        f"{summary['sampled_matched']} / {summary['sampled_fallback']}"
    )
    if summary["dominance"]:
        topic, share = summary["dominance"]
        print(
            f"⚠ Topic dominance: '{topic}' = {share * 100:.1f}% of matched records"
        )
    print(f"Wrote audit report to: {summary['output_path']}")


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""

    args = _build_parser().parse_args(argv)

    try:
        summary = run_audit(
            input_path=args.input,
            output_path=args.output,
            sample_size=args.sample_size,
            seed=args.seed,
        )
    except DataIOError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
