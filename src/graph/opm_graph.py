"""Simple OPM-style graph formatting utilities.

Object-Process Methodology (OPM) describes systems using objects, processes,
states, and links between them. This prototype keeps the representation small
and readable so the QA output can show why an answer was selected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class OPMLink:
    """A simple relationship between two OPM elements."""

    source: str
    relationship: str
    target: str

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> "OPMLink":
        """Create a link from JSON knowledge-base data."""

        return cls(
            source=data["source"],
            relationship=data["relationship"],
            target=data["target"],
        )

    def format(self) -> str:
        """Return a readable one-line link."""

        return f"{self.source} --[{self.relationship}]--> {self.target}"


class OPMGraph:
    """A beginner-friendly OPM-style graph container."""

    def __init__(
        self,
        objects: Iterable[str] | None = None,
        processes: Iterable[str] | None = None,
        states: Iterable[str] | None = None,
        links: Iterable[OPMLink] | None = None,
    ) -> None:
        self.objects: list[str] = list(objects or [])
        self.processes: list[str] = list(processes or [])
        self.states: list[str] = list(states or [])
        self.links: list[OPMLink] = list(links or [])

    @classmethod
    def from_topic_parts(
        cls,
        objects: Iterable[str],
        processes: Iterable[str],
        states: Iterable[str],
        links: Iterable[Mapping[str, str]],
    ) -> "OPMGraph":
        """Build a graph from the JSON fields stored for one topic."""

        return cls(
            objects=objects,
            processes=processes,
            states=states,
            links=[OPMLink.from_dict(link) for link in links],
        )

    def is_empty(self) -> bool:
        """True when the graph has no elements at all."""

        return not (self.objects or self.processes or self.states or self.links)

    def to_dict(self) -> dict[str, list]:
        """Return a JSON-serializable representation of the graph.

        The shape mirrors the knowledge-base format so an exported graph can be
        round-tripped through :meth:`from_topic_parts`.
        """

        return {
            "objects": list(self.objects),
            "processes": list(self.processes),
            "states": list(self.states),
            "links": [
                {
                    "source": link.source,
                    "relationship": link.relationship,
                    "target": link.target,
                }
                for link in self.links
            ],
        }

    def format_as_text(self) -> str:
        """Format objects, processes, states, and links as readable text."""

        sections = (
            ("OPM objects", self.objects),
            ("OPM processes", self.processes),
            ("OPM states", self.states),
            ("OPM links", [link.format() for link in self.links]),
        )

        lines: list[str] = []
        for title, items in sections:
            lines.append(f"{title}:")
            if items:
                lines.extend(f"- {item}" for item in items)
            else:
                lines.append("- (none)")
            lines.append("")

        return "\n".join(lines).rstrip()

    @staticmethod
    def path_as_text(path: Iterable[str]) -> str:
        """Format a reasoning path for display."""

        return " -> ".join(path)
