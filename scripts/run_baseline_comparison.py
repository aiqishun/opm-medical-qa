#!/usr/bin/env python
"""Compare the keyword-only baseline against the OPM reasoner.

For each question in the synthetic JSONL sample, runs both matchers and writes:

- a per-question JSONL row with both matcher's outcomes and whether the OPM
  reasoner produced a reasoning path and/or an OPM graph,
- a Markdown summary report with the headline counts and a per-question table.

This is a prototype-level comparison on a small synthetic sample. It makes no
medical accuracy claims and demonstrates no superiority on the real MedQA
dataset.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "medqa_cardiology_sample.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "experiments" / "results" / "baseline_comparison.jsonl"
DEFAULT_SUMMARY = PROJECT_ROOT / "experiments" / "results" / "baseline_comparison_summary.md"
DEFAULT_KNOWLEDGE_BASE = PROJECT_ROOT / "data" / "processed" / "cardiology_knowledge.json"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_io import DataIOError, read_jsonl, write_jsonl  # noqa: E402
from evaluation.baseline import (  # noqa: E402
    KeywordBaselineMatcher,
    build_baseline_comparison_markdown,
)
from reasoning import RuleBasedCardiologyReasoner, load_topics  # noqa: E402


STATUS_MATCHED = "matched"
STATUS_FALLBACK = "fallback"


@dataclass(frozen=True)
class ComparisonSummary:
    """Counts returned by :func:`run_comparison` for end-of-run reporting."""

    total_records: int
    skipped_missing_question: int
    baseline_matched: int
    baseline_fallback: int
    opm_matched: int
    opm_fallback: int
    opm_with_reasoning_path: int
    opm_with_graph: int
    input_path: Path
    output_path: Path
    summary_path: Path
    results: list[dict[str, Any]] = field(default_factory=list)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the keyword-only baseline alongside the OPM reasoner over a "
            "JSONL of cardiology questions and compare their outcomes."
        )
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        type=Path,
        help="Input JSONL file with one question per record.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        type=Path,
        help="JSONL file that receives one comparison row per question.",
    )
    parser.add_argument(
        "--summary",
        default=DEFAULT_SUMMARY,
        type=Path,
        help="Markdown file that receives the comparison summary report.",
    )
    parser.add_argument(
        "--knowledge-base",
        default=DEFAULT_KNOWLEDGE_BASE,
        type=Path,
        help="Path to the cardiology knowledge base JSON file.",
    )
    return parser


def _question_text(record: Mapping[str, Any]) -> str | None:
    question = record.get("question")
    if not isinstance(question, str):
        return None
    question = question.strip()
    return question or None


def run_comparison(
    input_path: Path,
    output_path: Path,
    summary_path: Path,
    knowledge_base_path: Path,
) -> ComparisonSummary:
    """Run both matchers over ``input_path`` and write JSONL + Markdown reports.

    Raises:
        DataIOError: if the knowledge base or input file is missing or invalid.
    """

    topics = load_topics(knowledge_base_path)
    opm_reasoner = RuleBasedCardiologyReasoner(topics=topics)
    baseline = KeywordBaselineMatcher(topics=topics)
    records = list(read_jsonl(input_path))

    rows: list[dict[str, Any]] = []
    skipped = 0
    baseline_matched = 0
    opm_matched = 0
    opm_with_path = 0
    opm_with_graph = 0

    for record in records:
        question = _question_text(record)
        if question is None:
            skipped += 1
            continue

        baseline_result = baseline.answer(question)
        opm_result = opm_reasoner.answer(question)
        has_path = bool(opm_result.reasoning_path)
        has_graph = not opm_result.graph.is_empty()

        if baseline_result.is_match:
            baseline_matched += 1
        if opm_result.is_match:
            opm_matched += 1
        if has_path:
            opm_with_path += 1
        if has_graph:
            opm_with_graph += 1

        rows.append(
            {
                "id": record.get("id"),
                "question": question,
                "baseline_matched_topic": baseline_result.matched_topic,
                "baseline_status": (
                    STATUS_MATCHED if baseline_result.is_match else STATUS_FALLBACK
                ),
                "opm_matched_topic": opm_result.matched_topic,
                "opm_status": (
                    STATUS_MATCHED if opm_result.is_match else STATUS_FALLBACK
                ),
                "opm_has_reasoning_path": has_path,
                "opm_has_graph": has_graph,
            }
        )

    write_jsonl(output_path, rows)

    markdown = build_baseline_comparison_markdown(
        input_path=input_path,
        output_path=output_path,
        total_records=len(records),
        skipped_missing_question=skipped,
        results=rows,
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(markdown, encoding="utf-8")

    return ComparisonSummary(
        total_records=len(records),
        skipped_missing_question=skipped,
        baseline_matched=baseline_matched,
        baseline_fallback=len(rows) - baseline_matched,
        opm_matched=opm_matched,
        opm_fallback=len(rows) - opm_matched,
        opm_with_reasoning_path=opm_with_path,
        opm_with_graph=opm_with_graph,
        input_path=input_path,
        output_path=output_path,
        summary_path=summary_path,
        results=rows,
    )


def _print_summary(summary: ComparisonSummary) -> None:
    print(f"Read {summary.total_records} records from: {summary.input_path}")
    print(f"Skipped (missing question): {summary.skipped_missing_question}")
    print(f"Baseline matched / fallback: {summary.baseline_matched} / {summary.baseline_fallback}")
    print(f"OPM QA matched / fallback:   {summary.opm_matched} / {summary.opm_fallback}")
    print(f"OPM reasoning paths produced: {summary.opm_with_reasoning_path}")
    print(f"OPM graphs produced:          {summary.opm_with_graph}")
    print(f"Wrote results to: {summary.output_path}")
    print(f"Wrote summary report to: {summary.summary_path}")


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""

    args = _build_parser().parse_args(argv)

    try:
        summary = run_comparison(
            input_path=args.input,
            output_path=args.output,
            summary_path=args.summary,
            knowledge_base_path=args.knowledge_base,
        )
    except DataIOError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
