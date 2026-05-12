# Evaluation Metrics

We evaluated the generated Object-Process Methodology (OPM) graphs using a
heuristic automatic graph-quality audit. The goal of this evaluation was to
measure whether the exported graph artifacts are structurally well formed,
whether they satisfy simplified OPM constraints, whether graph labels are
grounded in the associated QA text, and whether final answers are supported
by graph evidence. This evaluation is not a measure of clinical correctness
and should not be interpreted as clinical validation.

The metrics are grouped into four categories. Schema validity measures node
and edge well-formedness, whole-graph validity, isolated nodes, and duplicate
nodes or edges. OPM constraint satisfaction measures whether processes are
connected to objects, whether states are attached to object-supported
structures, whether edge type transitions are valid, and whether an
explanatory object-process-state path exists. Source grounding measures
surface-form overlap between object, process, and state labels and the
available question, generated knowledge, explanation, and answer text.
Answer-graph consistency measures whether final-answer concepts are covered
by graph labels, whether graph evidence is used in the answer or explanation,
and whether the answer is supported by graph/path concepts.

# Automatic OPM Graph Evaluation

The automatic evaluation was applied to the OPM graph JSON files in
`outputs/graphs/llm_relevant_batch/` and the corresponding QA records in
`experiments/results/llm_relevant_batch_qa_results.jsonl`. The dataset
contained 546 QA result rows, of which 543 included graph paths. All 543 graph
JSON files were successfully matched to QA result rows and evaluated.

The evaluation uses normalized surface-form matching: text is lowercased,
punctuation is removed, and whitespace is stripped before matching graph
labels against source and answer fields. A graph node is considered grounded
when its label appears in the associated question, generated knowledge,
explanation, or final answer. This makes the evaluation reproducible and
transparent, but also conservative: synonymy and paraphrase are not counted
unless they share surface forms with the graph label.

# Experimental Results

The aggregate results show strong graph-level structural quality and weaker
textual grounding. Table 1 summarizes the main metrics.

| Category | Metric | Mean |
| --- | --- | ---: |
| Schema validity | `valid_graph_rate` | 1.0000 |
| Schema validity | `isolated_node_ratio` | 0.0078 |
| OPM constraint satisfaction | `process_object_connectivity_rate` | 0.9435 |
| OPM constraint satisfaction | `state_object_attachment_rate` | 0.9509 |
| OPM constraint satisfaction | `explanation_path_rate` | 1.0000 |
| Source grounding | `overall_grounding_rate` | 0.3980 |
| Answer-graph consistency | `answer_concept_coverage` | 0.4103 |
| Answer-graph consistency | `graph_evidence_usage_rate` | 0.3364 |
| Answer-graph consistency | `path_support_rate` | 1.0000 |

The schema validity metrics indicate that the exported graphs are highly
well formed, with a valid graph rate of 1.0000 and a low isolated node ratio
of 0.0078. OPM constraint satisfaction is also strong, with process-object
connectivity at 0.9435, state-object attachment at 0.9509, and explanatory
path presence at 1.0000.

# Error Analysis

The main weakness is not graph syntax, but grounding. The overall grounding
rate is 0.3980, with state grounding lowest at 0.2670. This suggests that the
generated graphs often contain structurally valid OPM elements whose labels do
not appear explicitly in the question, explanation, generated knowledge, or
final answer. This may reflect useful abstraction, but under the current
surface-form audit it is counted as weak grounding.

Answer-graph consistency also remains incomplete. Answer concept coverage is
0.4103 and graph evidence usage is 0.3364, indicating that final answers are
only partially grounded in explicit graph evidence. The path support rate is
1.0000 under the current heuristic definition, because at least some answer
concepts overlap with graph-path or reasoning-path concepts. This should not
be interpreted as evidence that final answers fully use the graph: the lower
coverage and evidence-usage values show that answer text does not yet
systematically cite or reuse the full graph structure. Overall, the current
pipeline is stronger at structural graph generation than explicit span-level
grounding.

# Limitations and Future Work

This evaluation is a heuristic automatic graph-quality audit, not clinical
validation. It does not assess whether the medical answer is correct, whether
the graph is clinically complete, or whether the OPM representation fully
captures all formal aspects of OPM modeling. The grounding metrics rely on
surface-form matching, which may underestimate semantic grounding when the
graph uses synonyms, paraphrases, or clinically equivalent concepts.

Future work should focus on four concrete extensions: source-span linking
between graph labels and input text, normalized medical concept linking,
semantic matching for synonyms and paraphrases, and graph-grounded answer
generation with explicit references to the supporting OPM path. These
extensions would move the system from producing structurally valid
explanation artifacts toward producing answers that are explicitly and
verifiably grounded in those artifacts.
