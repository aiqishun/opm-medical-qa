"""Tests for the Markdown batch summary helper."""

from __future__ import annotations

import unittest
from pathlib import Path

from evaluation.summary import build_markdown_summary


def _matched(topic: str, question: str, graph_path: str = "g.json") -> dict:
    return {
        "id": None,
        "question": question,
        "matched_topic": topic,
        "answer": f"{topic} answer.",
        "explanation": f"{topic} explanation.",
        "reasoning_path": ["a", "b"],
        "graph_path": graph_path,
        "status": "matched",
    }


def _fallback(question: str) -> dict:
    return {
        "id": None,
        "question": question,
        "matched_topic": None,
        "answer": "no match",
        "explanation": "fallback",
        "reasoning_path": [],
        "graph_path": None,
        "status": "fallback",
    }


def _build(results: list[dict], **overrides) -> str:
    kwargs = {
        "input_path": Path("data/in.jsonl"),
        "output_path": Path("results.jsonl"),
        "graphs_dir": Path("graphs/"),
        "total_records": len(results),
        "skipped_missing_question": 0,
        "results": results,
    }
    kwargs.update(overrides)
    return build_markdown_summary(**kwargs)


class HeaderAndDisclaimerTests(unittest.TestCase):
    def test_header_and_prototype_disclaimer_present(self) -> None:
        markdown = _build([])

        self.assertIn("# OPM Medical QA — Batch Summary", markdown)
        self.assertIn("not** a full MedQA evaluation", markdown)
        self.assertIn("research artifacts", markdown)


class AllMatchedTests(unittest.TestCase):
    def test_counts_section_for_all_matched(self) -> None:
        results = [
            _matched("hypertension", "What causes hypertension?"),
            _matched("hypertension", "Why does hypertension happen?"),
            _matched("arrhythmia", "What causes arrhythmia?"),
        ]
        markdown = _build(results)

        self.assertIn("| Total input records | 3 |", markdown)
        self.assertIn("| Questions processed | 3 |", markdown)
        self.assertIn("| Matched | 3 |", markdown)
        self.assertIn("| Fallback | 0 |", markdown)
        self.assertIn("| Match rate | 100.0% |", markdown)
        self.assertIn("| Graph files generated | 3 |", markdown)

    def test_topic_frequency_table_sorted_by_count_then_name(self) -> None:
        results = [
            _matched("arrhythmia", "q1"),
            _matched("hypertension", "q2"),
            _matched("hypertension", "q3"),
        ]
        markdown = _build(results)

        topic_section = markdown.split("## Matched topic frequency", 1)[1]
        topic_section = topic_section.split("## ", 1)[0]
        # hypertension (2) should appear before arrhythmia (1).
        self.assertLess(
            topic_section.index("| hypertension | 2 |"),
            topic_section.index("| arrhythmia | 1 |"),
        )

    def test_inputs_and_outputs_paths_quoted(self) -> None:
        markdown = _build(
            [_matched("hypertension", "q")],
            input_path=Path("data/processed/sample.jsonl"),
            output_path=Path("experiments/results/out.jsonl"),
            graphs_dir=Path("outputs/graphs/batch"),
        )

        self.assertIn("- Input: `data/processed/sample.jsonl`", markdown)
        self.assertIn("- Results JSONL: `experiments/results/out.jsonl`", markdown)
        self.assertIn("- Graphs directory: `outputs/graphs/batch`", markdown)

    def test_fallback_section_shows_none_marker_when_all_matched(self) -> None:
        markdown = _build([_matched("hypertension", "q")])

        fallback_section = markdown.split("## Fallback questions", 1)[1].strip()
        self.assertEqual(fallback_section, "_None._")


class FallbackTests(unittest.TestCase):
    def test_fallback_questions_listed(self) -> None:
        results = [
            _matched("hypertension", "What causes hypertension?"),
            _fallback("How do glaciers form?"),
            _fallback("What is photosynthesis?"),
        ]
        markdown = _build(results)

        self.assertIn("| Matched | 1 |", markdown)
        self.assertIn("| Fallback | 2 |", markdown)
        self.assertIn("| Match rate | 33.3% |", markdown)
        self.assertIn("- How do glaciers form?", markdown)
        self.assertIn("- What is photosynthesis?", markdown)

    def test_match_rate_excludes_skipped_records(self) -> None:
        markdown = _build(
            [_matched("hypertension", "q"), _fallback("noise")],
            total_records=5,
            skipped_missing_question=3,
        )

        self.assertIn("| Total input records | 5 |", markdown)
        self.assertIn("| Skipped (missing question) | 3 |", markdown)
        self.assertIn("| Questions processed | 2 |", markdown)
        # 1 of 2 processed = 50.0% (skipped not counted)
        self.assertIn("| Match rate | 50.0% |", markdown)


class EmptyTests(unittest.TestCase):
    def test_empty_results_produce_n_a_match_rate(self) -> None:
        markdown = _build([])

        self.assertIn("| Total input records | 0 |", markdown)
        self.assertIn("| Questions processed | 0 |", markdown)
        self.assertIn("| Matched | 0 |", markdown)
        self.assertIn("| Fallback | 0 |", markdown)
        self.assertIn("| Match rate | n/a |", markdown)
        self.assertIn("| Graph files generated | 0 |", markdown)

    def test_empty_results_show_no_topics_marker(self) -> None:
        markdown = _build([])
        topic_section = markdown.split("## Matched topic frequency", 1)[1]
        topic_section = topic_section.split("## ", 1)[0].strip()
        self.assertEqual(topic_section, "_No matched topics._")

    def test_only_skipped_records(self) -> None:
        markdown = _build(
            [], total_records=4, skipped_missing_question=4
        )

        self.assertIn("| Total input records | 4 |", markdown)
        self.assertIn("| Skipped (missing question) | 4 |", markdown)
        self.assertIn("| Match rate | n/a |", markdown)


class RobustnessTests(unittest.TestCase):
    def test_matched_record_without_topic_is_not_counted(self) -> None:
        # Defensive: status=matched but matched_topic missing should not appear
        # in the topic table (it just means an upstream bug, but we still render).
        odd = _matched("hypertension", "q")
        odd["matched_topic"] = None
        markdown = _build([odd])

        topic_section = markdown.split("## Matched topic frequency", 1)[1]
        topic_section = topic_section.split("## ", 1)[0].strip()
        self.assertEqual(topic_section, "_No matched topics._")

    def test_fallback_with_blank_question_is_skipped_in_list(self) -> None:
        results = [_fallback("   "), _fallback("real question")]
        markdown = _build(results)

        fallback_section = markdown.split("## Fallback questions", 1)[1].strip()
        # Blank-question entries should not produce empty "- " bullet lines.
        self.assertEqual(
            fallback_section.splitlines(),
            ["- real question"],
        )


if __name__ == "__main__":
    unittest.main()
