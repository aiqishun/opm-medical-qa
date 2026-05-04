"""Human-readable Markdown summaries for batch QA runs.

Designed to be a pure function: it takes the metadata and per-record results
that ``scripts/run_batch_qa.py`` already produces and returns a Markdown
string. File I/O is handled by the caller.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

STATUS_MATCHED = "matched"
STATUS_FALLBACK = "fallback"


def _sample_label(input_path: Path) -> str:
    """Pick a short label describing what kind of sample this run used.

    Detection is purely path-based — the function never reads the file. The
    label is folded into the prototype-note disclaimer so the wording matches
    what the user actually ran on without overclaiming.
    """
    name = str(input_path).lower()
    if "medqa_cardiology_real_sample" in name or "real" in name:
        return "local MedQA-derived sample"
    if "medqa_cardiology_sample" in name:
        return "synthetic sample"
    return "local input sample"


def _prototype_note(input_path: Path) -> str:
    label = _sample_label(input_path)
    return (
        f"> Prototype run on a {label}. This is **not** a full MedQA "
        "evaluation and reports no medical performance metrics. Generated "
        "graphs are research artifacts, not clinical knowledge."
    )


def build_markdown_summary(
    *,
    input_path: Path,
    output_path: Path,
    graphs_dir: Path,
    total_records: int,
    skipped_missing_question: int,
    results: Sequence[Mapping[str, Any]],
) -> str:
    """Render a Markdown summary of one batch QA run.

    ``results`` is the list of per-question dicts that ``run_batch`` writes to
    the output JSONL. The function does not touch the filesystem.
    """

    matched_results = [r for r in results if r.get("status") == STATUS_MATCHED]
    fallback_results = [r for r in results if r.get("status") == STATUS_FALLBACK]
    matched = len(matched_results)
    fallback = len(fallback_results)
    processed = matched + fallback
    graph_files = sum(1 for r in matched_results if r.get("graph_path"))

    sections = [
        "# OPM Medical QA — Batch Summary",
        "",
        _prototype_note(input_path),
        "",
        "## Inputs and outputs",
        "",
        f"- Input: `{input_path}`",
        f"- Results JSONL: `{output_path}`",
        f"- Graphs directory: `{graphs_dir}`",
        "",
        "## Counts",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total input records | {total_records} |",
        f"| Questions processed | {processed} |",
        f"| Skipped (missing question) | {skipped_missing_question} |",
        f"| Matched | {matched} |",
        f"| Fallback | {fallback} |",
        f"| Match rate | {_format_match_rate(matched, processed)} |",
        f"| Graph files generated | {graph_files} |",
        "",
        "## Matched topic frequency",
        "",
        _format_topic_table(matched_results),
        "",
        "## Fallback questions",
        "",
        _format_fallback_list(fallback_results),
        "",
    ]

    return "\n".join(sections)


def _format_match_rate(matched: int, processed: int) -> str:
    if processed == 0:
        return "n/a"
    return f"{(matched / processed) * 100:.1f}%"


def _format_topic_table(matched_results: Sequence[Mapping[str, Any]]) -> str:
    if not matched_results:
        return "_No matched topics._"

    counts = Counter(
        str(r.get("matched_topic")) for r in matched_results if r.get("matched_topic")
    )
    if not counts:
        return "_No matched topics._"

    rows = ["| Topic | Count |", "| --- | ---: |"]
    # Sort by count desc, then topic name asc, for a stable, readable order.
    for topic, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        rows.append(f"| {topic} | {count} |")
    return "\n".join(rows)


def _format_fallback_list(fallback_results: Sequence[Mapping[str, Any]]) -> str:
    if not fallback_results:
        return "_None._"

    lines: list[str] = []
    for record in fallback_results:
        question = str(record.get("question", "")).strip()
        if not question:
            continue
        lines.append(f"- {question}")
    return "\n".join(lines) if lines else "_None._"
