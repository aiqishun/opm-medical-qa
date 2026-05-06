#!/usr/bin/env python3
"""Compare the completed baseline and LLM-supervised manual audits.

The script reads both audit CSVs, validates that their headers match, prints
side-by-side distribution and metric tables, and writes the same comparison to
``annotations/manual_audit_comparison_report.md``.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_CSV = PROJECT_ROOT / "annotations" / "manual_audit_baseline_v2.csv"
LLM_SUPERVISED_CSV = PROJECT_ROOT / "annotations" / "manual_audit_llm_supervised_v1.csv"
REPORT_PATH = PROJECT_ROOT / "annotations" / "manual_audit_comparison_report.md"

DISTRIBUTION_COLUMNS = (
    "cardiology_relevance",
    "topic_correctness",
    "matched_term_role",
    "error_type",
    "keep_for_cardiology_dataset",
    "keep_for_error_analysis",
)

METRICS = (
    ("topic_correctness correct rate", "topic_correctness", {"correct"}),
    (
        "topic_correctness correct + partial rate",
        "topic_correctness",
        {"correct", "partial"},
    ),
    ("topic_correctness incorrect rate", "topic_correctness", {"incorrect"}),
    ("keep_for_cardiology_dataset yes rate", "keep_for_cardiology_dataset", {"yes"}),
    ("keep_for_error_analysis yes rate", "keep_for_error_analysis", {"yes"}),
    ("out_of_scope error rate", "error_type", {"out_of_scope"}),
    (
        "past_history_distraction error rate",
        "error_type",
        {"past_history_distraction"},
    ),
    (
        "manifestation_vs_cause error rate",
        "error_type",
        {"manifestation_vs_cause"},
    ),
    ("vague_topic error rate", "error_type", {"vague_topic"}),
)


def load_csv(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Audit CSV not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Audit CSV has no header: {csv_path}")
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    return fieldnames, rows


def validate_schema(
    baseline_fields: list[str],
    llm_fields: list[str],
) -> None:
    if baseline_fields != llm_fields:
        baseline_set = set(baseline_fields)
        llm_set = set(llm_fields)
        only_baseline = sorted(baseline_set - llm_set)
        only_llm = sorted(llm_set - baseline_set)
        details = [
            "Audit CSV schemas differ.",
            f"Baseline columns: {baseline_fields}",
            f"LLM-supervised columns: {llm_fields}",
        ]
        if only_baseline:
            details.append(f"Only in baseline: {only_baseline}")
        if only_llm:
            details.append(f"Only in LLM-supervised: {only_llm}")
        raise ValueError("\n".join(details))

    missing_required = [col for col in DISTRIBUTION_COLUMNS if col not in baseline_fields]
    if missing_required:
        raise ValueError(f"Missing required audit columns: {missing_required}")


def pct(count: int, total: int) -> float:
    return 100.0 * count / total if total else 0.0


def format_count_pct(count: int, total: int) -> str:
    return f"{count} ({pct(count, total):.1f}%)"


def format_delta_pp(baseline_pct: float, llm_pct: float) -> str:
    delta = llm_pct - baseline_pct
    return f"{delta:+.1f} pp"


def markdown_escape(value: str) -> str:
    return value.replace("|", "\\|")


def sorted_values(
    baseline_counter: Counter[str],
    llm_counter: Counter[str],
) -> list[str]:
    values = set(baseline_counter) | set(llm_counter)
    return sorted(
        values,
        key=lambda value: (
            -(baseline_counter[value] + llm_counter[value]),
            -baseline_counter[value],
            value,
        ),
    )


def render_distribution_table(
    column: str,
    baseline_rows: list[dict[str, str]],
    llm_rows: list[dict[str, str]],
) -> list[str]:
    baseline_counter = Counter(row.get(column, "") for row in baseline_rows)
    llm_counter = Counter(row.get(column, "") for row in llm_rows)
    baseline_total = len(baseline_rows)
    llm_total = len(llm_rows)

    lines = [
        f"### {column}",
        "",
        "| Value | Baseline count (%) | LLM-supervised count (%) | Delta |",
        "|---|---:|---:|---:|",
    ]
    for value in sorted_values(baseline_counter, llm_counter):
        baseline_count = baseline_counter[value]
        llm_count = llm_counter[value]
        baseline_pct = pct(baseline_count, baseline_total)
        llm_pct = pct(llm_count, llm_total)
        display_value = markdown_escape(value or "(blank)")
        lines.append(
            "| "
            f"{display_value} | "
            f"{format_count_pct(baseline_count, baseline_total)} | "
            f"{format_count_pct(llm_count, llm_total)} | "
            f"{format_delta_pp(baseline_pct, llm_pct)} |"
        )

    return lines


def metric_count(rows: list[dict[str, str]], column: str, target_values: set[str]) -> int:
    return sum(1 for row in rows if row.get(column, "") in target_values)


def render_metric_table(
    baseline_rows: list[dict[str, str]],
    llm_rows: list[dict[str, str]],
) -> list[str]:
    baseline_total = len(baseline_rows)
    llm_total = len(llm_rows)
    lines = [
        "## Key comparison metrics",
        "",
        "| Metric | Baseline | LLM-supervised | Delta |",
        "|---|---:|---:|---:|",
    ]

    for label, column, values in METRICS:
        baseline_count = metric_count(baseline_rows, column, values)
        llm_count = metric_count(llm_rows, column, values)
        baseline_pct = pct(baseline_count, baseline_total)
        llm_pct = pct(llm_count, llm_total)
        lines.append(
            "| "
            f"{label} | "
            f"{format_count_pct(baseline_count, baseline_total)} | "
            f"{format_count_pct(llm_count, llm_total)} | "
            f"{format_delta_pp(baseline_pct, llm_pct)} |"
        )

    return lines


def build_interpretation(
    baseline_rows: list[dict[str, str]],
    llm_rows: list[dict[str, str]],
) -> list[str]:
    baseline_total = len(baseline_rows)
    llm_total = len(llm_rows)

    baseline_correct = metric_count(baseline_rows, "topic_correctness", {"correct"})
    llm_correct = metric_count(llm_rows, "topic_correctness", {"correct"})
    baseline_correct_partial = metric_count(
        baseline_rows,
        "topic_correctness",
        {"correct", "partial"},
    )
    llm_correct_partial = metric_count(
        llm_rows,
        "topic_correctness",
        {"correct", "partial"},
    )
    baseline_incorrect = metric_count(baseline_rows, "topic_correctness", {"incorrect"})
    llm_incorrect = metric_count(llm_rows, "topic_correctness", {"incorrect"})

    baseline_errors = Counter(row.get("error_type", "") for row in baseline_rows)
    llm_errors = Counter(row.get("error_type", "") for row in llm_rows)

    def error_delta(error_type: str) -> str:
        baseline_rate = pct(baseline_errors[error_type], baseline_total)
        llm_rate = pct(llm_errors[error_type], llm_total)
        return f"{error_type} {baseline_rate:.1f}% -> {llm_rate:.1f}%"

    return [
        "## Chinese interpretation",
        "",
        "### Topic matching quality",
        "",
        (
            "LLM supervision 明显提升了 topic matching 的可用质量："
            f"`correct` 从 {pct(baseline_correct, baseline_total):.1f}% "
            f"升至 {pct(llm_correct, llm_total):.1f}%，"
            f"`correct + partial` 从 {pct(baseline_correct_partial, baseline_total):.1f}% "
            f"升至 {pct(llm_correct_partial, llm_total):.1f}%，"
            f"`incorrect` 从 {pct(baseline_incorrect, baseline_total):.1f}% "
            f"降至 {pct(llm_incorrect, llm_total):.1f}%。"
            "这说明 LLM supervision 更容易把样本保留在相关心血管主题附近，"
            "但提升主要体现为更多 partial match；严格的完全正确匹配比例仍然偏低。"
        ),
        "",
        "### Error types",
        "",
        (
            "主要减少的错误包括 "
            f"{error_delta('out_of_scope')}、"
            f"{error_delta('past_history_distraction')}、"
            f"{error_delta('manifestation_vs_cause')}。"
            "这些下降说明 LLM supervision 对排除非心血管主题、既往史干扰、"
            "以及表现与病因混淆有帮助。仍然突出的残留问题是 "
            f"{error_delta('vague_topic')}，"
            "并且 partial_match 比例升高，提示模型常能找到相关方向，"
            "但仍会停留在过宽或不够精确的主题层级。"
        ),
    ]


def build_report(
    baseline_rows: list[dict[str, str]],
    llm_rows: list[dict[str, str]],
    schema_fields: list[str],
) -> str:
    lines = [
        "# Manual Audit Comparison Report",
        "",
        f"- Baseline file: `{BASELINE_CSV.relative_to(PROJECT_ROOT)}`",
        f"- LLM-supervised file: `{LLM_SUPERVISED_CSV.relative_to(PROJECT_ROOT)}`",
        f"- Schema validation: passed ({len(schema_fields)} matching columns)",
        f"- Baseline rows: {len(baseline_rows)}",
        f"- LLM-supervised rows: {len(llm_rows)}",
        "- Rates use all rows in each file as the denominator.",
        "",
    ]

    lines.extend(render_metric_table(baseline_rows, llm_rows))
    lines.extend(["", "## Side-by-side distributions", ""])

    for column in DISTRIBUTION_COLUMNS:
        lines.extend(render_distribution_table(column, baseline_rows, llm_rows))
        lines.append("")

    lines.extend(build_interpretation(baseline_rows, llm_rows))
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    baseline_fields, baseline_rows = load_csv(BASELINE_CSV)
    llm_fields, llm_rows = load_csv(LLM_SUPERVISED_CSV)
    validate_schema(baseline_fields, llm_fields)

    report = build_report(baseline_rows, llm_rows, baseline_fields)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Report written to: {REPORT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
