#!/usr/bin/env python
"""Run the rule-based reasoner over a JSONL file of questions.

For each input record this script reads the ``question`` field, runs the
existing :class:`RuleBasedCardiologyReasoner`, writes a JSONL row with the
answer and OPM metadata, and (for matched records) exports the OPM graph as
JSON into ``--graphs-dir``.

The script is intentionally simple: it processes records one at a time, uses
only the standard library, and shares all loading, reasoning, and export logic
with the single-question CLI.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "medqa_cardiology_sample.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "experiments" / "results" / "batch_qa_results.jsonl"
DEFAULT_GRAPHS_DIR = PROJECT_ROOT / "outputs" / "graphs" / "batch"
DEFAULT_KNOWLEDGE_BASE = PROJECT_ROOT / "data" / "processed" / "cardiology_knowledge.json"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_io import DataIOError, read_jsonl, write_jsonl  # noqa: E402
from evaluation.summary import build_markdown_summary  # noqa: E402
from graph.exporter import GraphExportError, export_graph  # noqa: E402
from graph.mermaid import MermaidExportError, export_mermaid  # noqa: E402
from reasoning import RuleBasedCardiologyReasoner, load_topics  # noqa: E402


_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9_-]+")
_MAX_STEM_LENGTH = 80

STATUS_MATCHED = "matched"
STATUS_FALLBACK = "fallback"


@dataclass(frozen=True)
class BatchSummary:
    """Counts returned by :func:`run_batch` for end-of-run reporting.

    ``results`` is the same list of dicts that was written to
    ``output_path`` as JSONL; it is exposed so callers can build downstream
    artifacts (such as a Markdown summary) without re-reading the file.
    """

    total_records: int
    matched: int
    fallback: int
    skipped_missing_question: int
    input_path: Path
    output_path: Path
    graphs_dir: Path
    mermaid_dir: Path | None = None
    results: list[dict[str, Any]] = field(default_factory=list)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the OPM cardiology reasoner over a JSONL file of questions and "
            "save structured results plus per-question OPM graph JSON files."
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
        help="JSONL file that receives one structured result per question.",
    )
    parser.add_argument(
        "--graphs-dir",
        default=DEFAULT_GRAPHS_DIR,
        type=Path,
        help="Directory to write one OPM graph JSON file per matched question.",
    )
    parser.add_argument(
        "--knowledge-base",
        default=DEFAULT_KNOWLEDGE_BASE,
        type=Path,
        help="Path to the cardiology knowledge base JSON file.",
    )
    parser.add_argument(
        "--mermaid-dir",
        default=None,
        type=Path,
        metavar="DIR",
        help=(
            "Optional directory to write one Mermaid flowchart (.mmd) per matched "
            "question alongside the JSON graph files."
        ),
    )
    parser.add_argument(
        "--summary",
        default=None,
        type=Path,
        metavar="PATH",
        help=(
            "Optional path to write a human-readable Markdown summary report. "
            "Parent directories are created automatically."
        ),
    )
    return parser


def _safe_filename_stem(record_id: object, index: int) -> str:
    """Return a filesystem-safe stem for a record's exported graph file."""

    if record_id is not None:
        slug = _FILENAME_SAFE.sub("_", str(record_id)).strip("_")
        if slug:
            return slug[:_MAX_STEM_LENGTH]
    return f"q{index:04d}"


def _question_text(record: Mapping[str, Any]) -> str | None:
    """Return the question text for ``record`` or ``None`` if it is missing."""

    question = record.get("question")
    if not isinstance(question, str):
        return None
    question = question.strip()
    return question or None


def run_batch(
    input_path: Path,
    output_path: Path,
    graphs_dir: Path,
    knowledge_base_path: Path,
    mermaid_dir: Path | None = None,
) -> BatchSummary:
    """Run the reasoner over ``input_path`` and write structured results.

    When ``mermaid_dir`` is provided, a Mermaid flowchart (``.mmd``) is written
    alongside the JSON graph for each matched record, and each result row gains
    a ``mermaid_path`` field.

    Raises:
        DataIOError: if the knowledge base or input file is missing or invalid.
        GraphExportError: if a graph file cannot be written.
        MermaidExportError: if a Mermaid file cannot be written.
    """

    topics = load_topics(knowledge_base_path)
    reasoner = RuleBasedCardiologyReasoner(topics=topics)
    records = list(read_jsonl(input_path))

    results: list[dict[str, Any]] = []
    matched = 0
    skipped = 0

    for index, record in enumerate(records):
        question = _question_text(record)
        if question is None:
            skipped += 1
            continue

        result = reasoner.answer(question)
        record_id = record.get("id")
        graph_path: str | None = None
        mermaid_path: str | None = None

        if result.is_match:
            stem = _safe_filename_stem(record_id, index)
            target = graphs_dir / f"{stem}.json"
            export_graph(result.graph, target)
            graph_path = str(target)
            if mermaid_dir is not None:
                mmd_target = mermaid_dir / f"{stem}.mmd"
                export_mermaid(
                    result.graph,
                    mmd_target,
                    reasoning_path=result.reasoning_path,
                )
                mermaid_path = str(mmd_target)
            matched += 1

        row: dict[str, Any] = {
            "id": record_id,
            "question": question,
            "matched_topic": result.matched_topic,
            "match_score": result.match_score,
            "answer": result.answer,
            "explanation": result.explanation,
            "reasoning_path": list(result.reasoning_path),
            "graph_path": graph_path,
            "status": STATUS_MATCHED if result.is_match else STATUS_FALLBACK,
        }
        matched_terms = record.get("matched_terms")
        if isinstance(matched_terms, list):
            row["matched_terms"] = list(matched_terms)
        if mermaid_dir is not None:
            row["mermaid_path"] = mermaid_path
        results.append(row)

    write_jsonl(output_path, results)

    return BatchSummary(
        total_records=len(records),
        matched=matched,
        fallback=len(results) - matched,
        skipped_missing_question=skipped,
        input_path=input_path,
        output_path=output_path,
        graphs_dir=graphs_dir,
        mermaid_dir=mermaid_dir,
        results=results,
    )


def _write_summary_report(summary: BatchSummary, path: Path) -> Path:
    """Render a Markdown report for ``summary`` and write it to ``path``."""

    markdown = build_markdown_summary(
        input_path=summary.input_path,
        output_path=summary.output_path,
        graphs_dir=summary.graphs_dir,
        total_records=summary.total_records,
        skipped_missing_question=summary.skipped_missing_question,
        results=summary.results,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


def _print_summary(summary: BatchSummary) -> None:
    print(f"Read {summary.total_records} records from: {summary.input_path}")
    print(f"Matched: {summary.matched}")
    print(f"Fallback: {summary.fallback}")
    print(f"Skipped (missing question): {summary.skipped_missing_question}")
    print(f"Wrote results to: {summary.output_path}")
    if summary.matched:
        print(f"Exported graphs to: {summary.graphs_dir}")
    if summary.matched and summary.mermaid_dir is not None:
        print(f"Exported Mermaid diagrams to: {summary.mermaid_dir}")


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""

    args = _build_parser().parse_args(argv)

    try:
        summary = run_batch(
            input_path=args.input,
            output_path=args.output,
            graphs_dir=args.graphs_dir,
            knowledge_base_path=args.knowledge_base,
            mermaid_dir=args.mermaid_dir,
        )
    except (DataIOError, GraphExportError, MermaidExportError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    _print_summary(summary)

    if args.summary is not None:
        try:
            summary_path = _write_summary_report(summary, args.summary)
        except OSError as error:
            print(f"error: could not write summary report: {error}", file=sys.stderr)
            return 1
        print(f"Wrote summary report to: {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
