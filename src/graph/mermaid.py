"""Export OPM-style graphs as Mermaid flowchart diagrams.

Diagrams are research artifacts produced by this prototype's rule-based
reasoner and must not be used for clinical decision-making. The output is a
visualization aid — it is not a standard-compliant OPM serialization.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from graph.opm_graph import OPMGraph


class MermaidExportError(Exception):
    """Raised when a Mermaid diagram cannot be written to disk."""


_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
_WORD_RE = re.compile(r"[a-z]+")
_MIN_PREFIX_MATCH = 5


def _node_id(prefix: str, name: str) -> str:
    slug = _NON_ALPHANUMERIC.sub("_", name.lower()).strip("_")
    return f"{prefix}_{slug}" if slug else f"{prefix}_node"


def _label(name: str) -> str:
    return name.replace('"', "'")


def _content_words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if len(w) > 2}


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return n


def _step_score(name: str, step: str) -> int:
    """Score how strongly an OPM element name relates to a reasoning step."""
    name_l = name.lower()
    step_l = step.lower()

    if name_l in step_l or step_l in name_l:
        return 100

    name_words = _content_words(name)
    step_words = _content_words(step)
    direct = len(name_words & step_words)
    if direct:
        return 10 * direct

    prefix_score = 0
    for nw in name_words:
        for sw in step_words:
            if _common_prefix_len(nw, sw) >= _MIN_PREFIX_MATCH:
                prefix_score += 1
    return prefix_score


def _best_step_id(
    name: str,
    reasoning_path: Sequence[str],
    name_to_id: dict[str, str],
    fallback_id: str,
) -> str:
    best_score = 0
    best_id: str | None = None
    for step in reasoning_path:
        key = step.lower()
        if not key.strip():
            continue
        step_id = name_to_id.get(key)
        if step_id is None:
            continue
        score = _step_score(name, step)
        if score > best_score:
            best_score = score
            best_id = step_id
    return best_id or fallback_id


def graph_to_mermaid(
    graph: OPMGraph,
    *,
    reasoning_path: Sequence[str] | None = None,
) -> str:
    """Convert an OPMGraph to a Mermaid flowchart diagram string.

    Node shapes:
        - Objects                              -> rectangle      ``[ ]``
        - Processes                            -> stadium        ``([ ])``
        - States                               -> rounded rect   ``( )``
        - Implicit outcomes (link endpoints
          not in objects/processes/states)     -> hexagon        ``{{ }}``
        - Reasoning-path steps not in OPM      -> hexagon        ``{{ }}``

    When ``reasoning_path`` is provided, consecutive steps are joined with a
    thick ``==>`` "leads to" arrow to form a visible causal spine. Any OPM
    element with no incoming or outgoing edges after that pass is connected to
    the most relevant reasoning step via a dotted ``-.->`` "involves" arrow
    (best-step matching uses substring containment, then content-word overlap,
    then a 5-character common-prefix fuzzy match, with a fallback to the final
    step).

    The returned string ends in a newline and uses only standard Mermaid
    flowchart syntax that GitHub renders out of the box.
    """
    lines: list[str] = ["flowchart TD"]
    name_to_id: dict[str, str] = {}

    def define(name: str, prefix: str, open_brace: str, close_brace: str) -> str:
        key = name.lower()
        if key in name_to_id:
            return name_to_id[key]
        node_id = _node_id(prefix, name)
        name_to_id[key] = node_id
        lines.append(f'    {node_id}{open_brace}"{_label(name)}"{close_brace}')
        return node_id

    for name in graph.objects:
        define(name, "obj", "[", "]")
    for name in graph.processes:
        define(name, "proc", "([", "])")
    for name in graph.states:
        define(name, "state", "(", ")")

    for link in graph.links:
        for name in (link.source, link.target):
            if name.lower() not in name_to_id:
                define(name, "out", "{{", "}}")

    path_ids: list[str] = []
    if reasoning_path:
        for step in reasoning_path:
            if not step or not step.strip():
                continue
            key = step.lower()
            if key in name_to_id:
                path_ids.append(name_to_id[key])
            else:
                path_ids.append(define(step, "step", "{{", "}}"))

    edge_endpoints: set[str] = set()

    for link in graph.links:
        src = name_to_id[link.source.lower()]
        tgt = name_to_id[link.target.lower()]
        rel = _label(link.relationship)
        lines.append(f'    {src} -->|"{rel}"| {tgt}')
        edge_endpoints.update((src, tgt))

    for i in range(len(path_ids) - 1):
        src, tgt = path_ids[i], path_ids[i + 1]
        lines.append(f'    {src} ==>|"leads to"| {tgt}')
        edge_endpoints.update((src, tgt))

    if path_ids and reasoning_path:
        fallback_id = path_ids[-1]
        for collection in (graph.objects, graph.processes, graph.states):
            for name in collection:
                node_id = name_to_id[name.lower()]
                if node_id in edge_endpoints:
                    continue
                target_id = _best_step_id(
                    name, reasoning_path, name_to_id, fallback_id
                )
                if target_id == node_id:
                    continue
                lines.append(
                    f'    {target_id} -.->|"involves"| {node_id}'
                )
                edge_endpoints.add(node_id)

    return "\n".join(lines) + "\n"


def export_mermaid(
    graph: OPMGraph,
    path: Path,
    *,
    reasoning_path: Sequence[str] | None = None,
) -> Path:
    """Write ``graph`` as a Mermaid flowchart to ``path`` and return the path.

    Pass ``reasoning_path`` to render the QA reasoning chain as a connected
    spine and to wire any otherwise-isolated OPM elements into that spine.

    Creates parent directories as needed.

    Raises:
        MermaidExportError: if the destination cannot be written.
    """
    path = Path(path)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise MermaidExportError(
            f"Could not create directory {path.parent}: {error}"
        ) from error

    try:
        path.write_text(
            graph_to_mermaid(graph, reasoning_path=reasoning_path),
            encoding="utf-8",
        )
    except OSError as error:
        raise MermaidExportError(
            f"Could not write Mermaid diagram to {path}: {error}"
        ) from error

    return path
