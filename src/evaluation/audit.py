"""Qualitative audit helpers for batch QA result files.

These functions support a manual-inspection layer over the JSONL written by
``scripts/run_batch_qa.py``. The audit is **qualitative**: it samples records,
counts matched-topic frequency, and flags possible topic dominance. It is
**not** an accuracy evaluation, makes no medical claims, and ``matched`` here
only means a topic was returned, not that the topic is clinically correct.

All functions are pure — file I/O is the caller's responsibility.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from random import Random
from typing import Any, Mapping

STATUS_MATCHED = "matched"
STATUS_FALLBACK = "fallback"

DEFAULT_DOMINANCE_THRESHOLD = 0.40
DEFAULT_TOP_N = 10
DEFAULT_ANSWER_TRUNCATION = 160

_AUDIT_NOTE = (
    "> Qualitative audit of a batch QA run. This is **not** an accuracy "
    "evaluation, makes **no** medical accuracy claims, and is **not** a full "
    "MedQA evaluation. ``matched`` means a topic was returned by the matcher, "
    "not that the topic is clinically correct. Sampled records are intended "
    "for manual inspection only."
)


def topic_frequency(matched_results: Sequence[Mapping[str, Any]]) -> Counter:
    """Tally ``matched_topic`` across matched records.

    Records with no ``matched_topic`` value (e.g. fallback rows passed in by
    accident) are silently skipped.
    """
    return Counter(
        str(r.get("matched_topic"))
        for r in matched_results
        if r.get("matched_topic")
    )


def filter_confidence_frequency(records: Sequence[Mapping[str, Any]]) -> Counter:
    """Tally ``filter_confidence`` values when present."""

    return Counter(
        str(record.get("filter_confidence"))
        for record in records
        if record.get("filter_confidence")
    )


def find_dominant_topic(
    counts: Counter,
    total_matched: int,
    threshold: float = DEFAULT_DOMINANCE_THRESHOLD,
) -> tuple[str, float] | None:
    """Return ``(topic, share)`` if any topic exceeds ``threshold`` of matched.

    Returns the single most-frequent topic only. ``share`` is a fraction in
    ``[0, 1]``. If no topic clears the threshold (or there are no matched
    records), returns ``None``.
    """
    if total_matched <= 0 or not counts:
        return None
    topic, count = counts.most_common(1)[0]
    share = count / total_matched
    if share > threshold:
        return topic, share
    return None


def truncate_answer(text: str, max_chars: int = DEFAULT_ANSWER_TRUNCATION) -> str:
    """Collapse whitespace and truncate ``text`` to ``max_chars`` + ``…``."""
    collapsed = " ".join(str(text or "").split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max(0, max_chars - 1)].rstrip() + "…"


def sample_records(
    records: Sequence[Mapping[str, Any]],
    sample_size: int,
    rng: Random,
) -> list[Mapping[str, Any]]:
    """Return up to ``sample_size`` records, sampled with ``rng`` if needed."""
    if sample_size <= 0 or not records:
        return []
    if sample_size >= len(records):
        return list(records)
    return rng.sample(list(records), sample_size)


def build_audit_markdown(
    *,
    input_path: Path,
    total_records: int,
    matched_count: int,
    fallback_count: int,
    topic_counts: Counter,
    filter_confidence_counts: Counter | None = None,
    sampled_matched: Sequence[Mapping[str, Any]],
    sampled_fallback: Sequence[Mapping[str, Any]],
    dominance: tuple[str, float] | None,
    sample_size: int,
    seed: int,
    top_n: int = DEFAULT_TOP_N,
    dominance_threshold: float = DEFAULT_DOMINANCE_THRESHOLD,
) -> str:
    """Render the full Markdown audit report."""

    sections: list[str] = [
        "# OPM Medical QA — Batch Results Audit",
        "",
        _AUDIT_NOTE,
        "",
        "## Inputs and parameters",
        "",
        f"- Input: `{input_path}`",
        f"- Sample size per bucket: {sample_size}",
        f"- Random seed: {seed}",
        "",
        "## Counts",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total records | {total_records} |",
        f"| Matched | {matched_count} |",
        f"| Fallback | {fallback_count} |",
        f"| Match rate | {_format_match_rate(matched_count, matched_count + fallback_count)} |",
        "",
        f"## Top {top_n} matched topics",
        "",
        _format_top_topics_table(topic_counts, matched_count, top_n),
        "",
        "## Full matched-topic frequency",
        "",
        _format_full_topic_table(topic_counts),
        "",
        "## Topic dominance check",
        "",
        _format_dominance_section(dominance, dominance_threshold),
        "",
        "## Filter confidence",
        "",
        _format_filter_confidence_table(filter_confidence_counts or Counter()),
        "",
        f"## Sampled matched records (up to {sample_size})",
        "",
        _format_record_samples(sampled_matched, fallback=False),
        "",
        f"## Sampled fallback records (up to {sample_size})",
        "",
        _format_record_samples(sampled_fallback, fallback=True),
        "",
        "## Notes",
        "",
        "- Random sampling is deterministic via Python's `random.Random(seed)`.",
        "- This audit is qualitative and intended for **manual inspection only**.",
        "- A high match rate may simply reflect broad keyword/topic matching, not clinical correctness.",
        "- Do not interpret these counts as accuracy or as evidence of MedQA performance.",
        "",
    ]
    return "\n".join(sections)


def _format_match_rate(matched: int, processed: int) -> str:
    if processed == 0:
        return "n/a"
    return f"{(matched / processed) * 100:.1f}%"


def _format_top_topics_table(
    counts: Counter, total_matched: int, top_n: int
) -> str:
    if not counts:
        return "_No matched topics._"
    rows = ["| Topic | Count | Share of matched |", "| --- | ---: | ---: |"]
    for topic, count in sorted(
        counts.most_common(top_n), key=lambda item: (-item[1], item[0])
    ):
        share = (count / total_matched) if total_matched else 0.0
        rows.append(f"| {topic} | {count} | {share * 100:.1f}% |")
    return "\n".join(rows)


def _format_full_topic_table(counts: Counter) -> str:
    if not counts:
        return "_No matched topics._"
    rows = ["| Topic | Count |", "| --- | ---: |"]
    for topic, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        rows.append(f"| {topic} | {count} |")
    return "\n".join(rows)


def _format_dominance_section(
    dominance: tuple[str, float] | None, threshold: float
) -> str:
    threshold_pct = f"{threshold * 100:.0f}%"
    if dominance is None:
        return f"_No single matched topic exceeds the {threshold_pct} threshold._"
    topic, share = dominance
    return (
        f"⚠ The topic **{topic}** accounts for "
        f"{share * 100:.1f}% of matched records, exceeding the "
        f"{threshold_pct} threshold. Consider whether this reflects topic "
        "prevalence in the input, overly broad keyword/topic matching, or "
        "both. Inspect a sample of these matches manually."
    )


def _format_record_samples(
    records: Sequence[Mapping[str, Any]], *, fallback: bool
) -> str:
    if not records:
        return "_No records to sample._" if not fallback else "_No fallback records._"

    blocks: list[str] = []
    for record in records:
        rid = record.get("id") or "—"
        topic = record.get("matched_topic") or "_(none)_"
        status = record.get("status") or ("fallback" if fallback else "matched")
        question = " ".join(str(record.get("question", "")).split()) or "_(missing)_"
        answer = truncate_answer(record.get("answer", ""))
        graph_path = record.get("graph_path")
        graph_line = f"`{graph_path}`" if graph_path else "_none_"
        matched_terms = _format_matched_terms(record.get("matched_terms"))
        confidence = str(record.get("filter_confidence") or "_not available_")

        blocks.append(
            "\n".join(
                [
                    f"### {rid} — {topic} ({status})",
                    "",
                    f"- **Question:** {question}",
                    f"- **Filter confidence:** {confidence}",
                    f"- **Matched terms:** {matched_terms}",
                    f"- **Answer:** {answer or '_(empty)_'}",
                    f"- **Graph:** {graph_line}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _format_matched_terms(value: Any) -> str:
    """Format preprocessing matched terms for audit samples."""

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return "_not available_"

    terms = [" ".join(str(term).split()) for term in value if str(term).strip()]
    if not terms:
        return "_none_"

    return ", ".join(f"`{term}`" for term in terms)


def _format_filter_confidence_table(counts: Counter) -> str:
    """Render a filter-confidence summary table if rows include it."""

    if not counts:
        return "_No filter confidence labels present._"

    rows = ["| Filter confidence | Count |", "| --- | ---: |"]
    for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        rows.append(f"| {label} | {count} |")
    return "\n".join(rows)
