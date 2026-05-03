"""Human-readable formatting for QA results.

The CLI demo prints the answer, explanation, reasoning path, and OPM graph for
every question. Keeping the formatting in one place lets tests assert on the
exact output and lets new entry points (notebooks, web demos) reuse it.
"""

from __future__ import annotations

from graph.opm_graph import OPMGraph
from reasoning.reasoner import QAResult


_NO_PATH_PLACEHOLDER = "(no reasoning path found)"


def format_qa_result(result: QAResult) -> str:
    """Render ``result`` as a multi-section human-readable string."""

    sections = [
        f"answer:\n{result.answer}",
        f"explanation:\n{result.explanation}",
        f"reasoning path:\n{_format_reasoning_path(result.reasoning_path)}",
        result.graph.format_as_text(),
    ]
    return "\n\n".join(sections)


def _format_reasoning_path(path: list[str]) -> str:
    if not path:
        return _NO_PATH_PLACEHOLDER
    return OPMGraph.path_as_text(path)
