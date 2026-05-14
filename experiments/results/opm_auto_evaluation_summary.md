# OPM Auto Evaluation Summary

> Heuristic graph-structure audit for prototype OPM exports. This is not a clinical validation.

## Inputs and outputs

- Results JSONL: `/Users/qishun/projects/opm-medical-qa/experiments/results/llm_relevant_batch_qa_results.jsonl`
- Graphs directory: `/Users/qishun/projects/opm-medical-qa/outputs/graphs/llm_relevant_batch`
- Per-sample metrics CSV: `/Users/qishun/projects/opm-medical-qa/experiments/results/opm_auto_evaluation_metrics.csv`

## Coverage

| Item | Count |
| --- | ---: |
| Results rows | 546 |
| Results rows with graph_path | 543 |
| Graph JSON files evaluated | 543 |
| Graph files matched to result rows | 543 |
| Graph files missing result rows | 0 |

## Schema validity

| Metric | Mean |
| --- | ---: |
| `node_validity_rate` | 1.0000 |
| `edge_validity_rate` | 1.0000 |
| `valid_graph_rate` | 1.0000 |
| `isolated_node_ratio` | 0.0078 |
| `duplicate_node_ratio` | 0.0000 |
| `duplicate_edge_ratio` | 0.0000 |

## OPM constraint satisfaction

| Metric | Mean |
| --- | ---: |
| `process_object_connectivity_rate` | 0.9435 |
| `state_object_attachment_rate` | 0.9509 |
| `valid_type_transition_rate` | 1.0000 |
| `explanation_path_rate` | 1.0000 |

## Source grounding

| Metric | Mean |
| --- | ---: |
| `object_grounding_rate` | 0.5273 |
| `process_grounding_rate` | 0.3996 |
| `state_grounding_rate` | 0.2670 |
| `overall_grounding_rate` | 0.3980 |

## Answer-graph consistency

| Metric | Mean |
| --- | ---: |
| `answer_concept_coverage` | 0.4103 |
| `graph_evidence_usage_rate` | 0.3364 |
| `path_support_rate` | 1.0000 |
