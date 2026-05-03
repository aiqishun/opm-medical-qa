"""Question-to-topic similarity scoring.

The matcher is intentionally simple: it normalises text, looks for exact phrase
hits from the topic, and adds a smaller bonus for shared content words. The
goal is to keep the scoring transparent so the rest of the prototype can show
*why* a topic was selected.
"""

from __future__ import annotations

import re
from typing import Iterable

from reasoning.topic import CardiologyTopic


_PHRASE_HIT_WEIGHT = 3
_DEFAULT_STOPWORDS = frozenset(
    {
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
)


class QuestionMatcher:
    """Score how well a free-text question matches a :class:`CardiologyTopic`."""

    def __init__(
        self,
        stopwords: Iterable[str] = _DEFAULT_STOPWORDS,
        phrase_weight: int = _PHRASE_HIT_WEIGHT,
    ) -> None:
        self._stopwords = frozenset(stopwords)
        self._phrase_weight = phrase_weight

    def score(self, question: str, topic: CardiologyTopic) -> int:
        """Return an integer match score; higher means a closer match."""

        question_text = self._normalize(question)
        if not question_text:
            return 0

        phrases = self._search_phrases(topic)
        searchable_text = self._normalize(" ".join(phrases))

        score = 0
        for phrase in phrases:
            normalized = self._normalize(phrase)
            if normalized and normalized in question_text:
                score += self._phrase_weight

        question_tokens = self._content_tokens(question_text)
        topic_tokens = self._content_tokens(searchable_text)
        score += len(question_tokens & topic_tokens)

        return score

    @staticmethod
    def _search_phrases(topic: CardiologyTopic) -> list[str]:
        """Collect all searchable phrases from a topic."""

        phrases: list[str] = [topic.name]
        phrases.extend(topic.question_patterns)
        phrases.extend(topic.keywords)
        phrases.extend(topic.reasoning_path)
        phrases.extend(topic.opm_objects)
        phrases.extend(topic.opm_processes)
        phrases.extend(topic.opm_states)
        for link in topic.opm_links:
            phrases.append(link.get("source", ""))
            phrases.append(link.get("relationship", ""))
            phrases.append(link.get("target", ""))
        return phrases

    @staticmethod
    def _normalize(text: str) -> str:
        """Lowercase and strip punctuation so matching is whitespace-stable."""

        return " ".join(re.findall(r"[a-z0-9]+", text.lower()))

    def _content_tokens(self, normalized_text: str) -> set[str]:
        """Return tokens with common question words removed."""

        return {token for token in normalized_text.split() if token not in self._stopwords}
