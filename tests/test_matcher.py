"""Tests for :class:`QuestionMatcher`."""

from __future__ import annotations

import unittest

from reasoning.matcher import QuestionMatcher
from reasoning.topic import CardiologyTopic


def _topic(**overrides: object) -> CardiologyTopic:
    base: dict = {
        "name": "myocardial infarction",
        "question_patterns": ["What causes myocardial infarction?"],
        "keywords": ["heart attack", "blocked artery"],
        "answer": "answer",
        "explanation": "explanation",
        "reasoning_path": ["Atherosclerosis", "Coronary artery blockage"],
        "opm_objects": ["Coronary artery"],
        "opm_processes": ["Plaque build-up"],
        "opm_states": ["Narrowed artery"],
        "opm_links": [
            {
                "source": "Plaque build-up",
                "relationship": "blocks",
                "target": "Coronary artery",
            }
        ],
    }
    base.update(overrides)
    return CardiologyTopic.from_dict(base)


class QuestionMatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matcher = QuestionMatcher()

    def test_exact_question_pattern_scores_high(self) -> None:
        topic = _topic()
        score = self.matcher.score("What causes myocardial infarction?", topic)
        self.assertGreaterEqual(score, 3)

    def test_keyword_match_scores_above_zero(self) -> None:
        topic = _topic()
        score = self.matcher.score("Tell me about heart attack risks.", topic)
        self.assertGreater(score, 0)

    def test_unrelated_question_scores_zero(self) -> None:
        topic = _topic()
        score = self.matcher.score("How do volcanoes form?", topic)
        self.assertEqual(score, 0)

    def test_normalisation_ignores_punctuation_and_case(self) -> None:
        topic = _topic()
        with_punct = self.matcher.score("MYOCARDIAL... infarction!?", topic)
        without_punct = self.matcher.score("myocardial infarction", topic)
        self.assertEqual(with_punct, without_punct)

    def test_empty_question_scores_zero(self) -> None:
        topic = _topic()
        self.assertEqual(self.matcher.score("", topic), 0)
        self.assertEqual(self.matcher.score("   ", topic), 0)

    def test_stopwords_do_not_drive_match(self) -> None:
        topic = _topic(
            question_patterns=["What causes alpha syndrome?"],
            keywords=[],
            reasoning_path=["alpha onset", "alpha syndrome"],
            opm_objects=["alpha tissue"],
            opm_processes=["alpha process"],
            opm_states=["alpha state"],
            opm_links=[
                {
                    "source": "alpha process",
                    "relationship": "leads to",
                    "target": "alpha syndrome",
                }
            ],
        )
        self.assertEqual(self.matcher.score("what is the cause", topic), 0)

    def test_phrase_weight_is_configurable(self) -> None:
        topic = _topic()
        weighted = QuestionMatcher(phrase_weight=10)
        baseline = QuestionMatcher(phrase_weight=1)
        question = "What causes myocardial infarction?"

        self.assertGreater(
            weighted.score(question, topic),
            baseline.score(question, topic),
        )


if __name__ == "__main__":
    unittest.main()
