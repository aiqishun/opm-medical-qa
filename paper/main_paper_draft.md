# An OPM-Based Explainable Question Answering Framework for Cardiology

## 1. Abstract

We present a research prototype for explainable cardiology question answering
based on Object-Process Methodology (OPM). Given a free-text question, the
system matches the question to a cardiology topic, generates a short answer
and explanation, and exports an OPM-style graph containing objects, processes,
states, and typed links. The goal is not to validate clinical correctness, but
to study whether structured graph artifacts can make medical QA behavior more
auditable. We evaluate 543 generated graphs from a 546-row local cardiology QA
batch using a heuristic graph-quality audit. The graphs show strong structural
validity (`valid_graph_rate = 1.0000`) and strong simplified OPM constraint
satisfaction (`process_object_connectivity_rate = 0.9435`,
`state_object_attachment_rate = 0.9509`, `explanation_path_rate = 1.0000`).
However, source grounding and answer-graph consistency remain moderate
(`overall_grounding_rate = 0.3980`, `answer_concept_coverage = 0.4103`,
`graph_evidence_usage_rate = 0.3364`). A 20-sample manual sanity check
confirms this pattern: most graphs are at least partially relevant, but full
path explainability is limited. Case studies illustrate successful,
partially aligned, and failed topic-matching behavior.

## 2. Introduction

Medical question answering systems increasingly produce fluent answers, but
their reasoning steps are often difficult to inspect. This is problematic in
clinical and educational settings, where users need to understand not only an
answer but also the mechanism by which a system reached it. This paper
explores a narrow research question: can OPM-style structured artifacts make a
cardiology QA prototype more transparent and easier to audit?

We implement a compact cardiology QA pipeline in which each matched question
produces a natural-language answer, a short explanation, a reasoning path, and
an OPM-style graph. The representation is intentionally simplified: it is a
readable prototype format rather than a standard-compliant OPM serialization.
Our evaluation therefore focuses on graph quality, grounding, and
answer-graph alignment rather than clinical accuracy. We explicitly do not
claim that the generated answers are clinically correct or suitable for
diagnosis, triage, or medical decision-making.

Our contributions are threefold. First, we present an OPM-inspired
explainable QA pipeline for cardiology that outputs both text and structured
graph artifacts. Second, we define an automatic graph-quality evaluation
protocol that measures schema validity, simplified OPM constraint
satisfaction, source grounding, and answer-graph consistency. Third, we
combine automatic metrics, a manual sanity check, and targeted case studies
to characterize when OPM graphs support explanation and when they fail.

## 3. Related Work

This work is related to three areas. First, medical QA research has explored
retrieval, language models, and domain-specific supervision for answering
clinical and biomedical questions [REF]. Second, explainable AI work argues
that high-stakes systems should expose intermediate evidence, reasoning, or
model behavior in forms that can be inspected by humans [REF]. Third,
knowledge graphs and formal modeling languages provide structured
representations for entities, relations, and causal or procedural mechanisms
[REF]. OPM is relevant because it represents systems through objects,
processes, states, and links, offering a compact vocabulary for graph-based
explanation [REF]. Our contribution is a small end-to-end prototype that uses
an OPM-inspired graph as an explicit QA explanation artifact and evaluates the
artifact separately from answer correctness.

## 4. Methodology

### 4.1 Overall Framework

Let the input be a free-text cardiology question \(q\). The system returns
either a fallback status or a structured output tuple
\((t, a, e, r, G)\), where \(t\) is the matched topic, \(a\) is a short
answer, \(e\) is a natural-language explanation, \(r\) is an ordered
reasoning path, and \(G\) is an exported OPM-style graph. The output is
intended for audit and explanation, not clinical decision-making.

The pipeline has three connected stages. First, topic matching selects a
candidate cardiology topic from a hand-built knowledge base. Second, the
selected topic provides the answer, explanation, and reasoning path. Third,
the topic's OPM fields are exported as a graph artifact aligned with the same
mechanism represented by the reasoning path.

### 4.2 Cardiology QA Processing

The current prototype uses a hand-built cardiology knowledge base with 21
topics, including myocardial infarction, hypertension, heart failure, angina,
arrhythmia, atrial fibrillation, infective endocarditis, aortic stenosis,
mitral regurgitation, patent ductus arteriosus, tetralogy of Fallot,
coarctation of the aorta, and pulmonary embolism. Each topic stores question
patterns, keywords, a short answer, an explanation, a 3-5 step reasoning path,
and OPM graph fields.

For each input question, the matcher scores candidate topics using phrase
hits and shared content-token overlap. If the best score exceeds the matching
threshold, the system returns the corresponding topic; otherwise, it returns
an explicit fallback rather than fabricating an answer. In the evaluated
batch, the input file contains 546 local cardiology-relevant QA records, of
which 543 were matched and 3 fell back. These counts describe prototype
coverage only and are not medical accuracy results.

### 4.3 OPM Graph Construction

For a matched topic, the system constructs an OPM-style graph
\(G = (O, P, S, E)\). \(O\) is the set of object labels, \(P\) is the set of
process labels, \(S\) is the set of state labels, and \(E\) is the set of
typed links. Each link is a triple \((source, relationship, target)\), where
the source and target are graph labels or a terminal topic outcome. The
prototype uses a restricted relationship vocabulary, including `object
participates in process`, `process changes state`, and `state contributes to
outcome`.

Graph construction is tied to topic matching: once a topic is selected, its
stored OPM objects, processes, states, and links are exported as the graph
for that QA instance. The reasoning path provides an ordered textual view of
the same mechanism, while the OPM graph exposes the mechanism as typed
structure. The graph can be written as JSON for automatic evaluation or
rendered as a Mermaid diagram for visual inspection.

### 4.4 Explainable Answer Generation

The generated answer is accompanied by a natural-language explanation and the
ordered reasoning path associated with the matched topic. The OPM graph is
intended to act as an explanation scaffold: it makes the selected topic,
intermediate mechanisms, and final outcome inspectable in a structured form.
This design supports auditability, but it does not prove medical correctness
or guarantee that every answer token is grounded in graph evidence.

## 5. Experiments and Evaluation

### 5.1 Dataset

The main graph-quality audit uses `experiments/results/llm_relevant_batch_qa_results.jsonl`
and graph files in `outputs/graphs/llm_relevant_batch/`. The batch contains
546 QA result rows, 543 of which include graph paths. All 543 graph files were
successfully matched to result rows and evaluated. This evaluation is a
heuristic graph-quality audit, not clinical validation.

### 5.2 Evaluation Metrics

We group metrics into four categories. Schema validity measures graph
well-formedness, isolated nodes, and duplicate structures. OPM constraint
satisfaction measures whether processes connect to objects, states attach to
object-supported structures, type transitions are valid, and explanatory
paths exist. Source grounding measures normalized surface-form overlap between
graph labels and question, answer, explanation, or generated knowledge text.
Answer-graph consistency measures whether answer concepts appear in graph
labels and whether answer text uses graph evidence. Because grounding relies
on surface-form matching, synonymy and paraphrase may be underestimated.

### 5.3 Automatic OPM Graph Evaluation

The automatic evaluation shows strong graph-level structure and weaker
textual grounding. Table 1 reports the main aggregate metrics.

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

These results indicate that the exported graphs are consistently well formed
and usually satisfy the simplified OPM constraints. The lower grounding and
answer-graph consistency scores show that graph structure alone is not enough:
the system still needs stronger links between graph labels, source text, and
the final answer.

### 5.4 Manual Sanity Check

We manually audited 20 samples drawn from four buckets: `high_quality`,
`low_grounding`, `low_consistency`, and `diverse_topics`, with five samples
per bucket. Each sample was annotated for graph relevance, path
explainability, and dominant error type.

| Field | Value | Count |
| --- | --- | ---: |
| `graph_relevance` | yes | 10 |
| `graph_relevance` | partial | 9 |
| `graph_relevance` | no | 1 |
| `path_explainability` | yes | 4 |
| `path_explainability` | partial | 14 |
| `path_explainability` | no | 2 |
| `main_error_type` | topic_mismatch | 8 |
| `main_error_type` | none | 4 |
| `main_error_type` | over_generalization | 4 |
| `main_error_type` | weak_grounding | 2 |
| `main_error_type` | answer_graph_misalignment | 2 |

The manual review aligns with the automatic audit. Nineteen of 20 graphs are
at least partially relevant, but only four are fully path-explainable.
Partial explainability is the modal outcome, and `topic_mismatch` is the most
common failure mode.

### 5.5 Case Studies

The successful case `q0115` concerns aortic stenosis. The matched topic is
`aortic stenosis`, and the key explanatory chain is: valve calcification ->
aortic valve narrowing -> left ventricular outflow obstruction -> pressure
overload -> exertional dyspnea/chest pressure. The graph captures the central
mechanism and provides a useful explanation scaffold, although it does not
encode the quantitative continuity-equation calculation required for the
final numeric answer.

The partially successful case `q0140` concerns infective endocarditis. The
graph explains the visible syndrome through microbial adhesion, infected
valve surface, vegetation formation, and valve dysfunction. However, the
question also asks about the downstream association between Streptococcus
gallolyticus/bovis and colorectal neoplasia, which is not represented in the
graph. This is therefore a partially successful answer-graph alignment case.

The failure case `q0003` is a topic-mismatch example. The neonatal vignette is
consistent with congenital infection and asks about a likely congenital heart
defect, but the matched topic is `pulmonary embolism`. The generated graph is
internally coherent for thromboembolism but unrelated to the case mechanism. A
more appropriate graph would represent congenital rubella infection and its
association with congenital cardiac defects such as patent ductus arteriosus.

Together, these cases support the aggregate findings. When topic matching is
accurate, the generated OPM graph can serve as a useful explanation scaffold.
When the topic is only partially aligned, the graph may explain visible
cardiac findings but fail to support the question-specific answer. When topic
matching fails, structural graph validity alone is insufficient for case-level
explainability.

### 5.6 Error Analysis

The main error pattern is not graph syntax but alignment. The automatic audit
shows high schema validity and OPM constraint satisfaction, while source
grounding and answer-graph consistency remain moderate. The manual audit
shows the same pattern: many graphs are topically adjacent, but the reasoning
path often fails to support the exact tested mechanism or answer. Common
failure modes include topic mismatch, over-generalization, weak grounding,
and answer-graph misalignment.

The `path_support_rate` of 1.0000 should be interpreted carefully. Under the
current heuristic, it indicates that at least some answer concepts overlap
with graph-path or reasoning-path concepts; it does not prove that the final
answer fully uses the graph. The lower answer concept coverage and graph
evidence usage rates provide a more conservative view of answer-graph
alignment.

## 6. Discussion

The results suggest that OPM-style graph artifacts can make a cardiology QA
prototype more auditable. The graph format exposes the matched topic, the
mechanism steps, and the object-process-state structure that the answer is
expected to follow. This makes certain failures easier to diagnose: a graph
may be structurally valid but too general, relevant to a visible symptom but
not the requested answer, or entirely mismatched to the clinical mechanism.

At the same time, the evaluation shows that structural graph quality is only
one part of explainability. A graph can satisfy schema and OPM constraints
without being well grounded in the source text or sufficient for the answer.
Future explainable QA systems should therefore evaluate both graph form and
graph faithfulness.

The key implication is that the present bottleneck is semantic rather than
syntactic. Structural graph validity and simplified OPM constraint
satisfaction are strong, but source grounding and answer-level graph usage
remain moderate. The manual sanity check further shows that topic mismatch is
the dominant observed failure mode, indicating that better semantic routing
and answer-specific graph alignment are central next steps.

## 7. Limitations and Future Work

This work is a research prototype and has several limitations. The knowledge
base is small and hand-built, the matching strategy is simple, and the OPM
representation is a simplified custom format rather than a full OPM
serialization. The automatic evaluation is a heuristic graph-quality audit,
not clinical validation. It does not assess medical answer correctness,
clinical completeness, or suitability for deployment.

Future work should expand the cardiology knowledge base, improve topic
matching, add normalized medical concept linking, connect graph labels to
explicit source spans, and use semantic matching to handle synonyms and
paraphrases. Graph-grounded answer generation should also make the supporting
OPM path explicit, so that final answers can be checked against the graph
rather than merely accompanied by it.

## 8. Conclusion

We introduced an OPM-based explainable QA framework for cardiology and
evaluated its generated graph artifacts. The system produces structurally
valid OPM-style graphs with strong simplified constraint satisfaction, but
source grounding and answer-graph consistency remain incomplete. Manual
inspection and case studies show that accurate topic matching can yield useful
explanation scaffolds, whereas partial or failed topic alignment limits
case-level explainability. These findings motivate future work on stronger
semantic grounding and graph-faithful answer generation.
