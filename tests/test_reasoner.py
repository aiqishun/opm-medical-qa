"""Tests for :class:`RuleBasedCardiologyReasoner`."""

from __future__ import annotations

import unittest

from reasoning.reasoner import RuleBasedCardiologyReasoner
from reasoning.topic import CardiologyTopic


def _topic(name: str, **overrides: object) -> CardiologyTopic:
    base: dict = {
        "name": name,
        "question_patterns": [f"What causes {name}?"],
        "keywords": [name],
        "answer": f"{name} answer.",
        "explanation": f"{name} explanation.",
        "reasoning_path": [f"{name} trigger", name],
        "opm_objects": [f"{name} object"],
        "opm_processes": [f"{name} process"],
        "opm_states": [f"{name} state"],
        "opm_links": [
            {
                "source": f"{name} trigger",
                "relationship": "leads to",
                "target": name,
            }
        ],
    }
    base.update(overrides)
    return CardiologyTopic.from_dict(base)


class RuleBasedReasonerTests(unittest.TestCase):
    def test_returns_matched_topic_for_known_question(self) -> None:
        topics = [_topic("hypertension"), _topic("arrhythmia")]
        reasoner = RuleBasedCardiologyReasoner(topics=topics)

        result = reasoner.answer("What causes hypertension?")

        self.assertTrue(result.is_match)
        self.assertEqual(result.matched_topic, "hypertension")
        self.assertEqual(result.answer, "hypertension answer.")
        self.assertEqual(result.reasoning_path, ["hypertension trigger", "hypertension"])
        self.assertFalse(result.graph.is_empty())

    def test_picks_higher_scoring_topic(self) -> None:
        topics = [_topic("hypertension"), _topic("arrhythmia")]
        reasoner = RuleBasedCardiologyReasoner(topics=topics)

        result = reasoner.answer("What causes arrhythmia?")

        self.assertEqual(result.matched_topic, "arrhythmia")

    def test_no_match_returns_transparent_fallback(self) -> None:
        topics = [_topic("hypertension")]
        reasoner = RuleBasedCardiologyReasoner(topics=topics)

        result = reasoner.answer("How do glaciers form?")

        self.assertFalse(result.is_match)
        self.assertIsNone(result.matched_topic)
        self.assertEqual(result.reasoning_path, [])
        self.assertTrue(result.graph.is_empty())
        self.assertIn("hypertension", result.explanation)

    def test_minimum_match_score_filters_weak_matches(self) -> None:
        topics = [_topic("hypertension")]
        strict = RuleBasedCardiologyReasoner(topics=topics, minimum_match_score=100)

        result = strict.answer("What causes hypertension?")

        self.assertFalse(result.is_match)
        self.assertGreater(result.match_score, 0)

    def test_empty_knowledge_base_explains_state(self) -> None:
        reasoner = RuleBasedCardiologyReasoner(topics=[])

        result = reasoner.answer("Anything?")

        self.assertFalse(result.is_match)
        self.assertIn("knowledge base is empty", result.explanation)


if __name__ == "__main__":
    unittest.main()
