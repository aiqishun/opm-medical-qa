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

## Manual Sanity Check

To qualitatively validate the automatic evaluation, we performed a small-scale
manual audit on a stratified sample of 20 QA records drawn from four selection
buckets (`high_quality`, `low_grounding`, `low_consistency`, `diverse_topics`;
five records each, see `annotations/manual_sanity_check_20.csv`). For each
record, a human annotator assigned three categorical labels: `graph_relevance`
(whether the OPM graph is topically relevant to the case), `path_explainability`
(whether the reasoning path supports the final answer end-to-end), and
`main_error_type` (the dominant failure mode, if any).

| Field | Value | Count | Share |
| --- | --- | ---: | ---: |
| `graph_relevance` | yes | 10 | 50.0% |
| `graph_relevance` | partial | 9 | 45.0% |
| `graph_relevance` | no | 1 | 5.0% |
| `path_explainability` | yes | 4 | 20.0% |
| `path_explainability` | partial | 14 | 70.0% |
| `path_explainability` | no | 2 | 10.0% |
| `main_error_type` | topic_mismatch | 8 | 40.0% |
| `main_error_type` | none | 4 | 20.0% |
| `main_error_type` | over_generalization | 4 | 20.0% |
| `main_error_type` | weak_grounding | 2 | 10.0% |
| `main_error_type` | answer_graph_misalignment | 2 | 10.0% |

The manual review shows that nearly all graphs are at least partially relevant
to the underlying case (19 of 20, 95%), but only 20% of samples are judged
fully path-explainable; the modal value of `path_explainability` is `partial`
(70%). The dominant failure mode is `topic_mismatch` (40%), in which the
matched OPM topic captures a surface finding rather than the case's primary
mechanism — for example, anchoring on mitral regurgitation when the upstream
cause is carcinoid syndrome, or on hypertension when the case is actually
acute limb ischemia from atrial fibrillation. Together with
`over_generalization` (20%), these two error types account for 60% of the
sample and characterize a consistent pattern: graphs that are topically
adjacent but not specific enough to ground the final answer.

These manual findings are consistent with the automatic evaluation. The high
rate of at-least-partial graph relevance (95%) parallels the strong structural
and OPM-constraint metrics in Table 1, while the limited full path
explainability (20%) and the prevalence of `topic_mismatch` and
`over_generalization` reinforce the same weakness flagged by the automatic
audit: an overall grounding rate of 0.3980 and an answer concept coverage of
0.4103. In both views the pipeline reliably produces structurally valid,
topically adjacent OPM graphs, but the link from graph evidence to the
case-specific mechanism and final answer remains the principal gap.

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
