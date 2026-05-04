"""Keyword-only baseline matcher and comparison-summary renderer.

The baseline scans each question for direct topic-name or topic-keyword
substring hits — no scoring weights, no content-token overlap, no fuzzy
matching. It returns just a matched topic name or ``None``; it produces no
reasoning path, OPM graph, or natural-language answer.

This is a deliberately weak baseline included only to provide a reference
point for prototype-level comparison against the rule-based OPM reasoner on
the bundled synthetic sample. It makes no medical accuracy claims and the
comparison demonstrates no superiority on the real MedQA dataset.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from reasoning.topic import CardiologyTopic


_PROTOTYPE_NOTE = (
    "> Prototype run on a small synthetic sample. This is **not** a full MedQA "
    "evaluation, makes **no** medical accuracy claims, and demonstrates **no** "
    "superiority on the real MedQA dataset. The baseline is a deliberately "
    "weak keyword-only matcher; the OPM reasoner is the rule-based prototype. "
    "Both are research artifacts."
)


@dataclass(frozen=True)
class BaselineResult:
    """Outcome of one keyword-only match attempt."""

    matched_topic: str | None

    @property
    def is_match(self) -> bool:
        return self.matched_topic is not None


class KeywordBaselineMatcher:
    """Match questions to topics by direct keyword/name substring hits.

    For each topic, the searchable phrase set is ``{topic.name, *topic.keywords}``
    (lowercased and de-duplicated). A topic scores +1 for every distinct phrase
    whose lowercased form appears as a substring of the lowercased question.
    The topic with the highest hit count wins; on ties, the topic declared
    first in the knowledge base wins. With zero hits the result is a fallback
    (``matched_topic=None``).
    """

    def __init__(self, topics: Iterable[CardiologyTopic]) -> None:
        self._topics: list[CardiologyTopic] = list(topics)
        self._phrase_sets: list[frozenset[str]] = [
            frozenset(
                phrase.lower()
                for phrase in (topic.name, *topic.keywords)
                if phrase
            )
            for topic in self._topics
        ]

    def answer(self, question: str) -> BaselineResult:
        normalized = question.lower()
        best_score = 0
        best_topic: str | None = None
        for topic, phrases in zip(self._topics, self._phrase_sets):
            score = sum(1 for phrase in phrases if phrase in normalized)
            if score > best_score:
                best_score = score
                best_topic = topic.name
        return BaselineResult(matched_topic=best_topic)


def build_baseline_comparison_markdown(
    *,
    input_path: Path,
    output_path: Path,
    total_records: int,
    skipped_missing_question: int,
    results: Sequence[Mapping[str, Any]],
) -> str:
    """Render a Markdown summary for a baseline-vs-OPM comparison run.

    ``results`` is the list of per-question dicts written to the comparison
    JSONL (each row carries ``baseline_status``, ``opm_status``,
    ``opm_has_reasoning_path``, and ``opm_has_graph``). The function is pure —
    file I/O is the caller's responsibility.
    """

    processed = len(results)
    baseline_matched = sum(1 for r in results if r.get("baseline_status") == "matched")
    baseline_fallback = processed - baseline_matched
    opm_matched = sum(1 for r in results if r.get("opm_status") == "matched")
    opm_fallback = processed - opm_matched
    opm_paths = sum(1 for r in results if r.get("opm_has_reasoning_path"))
    opm_graphs = sum(1 for r in results if r.get("opm_has_graph"))

    sections = [
        "# OPM Medical QA — Baseline Comparison",
        "",
        _PROTOTYPE_NOTE,
        "",
        "## Inputs and outputs",
        "",
        f"- Input: `{input_path}`",
        f"- Results JSONL: `{output_path}`",
        "",
        "## Counts",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total input records | {total_records} |",
        f"| Questions processed | {processed} |",
        f"| Skipped (missing question) | {skipped_missing_question} |",
        f"| Baseline matched | {baseline_matched} |",
        f"| Baseline fallback | {baseline_fallback} |",
        f"| OPM QA matched | {opm_matched} |",
        f"| OPM QA fallback | {opm_fallback} |",
        f"| OPM reasoning paths produced | {opm_paths} |",
        f"| OPM graphs produced | {opm_graphs} |",
        "",
        "## Per-question outcomes",
        "",
        _format_per_question_table(results),
        "",
        "## Notes",
        "",
        "- **Matched** here means the matcher returned a topic, not that the topic is clinically correct.",
        "- The keyword-only baseline can both miss matches **and** match the wrong topic when an unrelated keyword (e.g. \"chest pain\") happens to appear.",
        "- The OPM reasoner produces a reasoning path and OPM graph only on matched questions; fallbacks return an empty path and an empty graph.",
        "- Counts are over a small synthetic sample; do not generalize them to MedQA or to clinical performance.",
        "",
    ]

    return "\n".join(sections)


def _format_per_question_table(results: Sequence[Mapping[str, Any]]) -> str:
    if not results:
        return "_No questions processed._"

    rows = [
        "| ID | Baseline match | OPM match | Reasoning path | Graph |",
        "| --- | --- | --- | :---: | :---: |",
    ]
    for record in results:
        rid = record.get("id") or "—"
        baseline = record.get("baseline_matched_topic") or "_(fallback)_"
        opm = record.get("opm_matched_topic") or "_(fallback)_"
        path_cell = "yes" if record.get("opm_has_reasoning_path") else "no"
        graph_cell = "yes" if record.get("opm_has_graph") else "no"
        rows.append(f"| {rid} | {baseline} | {opm} | {path_cell} | {graph_cell} |")
    return "\n".join(rows)


def baseline_matched_topic_counts(results: Sequence[Mapping[str, Any]]) -> Counter:
    """Helper: tally baseline matched-topic frequencies (for tests/inspection)."""
    return Counter(
        str(r.get("baseline_matched_topic"))
        for r in results
        if r.get("baseline_status") == "matched" and r.get("baseline_matched_topic")
    )
