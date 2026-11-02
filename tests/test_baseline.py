"""Tests for the keyword-only baseline matcher and comparison summary."""

from __future__ import annotations

import unittest
from pathlib import Path

from evaluation.baseline import (
    BaselineResult,
    KeywordBaselineMatcher,
    build_baseline_comparison_markdown,
)
from reasoning.topic import CardiologyTopic, load_topics


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KB = PROJECT_ROOT / "data" / "processed" / "cardiology_knowledge.json"


def _make_topic(
    name: str,
    keywords: list[str] | None = None,
) -> CardiologyTopic:
    """Build a minimal topic for matcher tests."""
    return CardiologyTopic(
        name=name,
        question_patterns=[],
        answer="",
        explanation="",
        reasoning_path=[],
        opm_objects=[],
        opm_processes=[],
        opm_states=[],
        opm_links=[],
        keywords=keywords or [],
    )


class BaselineResultTests(unittest.TestCase):
    def test_is_match_true_for_topic(self) -> None:
        self.assertTrue(BaselineResult("hypertension").is_match)

    def test_is_match_false_for_none(self) -> None:
        self.assertFalse(BaselineResult(None).is_match)


class KeywordBaselineMatcherTests(unittest.TestCase):
    def test_matches_via_keyword_substring(self) -> None:
        topics = [_make_topic("angina", keywords=["chest pain"])]
        result = KeywordBaselineMatcher(topics).answer(
            "Patient with chest pain on exertion."
        )
        self.assertEqual(result.matched_topic, "angina")

    def test_matches_via_topic_name(self) -> None:
        topics = [_make_topic("hypertension", keywords=[])]
        result = KeywordBaselineMatcher(topics).answer("What is hypertension?")
        self.assertEqual(result.matched_topic, "hypertension")

    def test_returns_none_for_no_match(self) -> None:
        topics = [_make_topic("angina", keywords=["chest pain"])]
        result = KeywordBaselineMatcher(topics).answer("How do glaciers form?")
        self.assertIsNone(result.matched_topic)
        self.assertFalse(result.is_match)

    def test_matching_is_case_insensitive(self) -> None:
        topics = [_make_topic("Angina", keywords=["Chest Pain"])]
        result = KeywordBaselineMatcher(topics).answer("CHEST PAIN reported.")
        self.assertEqual(result.matched_topic, "Angina")

    def test_picks_topic_with_most_keyword_hits(self) -> None:
        topics = [
            _make_topic("angina", keywords=["chest pain"]),
            _make_topic(
                "myocardial infarction",
                keywords=["heart attack", "coronary blockage"],
            ),
        ]
        result = KeywordBaselineMatcher(topics).answer(
            "Coronary blockage triggering an acute heart attack."
        )
        self.assertEqual(result.matched_topic, "myocardial infarction")

    def test_first_declared_wins_on_tie(self) -> None:
        topics = [
            _make_topic("first", keywords=["shared"]),
            _make_topic("second", keywords=["shared"]),
        ]
        result = KeywordBaselineMatcher(topics).answer("Question with shared word.")
        self.assertEqual(result.matched_topic, "first")

    def test_duplicate_phrase_in_name_and_keywords_does_not_double_count(self) -> None:
        # The name and a keyword that match the same string collapse into one
        # phrase via the matcher's internal set, so a single occurrence counts
        # once. This means topics where name appears in keywords don't get an
        # unfair scoring boost.
        topics = [
            _make_topic("angina", keywords=["angina", "chest pain"]),
            _make_topic("other", keywords=["chest pain"]),
        ]
        result = KeywordBaselineMatcher(topics).answer("Chest pain only.")
        # Both topics get exactly one hit ("chest pain"); first declared wins.
        self.assertEqual(result.matched_topic, "angina")

    def test_empty_topics_always_falls_back(self) -> None:
        result = KeywordBaselineMatcher([]).answer("Anything at all.")
        self.assertIsNone(result.matched_topic)

    def test_blank_question_falls_back(self) -> None:
        topics = [_make_topic("angina", keywords=["chest pain"])]
        result = KeywordBaselineMatcher(topics).answer("")
        self.assertIsNone(result.matched_topic)

    def test_works_against_bundled_knowledge_base(self) -> None:
        # Smoke test using the real KB: a question that obviously mentions
        # multiple keywords for a topic must match that topic.
        topics = load_topics(DEFAULT_KB)
        matcher = KeywordBaselineMatcher(topics)
        result = matcher.answer(
            "Coronary blockage triggering an acute heart attack best describes which condition?"
        )
        self.assertEqual(result.matched_topic, "myocardial infarction")

    def test_bundled_kb_falls_back_for_unrelated_question(self) -> None:
        topics = load_topics(DEFAULT_KB)
        matcher = KeywordBaselineMatcher(topics)
        result = matcher.answer("How do glaciers form in mountain regions?")
        self.assertIsNone(result.matched_topic)


def _result_row(
    *,
    rid: str = "case",
    baseline_topic: str | None = None,
    opm_topic: str | None = None,
    has_path: bool = False,
    has_graph: bool = False,
    question: str = "Sample question?",
) -> dict:
    return {
        "id": rid,
        "question": question,
        "baseline_matched_topic": baseline_topic,
        "baseline_status": "matched" if baseline_topic else "fallback",
        "opm_matched_topic": opm_topic,
        "opm_status": "matched" if opm_topic else "fallback",
        "opm_has_reasoning_path": has_path,
        "opm_has_graph": has_graph,
    }


class BuildBaselineComparisonMarkdownTests(unittest.TestCase):
    def test_includes_header_and_disclaimer(self) -> None:
        md = build_baseline_comparison_markdown(
            input_path=Path("input.jsonl"),
            output_path=Path("out.jsonl"),
            total_records=0,
            skipped_missing_question=0,
            results=[],
        )
        self.assertIn("# OPM Medical QA — Baseline Comparison", md)
        self.assertIn("not** a full MedQA", md)
        self.assertIn("no** medical accuracy claims", md)

    def test_counts_each_axis_independently(self) -> None:
        results = [
            _result_row(rid="a", baseline_topic="angina", opm_topic="angina", has_path=True, has_graph=True),
            _result_row(rid="b", baseline_topic=None, opm_topic="hypertension", has_path=True, has_graph=True),
            _result_row(rid="c", baseline_topic="angina", opm_topic=None, has_path=False, has_graph=False),
            _result_row(rid="d", baseline_topic=None, opm_topic=None, has_path=False, has_graph=False),
        ]
        md = build_baseline_comparison_markdown(
            input_path=Path("input.jsonl"),
            output_path=Path("out.jsonl"),
            total_records=4,
            skipped_missing_question=0,
            results=results,
        )
        self.assertIn("| Total input records | 4 |", md)
        self.assertIn("| Questions processed | 4 |", md)
        self.assertIn("| Baseline matched | 2 |", md)
        self.assertIn("| Baseline fallback | 2 |", md)
        self.assertIn("| OPM QA matched | 2 |", md)
        self.assertIn("| OPM QA fallback | 2 |", md)
        self.assertIn("| OPM reasoning paths produced | 2 |", md)
        self.assertIn("| OPM graphs produced | 2 |", md)

    def test_counts_skipped_questions_separately(self) -> None:
        md = build_baseline_comparison_markdown(
            input_path=Path("input.jsonl"),
            output_path=Path("out.jsonl"),
            total_records=5,
            skipped_missing_question=3,
            results=[
                _result_row(rid="a", baseline_topic="angina", opm_topic="angina"),
                _result_row(rid="b"),
            ],
        )
        self.assertIn("| Total input records | 5 |", md)
        self.assertIn("| Questions processed | 2 |", md)
        self.assertIn("| Skipped (missing question) | 3 |", md)

    def test_per_question_table_lists_each_row(self) -> None:
        md = build_baseline_comparison_markdown(
            input_path=Path("input.jsonl"),
            output_path=Path("out.jsonl"),
            total_records=2,
            skipped_missing_question=0,
            results=[
                _result_row(
                    rid="mi-001",
                    baseline_topic="angina",
                    opm_topic="myocardial infarction",
                    has_path=True,
                    has_graph=True,
                ),
                _result_row(rid="fb-001"),
            ],
        )
        self.assertIn("| mi-001 | angina | myocardial infarction | yes | yes |", md)
        self.assertIn("| fb-001 | _(fallback)_ | _(fallback)_ | no | no |", md)

    def test_empty_results_section_message(self) -> None:
        md = build_baseline_comparison_markdown(
            input_path=Path("input.jsonl"),
            output_path=Path("out.jsonl"),
            total_records=0,
            skipped_missing_question=0,
            results=[],
        )
        self.assertIn("_No questions processed._", md)

    def test_per_question_table_handles_missing_id(self) -> None:
        md = build_baseline_comparison_markdown(
            input_path=Path("input.jsonl"),
            output_path=Path("out.jsonl"),
            total_records=1,
            skipped_missing_question=0,
            results=[_result_row(rid="", baseline_topic="angina", opm_topic="angina")],
        )
        self.assertIn("| — | angina | angina |", md)


if __name__ == "__main__":
    unittest.main()
