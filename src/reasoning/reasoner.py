"""Rule-based cardiology reasoner.

Selects the closest topic for a free-text question and packages the answer,
explanation, reasoning path, and OPM-style graph into a :class:`QAResult`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from graph.opm_graph import OPMGraph
from reasoning.matcher import QuestionMatcher
from reasoning.topic import CardiologyTopic


@dataclass(frozen=True)
class QAResult:
    """Structured answer returned by the rule-based reasoner."""

    answer: str
    explanation: str
    reasoning_path: list[str]
    graph: OPMGraph
    matched_topic: str | None = None
    match_score: int = 0

    @property
    def is_match(self) -> bool:
        """True when the reasoner returned a topic-backed answer."""

        return self.matched_topic is not None


class RuleBasedCardiologyReasoner:
    """Answer cardiology questions by matching against known topics."""

    def __init__(
        self,
        topics: Iterable[CardiologyTopic],
        matcher: QuestionMatcher | None = None,
        minimum_match_score: int = 1,
    ) -> None:
        self._topics: list[CardiologyTopic] = list(topics)
        self._matcher = matcher or QuestionMatcher()
        self._minimum_match_score = minimum_match_score

    @property
    def topics(self) -> list[CardiologyTopic]:
        return list(self._topics)

    def answer(self, question: str) -> QAResult:
        """Return a :class:`QAResult` for ``question``.

        If no topic clears the minimum match score, the result explains which
        topics are available rather than fabricating an answer.
        """

        best_topic, best_score = self._find_best_topic(question)

        if best_topic is None or best_score < self._minimum_match_score:
            return self._unmatched_result(best_score)

        return QAResult(
            answer=best_topic.answer,
            explanation=best_topic.explanation,
            reasoning_path=list(best_topic.reasoning_path),
            graph=OPMGraph.from_topic_parts(
                objects=best_topic.opm_objects,
                processes=best_topic.opm_processes,
                states=best_topic.opm_states,
                links=best_topic.opm_links,
            ),
            matched_topic=best_topic.name,
            match_score=best_score,
        )

    def _find_best_topic(
        self, question: str
    ) -> tuple[CardiologyTopic | None, int]:
        """Return the highest-scoring topic, or ``(None, 0)`` if there are none."""

        if not self._topics:
            return None, 0

        scored = [(topic, self._matcher.score(question, topic)) for topic in self._topics]
        return max(scored, key=lambda item: item[1])

    def _unmatched_result(self, best_score: int) -> QAResult:
        """Build a transparent fallback result when nothing matches."""

        if self._topics:
            known = ", ".join(topic.name for topic in self._topics)
            explanation = (
                "The rule-based matcher looks for shared medical keywords and "
                f"phrases. Available topics are: {known}."
            )
        else:
            explanation = "The knowledge base is empty, so no topic can be matched."

        return QAResult(
            answer=(
                "I could not find a matching cardiology topic for this question "
                "in the current prototype knowledge base."
            ),
            explanation=explanation,
            reasoning_path=[],
            graph=OPMGraph(),
            matched_topic=None,
            match_score=best_score,
        )
