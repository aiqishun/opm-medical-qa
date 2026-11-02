"""Tests for the qualitative batch-audit helpers in ``src/evaluation/audit.py``."""

from __future__ import annotations

import unittest
from collections import Counter
from pathlib import Path
from random import Random

from evaluation.audit import (
    DEFAULT_DOMINANCE_THRESHOLD,
    build_audit_markdown,
    filter_confidence_frequency,
    find_dominant_topic,
    sample_records,
    topic_frequency,
    truncate_answer,
)


def _matched(
    topic,
    *,
    rid="case",
    question="Q?",
    answer="A.",
    graph_path=None,
    matched_terms=None,
    filter_confidence=None,
):
    return {
        "id": rid,
        "question": question,
        "matched_topic": topic,
        "answer": answer,
        "explanation": "",
        "reasoning_path": [],
        "graph_path": graph_path,
        "matched_terms": matched_terms,
        "filter_confidence": filter_confidence,
        "status": "matched",
    }


def _fallback(*, rid="fb", question="?", answer="No match."):
    return {
        "id": rid,
        "question": question,
        "matched_topic": None,
        "answer": answer,
        "explanation": "",
        "reasoning_path": [],
        "graph_path": None,
        "status": "fallback",
    }


class TopicFrequencyTests(unittest.TestCase):
    def test_counts_matched_topics(self) -> None:
        results = [
            _matched("hypertension"),
            _matched("hypertension"),
            _matched("angina"),
        ]
        counts = topic_frequency(results)
        self.assertEqual(counts["hypertension"], 2)
        self.assertEqual(counts["angina"], 1)

    def test_skips_records_without_matched_topic(self) -> None:
        results = [_matched("angina"), {"matched_topic": None}, {}]
        self.assertEqual(topic_frequency(results), Counter({"angina": 1}))

    def test_empty_input(self) -> None:
        self.assertEqual(topic_frequency([]), Counter())


class FilterConfidenceFrequencyTests(unittest.TestCase):
    def test_counts_filter_confidence_labels(self) -> None:
        results = [
            _matched("angina", filter_confidence="high_confidence"),
            _matched("arrhythmia", filter_confidence="high_confidence"),
            _matched("heart failure", filter_confidence="strict"),
            _fallback(),
        ]

        counts = filter_confidence_frequency(results)

        self.assertEqual(counts["high_confidence"], 2)
        self.assertEqual(counts["strict"], 1)
        self.assertNotIn("None", counts)


class FindDominantTopicTests(unittest.TestCase):
    def test_returns_dominant_topic_above_threshold(self) -> None:
        counts = Counter({"a": 6, "b": 2, "c": 2})
        result = find_dominant_topic(counts, total_matched=10, threshold=0.4)
        self.assertEqual(result, ("a", 0.6))

    def test_returns_none_below_threshold(self) -> None:
        counts = Counter({"a": 4, "b": 3, "c": 3})
        # 4/10 = 0.4, threshold is strict greater-than
        self.assertIsNone(find_dominant_topic(counts, 10, 0.4))

    def test_uses_strict_greater_than(self) -> None:
        # Exactly at threshold should NOT trigger
        counts = Counter({"a": 5, "b": 5})
        self.assertIsNone(find_dominant_topic(counts, 10, 0.5))

    def test_default_threshold_is_forty_percent(self) -> None:
        counts = Counter({"a": 5, "b": 4})
        result = find_dominant_topic(counts, total_matched=9)
        self.assertIsNotNone(result)
        topic, _ = result
        self.assertEqual(topic, "a")
        # Confirm the constant
        self.assertEqual(DEFAULT_DOMINANCE_THRESHOLD, 0.40)

    def test_zero_matched_returns_none(self) -> None:
        self.assertIsNone(find_dominant_topic(Counter({"a": 0}), 0))

    def test_empty_counts_returns_none(self) -> None:
        self.assertIsNone(find_dominant_topic(Counter(), 0))


class TruncateAnswerTests(unittest.TestCase):
    def test_short_answer_unchanged(self) -> None:
        self.assertEqual(truncate_answer("Short answer."), "Short answer.")

    def test_long_answer_is_truncated_with_ellipsis(self) -> None:
        text = "x" * 200
        out = truncate_answer(text, max_chars=50)
        self.assertEqual(len(out), 50)
        self.assertTrue(out.endswith("…"))

    def test_collapses_internal_whitespace(self) -> None:
        text = "  Lots\nof\twhitespace   here.  "
        self.assertEqual(truncate_answer(text), "Lots of whitespace here.")

    def test_handles_none_or_empty_input(self) -> None:
        self.assertEqual(truncate_answer(None), "")
        self.assertEqual(truncate_answer(""), "")


class SampleRecordsTests(unittest.TestCase):
    def test_returns_all_records_when_sample_size_exceeds_population(self) -> None:
        records = [_matched("a", rid=f"r{i}") for i in range(5)]
        out = sample_records(records, sample_size=10, rng=Random(0))
        self.assertEqual(len(out), 5)

    def test_returns_at_most_sample_size_records(self) -> None:
        records = [_matched("a", rid=f"r{i}") for i in range(50)]
        out = sample_records(records, sample_size=10, rng=Random(0))
        self.assertEqual(len(out), 10)

    def test_sampling_is_deterministic_for_fixed_seed(self) -> None:
        records = [_matched("a", rid=f"r{i}") for i in range(50)]
        out1 = sample_records(records, sample_size=10, rng=Random(42))
        out2 = sample_records(records, sample_size=10, rng=Random(42))
        self.assertEqual(
            [r["id"] for r in out1],
            [r["id"] for r in out2],
        )

    def test_zero_sample_size_returns_empty(self) -> None:
        records = [_matched("a", rid=f"r{i}") for i in range(5)]
        self.assertEqual(sample_records(records, 0, Random(0)), [])

    def test_empty_population_returns_empty(self) -> None:
        self.assertEqual(sample_records([], 5, Random(0)), [])


class BuildAuditMarkdownTests(unittest.TestCase):
    def _build(self, **overrides):
        defaults = {
            "input_path": Path("results.jsonl"),
            "total_records": 0,
            "matched_count": 0,
            "fallback_count": 0,
            "topic_counts": Counter(),
            "sampled_matched": [],
            "sampled_fallback": [],
            "dominance": None,
            "sample_size": 30,
            "seed": 42,
        }
        defaults.update(overrides)
        return build_audit_markdown(**defaults)

    def test_includes_header_and_qualitative_disclaimer(self) -> None:
        md = self._build()
        self.assertIn("# OPM Medical QA — Batch Results Audit", md)
        self.assertIn("Qualitative audit", md)
        self.assertIn("not** an accuracy evaluation", md)
        self.assertIn("no** medical accuracy claims", md)

    def test_counts_section(self) -> None:
        md = self._build(total_records=100, matched_count=98, fallback_count=2)
        self.assertIn("| Total records | 100 |", md)
        self.assertIn("| Matched | 98 |", md)
        self.assertIn("| Fallback | 2 |", md)
        self.assertIn("| Match rate | 98.0% |", md)

    def test_top_topics_table_sorted_by_count_then_name(self) -> None:
        counts = Counter({"angina": 5, "arrhythmia": 5, "myocardial infarction": 10})
        md = self._build(matched_count=20, topic_counts=counts)
        # Confirm the top entry is the most-frequent topic and the share column
        # is rendered as a percentage.
        self.assertIn("| myocardial infarction | 10 | 50.0% |", md)
        # Ties sort alphabetically — angina before arrhythmia
        angina_pos = md.find("| angina | 5 |")
        arr_pos = md.find("| arrhythmia | 5 |")
        self.assertTrue(0 < angina_pos < arr_pos)

    def test_dominance_warning_rendered_when_present(self) -> None:
        md = self._build(
            matched_count=10,
            topic_counts=Counter({"a": 6, "b": 4}),
            dominance=("a", 0.6),
        )
        self.assertIn("⚠", md)
        self.assertIn("**a**", md)
        self.assertIn("60.0%", md)
        self.assertIn("40% threshold", md)

    def test_dominance_section_falls_through_when_absent(self) -> None:
        md = self._build()
        self.assertIn("No single matched topic exceeds the 40% threshold", md)
        self.assertNotIn("⚠", md)

    def test_sampled_matched_block(self) -> None:
        md = self._build(
            sampled_matched=[
                _matched(
                    "hypertension",
                    rid="case-001",
                    question="What causes hypertension?",
                    answer="Hypertension can result from increased vascular resistance.",
                    graph_path="outputs/graphs/case-001.json",
                    matched_terms=["hypertension", "blood pressure"],
                    filter_confidence="broad",
                )
            ],
        )
        self.assertIn("### case-001 — hypertension (matched)", md)
        self.assertIn("**Question:** What causes hypertension?", md)
        self.assertIn("**Filter confidence:** broad", md)
        self.assertIn("**Matched terms:** `hypertension`, `blood pressure`", md)
        self.assertIn("**Answer:** Hypertension can result from", md)
        self.assertIn("`outputs/graphs/case-001.json`", md)

    def test_sampled_fallback_block_shows_none_for_graph(self) -> None:
        md = self._build(sampled_fallback=[_fallback(rid="fb-001", question="???")])
        self.assertIn("### fb-001 — _(none)_ (fallback)", md)
        self.assertIn("**Filter confidence:** _not available_", md)
        self.assertIn("**Matched terms:** _not available_", md)
        self.assertIn("**Graph:** _none_", md)

    def test_filter_confidence_section_renders_counts(self) -> None:
        md = self._build(
            filter_confidence_counts=Counter({"high_confidence": 3, "strict": 1})
        )

        self.assertIn("## Filter confidence", md)
        self.assertIn("| high_confidence | 3 |", md)
        self.assertIn("| strict | 1 |", md)

    def test_filter_confidence_section_handles_missing_labels(self) -> None:
        md = self._build()

        self.assertIn("_No filter confidence labels present._", md)

    def test_empty_samples_show_friendly_messages(self) -> None:
        md = self._build()
        self.assertIn("_No records to sample._", md)
        self.assertIn("_No fallback records._", md)

    def test_zero_processed_match_rate_is_n_a(self) -> None:
        md = self._build(total_records=0, matched_count=0, fallback_count=0)
        self.assertIn("| Match rate | n/a |", md)

    def test_input_path_and_seed_appear_in_header(self) -> None:
        md = self._build(input_path=Path("/tmp/in.jsonl"), seed=123, sample_size=7)
        self.assertIn("- Input: `/tmp/in.jsonl`", md)
        self.assertIn("- Sample size per bucket: 7", md)
        self.assertIn("- Random seed: 123", md)


if __name__ == "__main__":
    unittest.main()
