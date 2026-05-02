"""Small OPM-style graph model used by the first QA demo.

Object-Process Methodology (OPM) represents systems with objects, processes,
and links between them. This prototype keeps the representation intentionally
simple: each node has a label and type, and directed edges describe causal or
state-changing relationships.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class OPMNode:
    """A medical object or process in the OPM graph."""

    label: str
    node_type: str


@dataclass(frozen=True)
class OPMEdge:
    """A directed relationship between two OPM nodes."""

    source: str
    target: str
    relationship: str


class OPMGraph:
    """A beginner-friendly directed graph for OPM medical knowledge."""

    def __init__(self) -> None:
        self._nodes: Dict[str, OPMNode] = {}
        self._edges: List[OPMEdge] = []

    def add_node(self, label: str, node_type: str) -> None:
        """Add an object or process node to the graph."""

        self._nodes[label] = OPMNode(label=label, node_type=node_type)

    def add_edge(self, source: str, target: str, relationship: str) -> None:
        """Add a directed relationship between two existing nodes."""

        if source not in self._nodes:
            raise ValueError(f"Unknown source node: {source}")
        if target not in self._nodes:
            raise ValueError(f"Unknown target node: {target}")

        self._edges.append(
            OPMEdge(source=source, target=target, relationship=relationship)
        )

    @property
    def nodes(self) -> Iterable[OPMNode]:
        """Return all nodes in insertion order."""

        return self._nodes.values()

    @property
    def edges(self) -> Iterable[OPMEdge]:
        """Return all directed edges in insertion order."""

        return self._edges

    def path_as_text(self, path: List[str]) -> str:
        """Format a reasoning path for display."""

        return " -> ".join(path)


def build_mock_cardiology_graph() -> OPMGraph:
    """Build the hard-coded cardiology graph used by the first demo."""

    graph = OPMGraph()

    graph.add_node("Atherosclerosis", "object")
    graph.add_node("Coronary artery blockage", "object")
    graph.add_node("Reduced blood flow", "process")
    graph.add_node("Myocardial infarction", "object")

    graph.add_edge(
        "Atherosclerosis",
        "Coronary artery blockage",
        "can lead to",
    )
    graph.add_edge(
        "Coronary artery blockage",
        "Reduced blood flow",
        "causes",
    )
    graph.add_edge(
        "Reduced blood flow",
        "Myocardial infarction",
        "can result in",
    )

    return graph
