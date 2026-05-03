"""Cardiology topic data model.

A :class:`CardiologyTopic` is one entry in the small JSON knowledge base. It
bundles the answer text together with the OPM-style fields used to explain it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from data_io import DataIOError, read_json


_REQUIRED_FIELDS = (
    "name",
    "question_patterns",
    "answer",
    "explanation",
    "reasoning_path",
    "opm_objects",
    "opm_processes",
    "opm_states",
    "opm_links",
)


@dataclass(frozen=True)
class CardiologyTopic:
    """One cardiology topic loaded from the knowledge base."""

    name: str
    question_patterns: list[str]
    answer: str
    explanation: str
    reasoning_path: list[str]
    opm_objects: list[str]
    opm_processes: list[str]
    opm_states: list[str]
    opm_links: list[dict[str, str]]
    keywords: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CardiologyTopic":
        """Build a topic from a JSON-decoded mapping.

        Raises:
            DataIOError: if a required field is missing.
        """

        missing = [field_name for field_name in _REQUIRED_FIELDS if field_name not in data]
        if missing:
            name = data.get("name", "<unnamed>")
            raise DataIOError(
                f"Topic {name!r} is missing required field(s): {', '.join(missing)}"
            )

        return cls(
            name=str(data["name"]),
            question_patterns=list(data["question_patterns"]),
            keywords=list(data.get("keywords", [])),
            answer=str(data["answer"]),
            explanation=str(data["explanation"]),
            reasoning_path=list(data["reasoning_path"]),
            opm_objects=list(data["opm_objects"]),
            opm_processes=list(data["opm_processes"]),
            opm_states=list(data["opm_states"]),
            opm_links=[dict(link) for link in data["opm_links"]],
        )


def load_topics(path: Path) -> list[CardiologyTopic]:
    """Load and validate every topic from a knowledge-base JSON file.

    The file must be a JSON object with a top-level ``topics`` list.

    Raises:
        DataIOError: if the file is missing, malformed, or has the wrong shape.
    """

    document = read_json(path)
    if not isinstance(document, dict):
        raise DataIOError(
            f"Knowledge base {path} must be a JSON object, got {type(document).__name__}."
        )

    topics = document.get("topics")
    if not isinstance(topics, list):
        raise DataIOError(
            f"Knowledge base {path} must contain a top-level 'topics' list."
        )

    return [CardiologyTopic.from_dict(topic) for topic in topics]
