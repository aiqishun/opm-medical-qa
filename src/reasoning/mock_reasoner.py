"""Small rule-based reasoner for cardiology QA examples.

The reasoner is intentionally simple for the research prototype. It receives a
list of examples from a JSON knowledge base, compares the user's question with
each example's question pattern, and returns the closest match.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class QAResult:
    """Structured answer returned by the rule-based reasoner."""

    answer: str
    explanation: str
    reasoning_path: List[str]
    matched_question_pattern: str | None = None
    match_score: float = 0.0


@dataclass(frozen=True)
class CardiologyExample:
    """One cardiology QA example loaded from the knowledge base."""

    condition: str
    question_pattern: str
    keywords: List[str]
    answer: str
    explanation: str
    reasoning_path: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CardiologyExample":
        """Create a typed example from JSON data."""

        return cls(
            condition=data["condition"],
            question_pattern=data["question_pattern"],
            keywords=list(data.get("keywords", [])),
            answer=data["answer"],
            explanation=data["explanation"],
            reasoning_path=list(data["reasoning_path"]),
        )


class RuleBasedCardiologyReasoner:
    """Answer cardiology questions by matching against known examples."""

    def __init__(
        self,
        examples: Iterable[CardiologyExample],
        minimum_match_score: float = 0.30,
    ) -> None:
        self.examples = list(examples)
        self.minimum_match_score = minimum_match_score

    def answer(self, question: str) -> QAResult:
        """Return an answer, explanation, and reasoning path.

        If no example is similar enough, the result explains what topics are
        currently available instead of pretending to know the answer.
        """

        best_example, best_score = self._find_best_example(question)

        if best_example is None or best_score < self.minimum_match_score:
            known_topics = ", ".join(example.condition for example in self.examples)

            return QAResult(
                answer=(
                    "I could not find a close cardiology example for this "
                    "question in the current prototype knowledge base."
                ),
                explanation=(
                    "The rule-based matcher compares the input question with "
                    f"known examples. Available topics are: {known_topics}."
                ),
                reasoning_path=[],
                match_score=best_score,
            )

        return QAResult(
            answer=best_example.answer,
            explanation=best_example.explanation,
            reasoning_path=best_example.reasoning_path,
            matched_question_pattern=best_example.question_pattern,
            match_score=best_score,
        )

    def _find_best_example(
        self,
        question: str,
    ) -> tuple[CardiologyExample | None, float]:
        """Find the example with the highest similarity score."""

        if not self.examples:
            return None, 0.0

        scored_examples = [
            (example, self._score_question(question, example))
            for example in self.examples
        ]
        return max(scored_examples, key=lambda item: item[1])

    def _score_question(self, question: str, example: CardiologyExample) -> float:
        """Score how well an input question matches one knowledge example."""

        searchable_text = " ".join(
            [
                example.question_pattern,
                example.condition,
                *example.keywords,
                *example.reasoning_path,
            ]
        )
        question_text = self._normalize(question)
        example_text = self._normalize(searchable_text)

        pattern_score = SequenceMatcher(
            None,
            question_text,
            self._normalize(example.question_pattern),
        ).ratio()
        token_score = self._token_overlap(question_text, example_text)

        # Exact condition or keyword phrases are strong signals. This lets
        # beginner-friendly synonyms such as "heart attack" or "high blood
        # pressure" match the right example without a clinical NLP model.
        if self._contains_known_phrase(question_text, example):
            return max(0.85, token_score)

        # Token overlap carries most of the score so generic wording like
        # "what causes" does not dominate the medical concept match.
        return (0.75 * token_score) + (0.25 * pattern_score)

    def _normalize(self, text: str) -> str:
        """Lowercase text and remove punctuation for simple matching."""

        return " ".join(re.findall(r"[a-z0-9]+", text.lower()))

    def _token_overlap(self, question_text: str, example_text: str) -> float:
        """Compute the fraction of shared tokens between two strings."""

        question_tokens = self._important_tokens(question_text)
        example_tokens = self._important_tokens(example_text)

        if not question_tokens or not example_tokens:
            return 0.0

        shared_tokens = question_tokens & example_tokens
        all_tokens = question_tokens | example_tokens
        return len(shared_tokens) / len(all_tokens)

    def _important_tokens(self, text: str) -> set[str]:
        """Remove common question words so medical terms drive matching."""

        stopwords = {
            "a",
            "an",
            "and",
            "are",
            "can",
            "cause",
            "caused",
            "causes",
            "do",
            "does",
            "happen",
            "how",
            "is",
            "the",
            "to",
            "what",
            "why",
        }
        return {token for token in text.split() if token not in stopwords}

    def _contains_known_phrase(
        self,
        question_text: str,
        example: CardiologyExample,
    ) -> bool:
        """Check for exact condition or keyword phrase matches."""

        phrases = [example.condition, *example.keywords]
        normalized_phrases = [self._normalize(phrase) for phrase in phrases]
        return any(phrase and phrase in question_text for phrase in normalized_phrases)


# Backwards-compatible name from the first prototype.
MockCardiologyReasoner = RuleBasedCardiologyReasoner
