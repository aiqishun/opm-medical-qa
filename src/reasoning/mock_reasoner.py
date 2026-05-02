"""Small rule-based reasoner for cardiology QA topics.

The reasoner is intentionally simple for the research prototype. It receives a
list of topics from a JSON knowledge base, compares the user's question with
topic keywords and question patterns, and returns the closest match.
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class QAResult:
    """Structured answer returned by the rule-based reasoner."""

    answer: str
    explanation: str
    reasoning_path: List[str]
    opm_objects: List[str]
    opm_processes: List[str]
    opm_states: List[str]
    opm_links: List[Dict[str, str]]
    matched_topic: str | None = None
    match_score: int = 0


@dataclass(frozen=True)
class CardiologyTopic:
    """One cardiology topic loaded from the knowledge base."""

    name: str
    question_patterns: List[str]
    keywords: List[str]
    answer: str
    explanation: str
    reasoning_path: List[str]
    opm_objects: List[str]
    opm_processes: List[str]
    opm_states: List[str]
    opm_links: List[Dict[str, str]]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CardiologyTopic":
        """Create a typed topic from JSON data."""

        return cls(
            name=data["name"],
            question_patterns=list(data["question_patterns"]),
            keywords=list(data.get("keywords", [])),
            answer=data["answer"],
            explanation=data["explanation"],
            reasoning_path=list(data["reasoning_path"]),
            opm_objects=list(data["opm_objects"]),
            opm_processes=list(data["opm_processes"]),
            opm_states=list(data["opm_states"]),
            opm_links=list(data["opm_links"]),
        )


class RuleBasedCardiologyReasoner:
    """Answer cardiology questions by matching against known topics."""

    def __init__(
        self,
        topics: Iterable[CardiologyTopic],
        minimum_match_score: int = 1,
    ) -> None:
        self.topics = list(topics)
        self.minimum_match_score = minimum_match_score

    def answer(self, question: str) -> QAResult:
        """Return an answer, explanation, and reasoning path.

        If no topic is similar enough, the result explains what topics are
        currently available instead of pretending to know the answer.
        """

        best_topic, best_score = self._find_best_topic(question)

        if best_topic is None or best_score < self.minimum_match_score:
            known_topics = ", ".join(topic.name for topic in self.topics)

            return QAResult(
                answer=(
                    "I could not find a matching cardiology topic for this "
                    "question in the current prototype knowledge base."
                ),
                explanation=(
                    "The rule-based matcher looks for shared medical keywords "
                    f"and phrases. Available topics are: {known_topics}."
                ),
                reasoning_path=[],
                opm_objects=[],
                opm_processes=[],
                opm_states=[],
                opm_links=[],
                match_score=best_score,
            )

        return QAResult(
            answer=best_topic.answer,
            explanation=best_topic.explanation,
            reasoning_path=best_topic.reasoning_path,
            opm_objects=best_topic.opm_objects,
            opm_processes=best_topic.opm_processes,
            opm_states=best_topic.opm_states,
            opm_links=best_topic.opm_links,
            matched_topic=best_topic.name,
            match_score=best_score,
        )

    def _find_best_topic(
        self,
        question: str,
    ) -> tuple[CardiologyTopic | None, int]:
        """Find the topic with the highest keyword score."""

        if not self.topics:
            return None, 0

        scored_topics = [
            (topic, self._score_question(question, topic))
            for topic in self.topics
        ]
        return max(scored_topics, key=lambda item: item[1])

    def _score_question(self, question: str, topic: CardiologyTopic) -> int:
        """Score how well an input question matches one knowledge topic."""

        question_text = self._normalize(question)
        search_phrases = self._search_phrases(topic)
        searchable_text = self._normalize(" ".join(search_phrases))

        score = 0

        # Exact phrase matches are the strongest signal.
        for phrase in search_phrases:
            normalized_phrase = self._normalize(phrase)
            if normalized_phrase and normalized_phrase in question_text:
                score += 3

        # Shared important words are a weaker but useful signal.
        question_tokens = self._important_tokens(question_text)
        topic_tokens = self._important_tokens(searchable_text)
        score += len(question_tokens & topic_tokens)

        return score

    def _search_phrases(self, topic: CardiologyTopic) -> List[str]:
        """Collect simple searchable text from a topic."""

        return [
            topic.name,
            *topic.question_patterns,
            *topic.keywords,
            *topic.reasoning_path,
            *topic.opm_objects,
            *topic.opm_processes,
            *topic.opm_states,
            *self._link_phrases(topic.opm_links),
        ]

    def _link_phrases(self, links: List[Dict[str, str]]) -> List[str]:
        """Collect searchable text from OPM links."""

        phrases = []
        for link in links:
            phrases.extend(
                [
                    link.get("source", ""),
                    link.get("relationship", ""),
                    link.get("target", ""),
                ]
            )
        return phrases

    def _normalize(self, text: str) -> str:
        """Lowercase text and remove punctuation for simple matching."""

        return " ".join(re.findall(r"[a-z0-9]+", text.lower()))

    def _important_tokens(self, text: str) -> set[str]:
        """Remove common question words so medical terms drive matching."""

        stopwords = {
            "a",
            "an",
            "and",
            "are",
            "be",
            "can",
            "cause",
            "caused",
            "causes",
            "do",
            "does",
            "happen",
            "happens",
            "how",
            "is",
            "lead",
            "leads",
            "of",
            "or",
            "the",
            "to",
            "what",
            "why",
        }
        return {token for token in text.split() if token not in stopwords}


# Backwards-compatible name from the first prototype.
MockCardiologyReasoner = RuleBasedCardiologyReasoner
CardiologyExample = CardiologyTopic
