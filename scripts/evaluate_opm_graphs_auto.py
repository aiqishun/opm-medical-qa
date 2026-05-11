#!/usr/bin/env python3
"""Automatically evaluate exported OPM graph JSON files.

This script is a lightweight structural audit for the prototype OPM graph
exports. It combines graph JSON files with the batch QA JSONL rows that
produced them and computes schema, OPM-constraint, grounding, and
answer-graph-consistency metrics.

The evaluation is heuristic and intended for research triage only. It does
not validate clinical correctness.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import string
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = (
    PROJECT_ROOT / "experiments" / "results" / "llm_relevant_batch_qa_results.jsonl"
)
DEFAULT_GRAPHS_DIR = PROJECT_ROOT / "outputs" / "graphs" / "llm_relevant_batch"
DEFAULT_OUTPUT_CSV = (
    PROJECT_ROOT / "experiments" / "results" / "opm_auto_evaluation_metrics.csv"
)
DEFAULT_SUMMARY = (
    PROJECT_ROOT / "experiments" / "results" / "opm_auto_evaluation_summary.md"
)

OBJECT_KEYS = ("objects", "opm_objects")
PROCESS_KEYS = ("processes", "opm_processes")
STATE_KEYS = ("states", "opm_states")
LINK_KEYS = ("links", "opm_links", "edges")

SOURCE_TEXT_FIELDS = (
    "question",
    "query",
    "prompt",
    "generated_knowledge",
    "knowledge",
    "context",
    "retrieved_knowledge",
    "explanation",
    "rationale",
    "answer",
    "final_answer",
    "generated_answer",
    "output",
    "reasoning_path",
)
ANSWER_FIELDS = ("answer", "final_answer", "generated_answer", "output")
EXPLANATION_FIELDS = ("explanation", "rationale")

METRIC_GROUPS = {
    "Schema validity": (
        "node_validity_rate",
        "edge_validity_rate",
        "valid_graph_rate",
        "isolated_node_ratio",
        "duplicate_node_ratio",
        "duplicate_edge_ratio",
    ),
    "OPM constraint satisfaction": (
        "process_object_connectivity_rate",
        "state_object_attachment_rate",
        "valid_type_transition_rate",
        "explanation_path_rate",
    ),
    "Source grounding": (
        "object_grounding_rate",
        "process_grounding_rate",
        "state_grounding_rate",
        "overall_grounding_rate",
    ),
    "Answer-graph consistency": (
        "answer_concept_coverage",
        "graph_evidence_usage_rate",
        "path_support_rate",
    ),
}

METRIC_FIELDS = tuple(
    metric for group in METRIC_GROUPS.values() for metric in group
)

CSV_FIELDS = (
    "sample_id",
    "graph_file",
    "result_index",
    "matched_topic",
    "status",
    "node_count",
    "edge_count",
    *METRIC_FIELDS,
)

STOPWORDS = {
    "about",
    "after",
    "also",
    "answer",
    "because",
    "been",
    "best",
    "caused",
    "causes",
    "choice",
    "following",
    "from",
    "have",
    "into",
    "lead",
    "leads",
    "likely",
    "more",
    "most",
    "patient",
    "question",
    "result",
    "shown",
    "that",
    "their",
    "there",
    "these",
    "this",
    "through",
    "which",
    "with",
    "woman",
    "year",
    "years",
}


def normalize_text(text: Any) -> str:
    """Lowercase text, remove punctuation, and normalize whitespace."""

    raw = value_to_text(text).lower()
    translation = str.maketrans({char: " " for char in string.punctuation})
    no_punctuation = raw.translate(translation)
    no_punctuation = re.sub(r"[^\w\s]", " ", no_punctuation, flags=re.UNICODE)
    return " ".join(no_punctuation.split())


def value_to_text(value: Any) -> str:
    """Convert a permissive JSON value into text for matching."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(value_to_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(value_to_text(item) for item in value.values())
    return str(value)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {error}") from error
            if isinstance(row, dict):
                rows.append(row)
    return rows


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Graph JSON must be an object: {path}")
    return data


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def first_present(data: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return []


def extract_label(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("label", "name", "id", "value"):
            raw = value.get(key)
            if raw:
                return str(raw)
    return value_to_text(value)


def extract_nodes(data: dict[str, Any], keys: Iterable[str]) -> list[str]:
    return [extract_label(item) for item in ensure_list(first_present(data, keys))]


def extract_links(data: dict[str, Any]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for raw_link in ensure_list(first_present(data, LINK_KEYS)):
        if not isinstance(raw_link, dict):
            continue
        source = raw_link.get("source") or raw_link.get("from") or raw_link.get("src")
        target = raw_link.get("target") or raw_link.get("to") or raw_link.get("dst")
        relationship = (
            raw_link.get("relationship")
            or raw_link.get("type")
            or raw_link.get("label")
            or raw_link.get("relation")
        )
        links.append(
            {
                "source": value_to_text(source),
                "relationship": value_to_text(relationship),
                "target": value_to_text(target),
            }
        )
    return links


def extract_graph_parts(data: dict[str, Any]) -> dict[str, Any]:
    objects = extract_nodes(data, OBJECT_KEYS)
    processes = extract_nodes(data, PROCESS_KEYS)
    states = extract_nodes(data, STATE_KEYS)

    # Compatibility for graph formats that store all nodes in one list.
    for raw_node in ensure_list(data.get("nodes")):
        if not isinstance(raw_node, dict):
            continue
        label = extract_label(raw_node)
        node_type = normalize_text(raw_node.get("type") or raw_node.get("kind"))
        if "object" in node_type:
            objects.append(label)
        elif "process" in node_type:
            processes.append(label)
        elif "state" in node_type:
            states.append(label)

    return {
        "objects": objects,
        "processes": processes,
        "states": states,
        "links": extract_links(data),
    }


def node_entries(parts: dict[str, Any]) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    for node_type in ("object", "process", "state"):
        key = f"{node_type}s" if node_type != "process" else "processes"
        for label in parts[key]:
            entries.append((label, node_type, normalize_text(label)))
    return entries


def unique_nodes_by_type(
    entries: list[tuple[str, str, str]]
) -> dict[str, dict[str, str]]:
    by_type: dict[str, dict[str, str]] = {
        "object": {},
        "process": {},
        "state": {},
    }
    for label, node_type, norm in entries:
        if norm and norm not in by_type[node_type]:
            by_type[node_type][norm] = label
    return by_type


def build_type_map(entries: list[tuple[str, str, str]]) -> dict[str, set[str]]:
    type_map: dict[str, set[str]] = defaultdict(set)
    for _label, node_type, norm in entries:
        if norm:
            type_map[norm].add(node_type)
    return type_map


def endpoint_type(norm_label: str, type_map: dict[str, set[str]], relationship: str) -> str:
    types = type_map.get(norm_label, set())
    if len(types) == 1:
        return next(iter(types))
    if len(types) > 1:
        relation = normalize_text(relationship)
        if "object" in relation and "object" in types:
            return "object"
        if "process" in relation and "process" in types:
            return "process"
        if "state" in relation and "state" in types:
            return "state"
        return sorted(types)[0]
    if "outcome" in normalize_text(relationship):
        return "outcome"
    return "unknown"


def is_edge_schema_valid(link: dict[str, str], type_map: dict[str, set[str]]) -> bool:
    source = normalize_text(link.get("source", ""))
    target = normalize_text(link.get("target", ""))
    relationship = normalize_text(link.get("relationship", ""))
    if not source or not target or not relationship:
        return False
    source_known = source in type_map
    target_known = target in type_map
    if source_known and target_known:
        return True
    return "outcome" in relationship and (source_known or target_known)


def is_valid_type_transition(link: dict[str, str], type_map: dict[str, set[str]]) -> bool:
    source = normalize_text(link.get("source", ""))
    target = normalize_text(link.get("target", ""))
    relationship = link.get("relationship", "")
    if not source or not target:
        return False
    source_type = endpoint_type(source, type_map, relationship)
    target_type = endpoint_type(target, type_map, relationship)
    return (source_type, target_type) in {
        ("object", "process"),
        ("process", "state"),
        ("process", "outcome"),
        ("state", "outcome"),
    }


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def duplicate_ratio(values: Sequence[str]) -> float:
    normalized = [value for value in values if value]
    if not normalized:
        return 0.0
    return (len(normalized) - len(set(normalized))) / len(normalized)


def adjacency_for_nodes(
    links: list[dict[str, str]],
    type_map: dict[str, set[str]],
) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = {norm: set() for norm in type_map}
    for link in links:
        source = normalize_text(link.get("source", ""))
        target = normalize_text(link.get("target", ""))
        if source in type_map and target in type_map:
            adjacency[source].add(target)
            adjacency[target].add(source)
    return adjacency


def has_neighbor_type(
    node: str,
    desired_type: str,
    adjacency: dict[str, set[str]],
    type_map: dict[str, set[str]],
) -> bool:
    return any(desired_type in type_map.get(neighbor, set()) for neighbor in adjacency[node])


def has_explanation_path(
    adjacency: dict[str, set[str]],
    type_map: dict[str, set[str]],
) -> bool:
    visited: set[str] = set()
    for start in adjacency:
        if start in visited:
            continue
        component: set[str] = set()
        queue: deque[str] = deque([start])
        visited.add(start)
        while queue:
            node = queue.popleft()
            component.add(node)
            for neighbor in adjacency[node]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        component_types = set().union(*(type_map[node] for node in component))
        if {"object", "process", "state"}.issubset(component_types):
            return True
    return False


def collect_text(row: dict[str, Any], fields: Sequence[str]) -> str:
    return " ".join(value_to_text(row.get(field)) for field in fields)


def is_label_grounded(label: str, normalized_source_text: str) -> bool:
    normalized_label = normalize_text(label)
    return bool(normalized_label and normalized_label in normalized_source_text)


def grounding_rate(labels_by_norm: dict[str, str], normalized_source_text: str) -> float:
    if not labels_by_norm:
        return 0.0
    grounded = sum(
        1 for label in labels_by_norm.values() if is_label_grounded(label, normalized_source_text)
    )
    return grounded / len(labels_by_norm)


def concept_tokens(text: Any) -> set[str]:
    normalized = normalize_text(text)
    tokens = {
        token
        for token in normalized.split()
        if len(token) >= 4 and token not in STOPWORDS and not token.isdigit()
    }
    return tokens


def labels_to_tokens(labels: Iterable[str]) -> set[str]:
    tokens: set[str] = set()
    for label in labels:
        tokens.update(concept_tokens(label))
    return tokens


def graph_path_labels(
    links: list[dict[str, str]],
    reasoning_path: Any,
) -> list[str]:
    labels: list[str] = []
    for link in links:
        labels.extend([link.get("source", ""), link.get("target", "")])
    labels.extend(ensure_list(reasoning_path))
    return [value_to_text(label) for label in labels if value_to_text(label)]


def evaluate_graph(
    graph_data: dict[str, Any],
    result_row: dict[str, Any] | None = None,
) -> dict[str, float | int | str]:
    result_row = result_row or {}
    parts = extract_graph_parts(graph_data)
    entries = node_entries(parts)
    type_map = build_type_map(entries)
    unique_by_type = unique_nodes_by_type(entries)
    unique_node_norms = set(type_map)
    links = parts["links"]

    valid_node_count = sum(1 for _label, _node_type, norm in entries if bool(norm))
    valid_edge_count = sum(1 for link in links if is_edge_schema_valid(link, type_map))
    valid_transition_count = sum(1 for link in links if is_valid_type_transition(link, type_map))
    adjacency = adjacency_for_nodes(links, type_map)

    process_nodes = unique_by_type["process"]
    object_nodes = unique_by_type["object"]
    state_nodes = unique_by_type["state"]

    process_object_connected = sum(
        1
        for process_norm in process_nodes
        if has_neighbor_type(process_norm, "object", adjacency, type_map)
    )

    state_attached = 0
    for state_norm in state_nodes:
        direct_object = has_neighbor_type(state_norm, "object", adjacency, type_map)
        process_with_object = any(
            "process" in type_map.get(neighbor, set())
            and has_neighbor_type(neighbor, "object", adjacency, type_map)
            for neighbor in adjacency.get(state_norm, set())
        )
        if direct_object or process_with_object:
            state_attached += 1

    source_text = collect_text(result_row, SOURCE_TEXT_FIELDS)
    normalized_source_text = normalize_text(source_text)
    answer_text = collect_text(result_row, ANSWER_FIELDS)
    answer_explanation_text = collect_text(result_row, ANSWER_FIELDS + EXPLANATION_FIELDS)
    normalized_answer_explanation = normalize_text(answer_explanation_text)

    all_unique_labels = {
        norm: label for labels in unique_by_type.values() for norm, label in labels.items()
    }
    grounded_all = sum(
        1 for label in all_unique_labels.values() if is_label_grounded(label, normalized_source_text)
    )
    used_in_answer_explanation = sum(
        1
        for label in all_unique_labels.values()
        if is_label_grounded(label, normalized_answer_explanation)
    )

    graph_tokens = labels_to_tokens(all_unique_labels.values())
    answer_tokens = concept_tokens(answer_text)
    answer_covered = len(answer_tokens & graph_tokens)

    path_tokens = labels_to_tokens(graph_path_labels(links, result_row.get("reasoning_path")))
    path_supported = bool(answer_tokens & path_tokens)

    normalized_nodes = [norm for _label, _node_type, norm in entries]
    normalized_edges = [
        "|".join(
            [
                normalize_text(link.get("source", "")),
                normalize_text(link.get("relationship", "")),
                normalize_text(link.get("target", "")),
            ]
        )
        for link in links
    ]

    isolated_nodes = sum(1 for norm in unique_node_norms if not adjacency.get(norm))
    valid_graph = int(
        bool(unique_node_norms)
        and bool(links)
        and valid_node_count == len(entries)
        and valid_edge_count == len(links)
    )

    return {
        "node_count": len(unique_node_norms),
        "edge_count": len(links),
        "node_validity_rate": ratio(valid_node_count, len(entries)),
        "edge_validity_rate": ratio(valid_edge_count, len(links)),
        "valid_graph_rate": float(valid_graph),
        "isolated_node_ratio": ratio(isolated_nodes, len(unique_node_norms)),
        "duplicate_node_ratio": duplicate_ratio(normalized_nodes),
        "duplicate_edge_ratio": duplicate_ratio(normalized_edges),
        "process_object_connectivity_rate": ratio(
            process_object_connected,
            len(process_nodes),
        ),
        "state_object_attachment_rate": ratio(state_attached, len(state_nodes)),
        "valid_type_transition_rate": ratio(valid_transition_count, len(links)),
        "explanation_path_rate": float(has_explanation_path(adjacency, type_map)),
        "object_grounding_rate": grounding_rate(object_nodes, normalized_source_text),
        "process_grounding_rate": grounding_rate(process_nodes, normalized_source_text),
        "state_grounding_rate": grounding_rate(state_nodes, normalized_source_text),
        "overall_grounding_rate": ratio(grounded_all, len(all_unique_labels)),
        "answer_concept_coverage": ratio(answer_covered, len(answer_tokens)),
        "graph_evidence_usage_rate": ratio(
            used_in_answer_explanation,
            len(all_unique_labels),
        ),
        "path_support_rate": float(path_supported),
    }


def result_index_by_graph_stem(rows: list[dict[str, Any]]) -> dict[str, tuple[int, dict[str, Any]]]:
    index: dict[str, tuple[int, dict[str, Any]]] = {}
    for row_index, row in enumerate(rows):
        graph_path = value_to_text(row.get("graph_path")).strip()
        if graph_path:
            index[Path(graph_path).stem] = (row_index, row)
        row_id = value_to_text(row.get("id")).strip()
        if row_id and row_id not in index:
            index[row_id] = (row_index, row)
    return index


def evaluate_graph_directory(
    results_path: Path,
    graphs_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results = read_jsonl(results_path)
    result_index = result_index_by_graph_stem(results)
    graph_files = sorted(graphs_dir.glob("*.json"))

    rows: list[dict[str, Any]] = []
    missing_result_rows = 0
    for graph_file in graph_files:
        graph_data = read_json(graph_file)
        row_index, result_row = result_index.get(graph_file.stem, (-1, {}))
        if row_index < 0:
            missing_result_rows += 1
        metrics = evaluate_graph(graph_data, result_row)
        output_row: dict[str, Any] = {
            "sample_id": graph_file.stem,
            "graph_file": str(graph_file),
            "result_index": row_index if row_index >= 0 else "",
            "matched_topic": value_to_text(result_row.get("matched_topic")),
            "status": value_to_text(result_row.get("status")),
        }
        output_row.update(metrics)
        rows.append(output_row)

    metadata = {
        "results_count": len(results),
        "results_with_graph_path": sum(1 for row in results if row.get("graph_path")),
        "graph_files_evaluated": len(graph_files),
        "graph_files_with_result_rows": len(graph_files) - missing_result_rows,
        "graph_files_missing_result_rows": missing_result_rows,
        "results_path": results_path,
        "graphs_dir": graphs_dir,
    }
    return rows, metadata


def aggregate_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    aggregates: dict[str, float] = {}
    for metric in METRIC_FIELDS:
        values = [float(row.get(metric, 0.0)) for row in rows]
        aggregates[metric] = sum(values) / len(values) if values else 0.0
    return aggregates


def format_float(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def write_metrics_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_float(row.get(field, "")) for field in CSV_FIELDS})


def build_summary_markdown(
    aggregates: dict[str, float],
    metadata: dict[str, Any],
    output_csv: Path,
) -> str:
    lines = [
        "# OPM Auto Evaluation Summary",
        "",
        "> Heuristic graph-structure audit for prototype OPM exports. This is not a clinical validation.",
        "",
        "## Inputs and outputs",
        "",
        f"- Results JSONL: `{metadata['results_path']}`",
        f"- Graphs directory: `{metadata['graphs_dir']}`",
        f"- Per-sample metrics CSV: `{output_csv}`",
        "",
        "## Coverage",
        "",
        "| Item | Count |",
        "| --- | ---: |",
        f"| Results rows | {metadata['results_count']} |",
        f"| Results rows with graph_path | {metadata['results_with_graph_path']} |",
        f"| Graph JSON files evaluated | {metadata['graph_files_evaluated']} |",
        f"| Graph files matched to result rows | {metadata['graph_files_with_result_rows']} |",
        f"| Graph files missing result rows | {metadata['graph_files_missing_result_rows']} |",
        "",
    ]

    for group, metrics in METRIC_GROUPS.items():
        lines.extend([f"## {group}", "", "| Metric | Mean |", "| --- | ---: |"])
        for metric in metrics:
            lines.append(f"| `{metric}` | {aggregates[metric]:.4f} |")
        lines.append("")

    return "\n".join(lines)


def write_summary_markdown(
    aggregates: dict[str, float],
    metadata: dict[str, Any],
    output_csv: Path,
    summary_path: Path,
) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        build_summary_markdown(aggregates, metadata, output_csv),
        encoding="utf-8",
    )


def run_evaluation(
    results_path: Path,
    graphs_dir: Path,
    output_csv: Path,
    summary_path: Path,
) -> dict[str, Any]:
    rows, metadata = evaluate_graph_directory(results_path, graphs_dir)
    aggregates = aggregate_metrics(rows)
    write_metrics_csv(rows, output_csv)
    write_summary_markdown(aggregates, metadata, output_csv, summary_path)
    return {"rows": rows, "metadata": metadata, "aggregates": aggregates}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--graphs-dir", type=Path, default=DEFAULT_GRAPHS_DIR)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results_path = resolve_path(args.results)
    graphs_dir = resolve_path(args.graphs_dir)
    output_csv = resolve_path(args.output_csv)
    summary_path = resolve_path(args.summary)

    try:
        evaluation = run_evaluation(results_path, graphs_dir, output_csv, summary_path)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    metadata = evaluation["metadata"]
    aggregates = evaluation["aggregates"]
    print(f"Graph JSON files evaluated: {metadata['graph_files_evaluated']}")
    print(f"Graph files matched to result rows: {metadata['graph_files_with_result_rows']}")
    print(f"Metrics CSV written to: {output_csv}")
    print(f"Summary written to: {summary_path}")
    print("Headline aggregate metrics:")
    for metric in (
        "valid_graph_rate",
        "explanation_path_rate",
        "overall_grounding_rate",
        "answer_concept_coverage",
        "path_support_rate",
    ):
        print(f"  {metric}: {aggregates[metric]:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
