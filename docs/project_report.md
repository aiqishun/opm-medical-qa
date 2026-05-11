# OPM Medical QA — Project Report (Draft)

> **Scope and disclaimers.** This report describes a research prototype only.
> All evaluation in this document uses **synthetic, hand-authored MedQA-style
> samples** that ship with this repository. **No** experiments here use the
> real MedQA dataset, this is **not** a full MedQA evaluation, the system has
> **not** been clinically validated, and **no** medical accuracy or clinical
> performance claims are made. The OPM-style structures used here are a
> simplified representation chosen for prototype legibility and are **not** a
> standard-compliant OPM serialization. Nothing in this repository should be
> used for diagnosis, triage, or any clinical decision-making.

---

## Overview

`opm-medical-qa` is a small Python research prototype that explores whether
[Object-Process Methodology (OPM)][opm-wiki]-style structured representations
can make rule-based medical question answering more transparent. Given a
free-text cardiology question, the prototype matches it to a topic in a
hand-built knowledge base and returns:

- a short natural-language answer,
- a natural-language explanation,
- a 3–5-step reasoning path,
- an OPM-style explanation graph of objects, processes, states, and labelled
  links between them.

The same graph can be exported as JSON (for programmatic inspection) or as a
Mermaid flowchart (for visual inspection in any standard Markdown viewer).
Beyond single-question answering, the project includes a batch pipeline over a
small synthetic JSONL sample, a Markdown summary report, and a deliberately
weak keyword-only baseline used for prototype-level comparison.

[opm-wiki]: https://en.wikipedia.org/wiki/Object_Process_Methodology

## Motivation

Two observations drove the prototype's design:

1. **Black-box LLM answers are hard to audit in safety-critical domains.**
   Even when a model is "right," the path from question to answer is not
   readable, which makes triage of failures, retraining, and human oversight
   harder. A prototype that exposes intermediate structure is a useful
   research baseline against which more opaque systems can be compared.
2. **OPM provides a small, readable vocabulary for system descriptions.** By
   restricting an explanation to objects, processes, and states with labelled
   links, the structured output stays compact, comparable across topics, and
   easy to render visually. This makes the *shape* of an explanation a
   first-class artifact rather than an aside.

The prototype is intentionally narrow: a single specialty (cardiology), a
single matching strategy (rule-based), a small hand-built knowledge base, a
small synthetic sample. The aim is a clean, runnable scaffold that can be
extended later, not a benchmark result.

## Current System Architecture

The project is dependency-light — the core demo and tests use only the Python
standard library — and is organized into a thin `scripts/` CLI layer over a
`src/` library.

```
question text                         JSONL of questions
      |                                       |
      v                                       v
  scripts/run_qa.py              scripts/run_batch_qa.py
      |                                       |
      |--> src/reasoning/topic.py    (load CardiologyTopic from JSON)
      |--> src/reasoning/matcher.py  (score question vs topic phrases)
      |--> src/reasoning/reasoner.py (pick best topic; build QAResult)
      |--> src/graph/opm_graph.py    (assemble OPMGraph from topic parts)
      |--> src/graph/exporter.py     (atomic JSON write)
      |--> src/graph/mermaid.py      (Mermaid flowchart rendering)
      |--> src/formatting.py         (text rendering)
      |
      |                              + src/evaluation/summary.py
      |                                (Markdown batch summary)
      |
      \----> stdout / file outputs

scripts/prepare_medqa.py  (substring keyword filter; no model)
scripts/run_baseline_comparison.py
      |--> src/evaluation/baseline.py (KeywordBaselineMatcher + report)
      \--> JSONL + Markdown comparing baseline vs OPM
```

| Layer | Files | Responsibility |
| --- | --- | --- |
| Data I/O | `src/data_io.py` | JSON / JSONL read & write with friendly errors |
| Topic model | `src/reasoning/topic.py` | Load and validate `CardiologyTopic` records |
| Matching | `src/reasoning/matcher.py` | Score a free-text question against a topic |
| Reasoning | `src/reasoning/reasoner.py` | Select the best topic or return an explicit fallback |
| OPM graph | `src/graph/opm_graph.py` | `OPMGraph` data structure plus text formatting |
| JSON export | `src/graph/exporter.py` | Atomically write an `OPMGraph` to a JSON file |
| Mermaid export | `src/graph/mermaid.py` | Convert an `OPMGraph` to a Mermaid flowchart and write `.mmd` |
| Output formatting | `src/formatting.py` | Render answer + explanation + path + OPM sections |
| Batch summary | `src/evaluation/summary.py` | Markdown report for a batch QA run |
| Baseline | `src/evaluation/baseline.py` | Keyword-only baseline matcher + comparison report |
| CLIs | `scripts/run_qa.py`, `scripts/run_batch_qa.py`, `scripts/prepare_medqa.py`, `scripts/run_baseline_comparison.py` | Argument parsing, file paths, exit codes |

The matcher uses substring phrase hits (weight 3) plus shared content-token
overlap (weight 1), with a minimum match score of 2 below which the reasoner
returns a transparent fallback rather than fabricating an answer.

## Knowledge Base Design

The knowledge base lives at `data/processed/cardiology_knowledge.json` and
contains **21 topics**: myocardial infarction, hypertension, heart failure,
angina, arrhythmia, atherosclerosis, coronary artery disease, cardiac arrest,
valvular heart disease, cardiomyopathy, myocarditis, pericarditis, atrial
fibrillation, infective endocarditis, aortic stenosis, mitral regurgitation,
mitral valve prolapse, patent ductus arteriosus, tetralogy of Fallot,
coarctation of the aorta, and pulmonary embolism.

Every topic uses the same schema. Required fields enforced by the loader
(`src/reasoning/topic.py`) are:

- `name` — canonical topic name
- `question_patterns` — sample free-text phrasings of the question
- `answer` — short natural-language answer
- `explanation` — short natural-language explanation
- `reasoning_path` — ordered list of 3–5 simplified mechanism steps
- `opm_objects` — list of object names
- `opm_processes` — list of process names
- `opm_states` — list of state names
- `opm_links` — list of `{source, relationship, target}` records

Plus an optional `keywords` field used by both the OPM matcher and the
keyword-only baseline.

Each topic was hand-authored with three structural rules in mind:

1. The `reasoning_path` runs from an upstream cause or mechanism to the
   disease outcome in 3–5 steps.
2. Every OPM element (object, process, state) participates in at least one
   link, so the resulting graph forms a connected `object → process → state →
   outcome` chain rather than a set of disconnected fragments.
3. Each topic uses the same four relationship vocabulary across `opm_links`:
   `object participates in process`, `process changes state`,
   `process leads to outcome`, and `state contributes to outcome`. Most topics
   use the third only implicitly via the state-to-outcome closure. This
   restricted vocabulary is **not** a standard-compliant OPM serialization —
   it is a small, readable subset chosen for prototype use.

These rules are why the Mermaid renderer can, for any topic in the bundled
KB, produce a connected diagram in which every node lies on at least one
edge.

## OPM-style Explanation Graph

For each matched question the reasoner constructs an `OPMGraph` — a small
container of object, process, and state names plus typed links between them.
The same data structure powers both the text and the file outputs.

### JSON export

`scripts/run_qa.py --export-graph PATH` writes the `OPMGraph` as JSON. The
shape mirrors the knowledge-base layout, so the file can be re-loaded into an
`OPMGraph` without translation:

```json
{
  "objects": ["Coronary artery", "Heart muscle", "Oxygen"],
  "processes": ["Artery narrowing", "Oxygen delivery reduction", "Pain signal generation"],
  "states":    ["Oxygen mismatch", "Ischemic myocardium", "Chest discomfort"],
  "links": [
    {
      "source": "Oxygen delivery reduction",
      "relationship": "process changes state",
      "target": "Ischemic myocardium"
    },
    {
      "source": "Ischemic myocardium",
      "relationship": "state contributes to outcome",
      "target": "Angina"
    }
  ]
}
```

Writes go through a sibling temporary file and are renamed into place so a
failure cannot leave a half-written file behind.

### Mermaid export

`scripts/run_qa.py --export-mermaid PATH` (and `--mermaid-dir DIR` on the
batch script) writes a `.mmd` Mermaid flowchart that GitHub renders inline.
The renderer maps OPM element types to distinct shapes and uses three arrow
styles:

| Mermaid syntax | Meaning |
| --- | --- |
| `[label]` | Object |
| `([label])` | Process |
| `(label)` | State |
| `{{label}}` | Terminal outcome (link endpoint not in O/P/S) or reasoning-path step |
| `-->` | OPM link from the knowledge base |
| `==>` | Reasoning-path spine (`leads to`) — connects upstream cause to final outcome |
| `-.->` | `involves` — wires an otherwise-isolated OPM element into the spine |

When the reasoning path is supplied, the renderer walks the path as a
connected spine of `==>` arrows, reuses (rather than duplicates) any path
step whose name matches an existing OPM node, and wires isolated OPM
elements to the most relevant step using a small heuristic (substring
containment, then content-word overlap, then a 5-character common-prefix
fuzzy match, with a fallback to the final step). For every topic in the
bundled KB the resulting diagram has no isolated nodes.

## Batch Experiment Pipeline

The end-to-end pipeline is three stages, each its own script.

### 1. Preprocessing — placeholder cardiology filter

```bash
python3 scripts/prepare_medqa.py
```

Reads `data/raw/medqa_sample.jsonl` (19 hand-authored synthetic records),
keeps any record whose question, options, answer, or explanation mentions any
of a small fixed cardiology keyword list (`heart`, `cardiac`, `coronary`,
`myocardial`, `hypertension`, `arrhythmia`, `angina`, `infarction`, `valve`,
`cardiomyopathy`, `artery`, `blood pressure`), and writes the filtered subset
to `data/processed/medqa_cardiology_sample.jsonl` (16 records: 14 designed to
match a KB topic, plus 2 cardiology-adjacent fallbacks). The full MedQA
dataset is intentionally **not** included; users with their own copy can pass
`--input` to point at it.

### 2. Single-question demo

```bash
python3 scripts/run_qa.py --question "What causes myocardial infarction?"
```

Loads the KB, runs the reasoner, prints the answer + explanation + reasoning
path + OPM sections, and (with `--export-graph` / `--export-mermaid`) writes
the OPM graph to disk.

### 3. Batch QA + summary report

```bash
python3 scripts/run_batch_qa.py \
    --input data/processed/medqa_cardiology_sample.jsonl \
    --output experiments/results/batch_qa_results.jsonl \
    --graphs-dir outputs/graphs/batch/ \
    --mermaid-dir outputs/graphs/batch_mermaid/ \
    --summary experiments/results/batch_summary.md
```

Runs the OPM reasoner over every record, writes one JSONL row per question
(including `matched_topic`, `reasoning_path`, `graph_path`, `mermaid_path`,
and `status`), exports one JSON graph and one Mermaid file per *matched*
record, and renders a Markdown summary with counts, match rate, a
matched-topic frequency table, and a list of fallback questions.

## Baseline Comparison

`src/evaluation/baseline.py` defines `KeywordBaselineMatcher`, a deliberately
weak baseline that:

- considers only a topic's `name` and its `keywords` as searchable phrases,
- counts each phrase that appears as a lowercase substring of the question,
- returns the topic with the highest hit count (first declared wins on
  ties), or `None` for fallback,
- does **not** use scoring weights, content-token overlap, fuzzy matching,
  the OPM graph, or any reasoning structure,
- returns just a topic name — it produces no reasoning path, no OPM graph,
  and no natural-language answer.

`scripts/run_baseline_comparison.py` runs both the baseline and the OPM
reasoner over the same JSONL sample and reports their per-question outcomes
plus aggregate counts.

```bash
python3 scripts/run_baseline_comparison.py \
    --input data/processed/medqa_cardiology_sample.jsonl \
    --output experiments/results/baseline_comparison.jsonl \
    --summary experiments/results/baseline_comparison_summary.md
```

Each row of the per-question JSONL has this shape:

```json
{
  "id": "mi-001",
  "question": "...",
  "baseline_matched_topic": "angina",
  "baseline_status": "matched",
  "opm_matched_topic": "myocardial infarction",
  "opm_status": "matched",
  "opm_has_reasoning_path": true,
  "opm_has_graph": true
}
```

The summary report adds a counts table (total / processed / skipped /
baseline matched / baseline fallback / OPM matched / OPM fallback / OPM
reasoning paths produced / OPM graphs produced) and a per-question table
that makes per-row divergence between the two matchers easy to read.

## Current Results on Synthetic Sample

> **Reminder.** All numbers below come from a single run over a small,
> synthetic, hand-authored sample shipped with this repository. They are
> useful only for prototype-level introspection and **must not** be
> interpreted as MedQA performance, clinical accuracy, or evidence of
> superiority over any other system.

### Batch QA over the bundled cardiology sample

| Metric | Value |
| --- | ---: |
| Total input records | 16 |
| Questions processed | 16 |
| Skipped (missing question) | 0 |
| Matched | 16 |
| Fallback | 0 |
| Match rate | 100.0% |
| OPM graph files generated | 16 |

After the audit-driven topic expansion, every bundled synthetic cardiology row
now receives a prototype topic match and an OPM graph. This is useful for
exercising the pipeline end to end, but it is still only a prototype match —
not evidence of clinical correctness.

### Baseline vs OPM on the same 16 records

| Metric | Value |
| --- | ---: |
| Baseline matched | 14 |
| Baseline fallback | 2 |
| OPM QA matched | 16 |
| OPM QA fallback | 0 |
| OPM reasoning paths produced | 16 |
| OPM graphs produced | 16 |

Three substantive interpretations from the per-question table:

1. **The keyword baseline still falls back on questions where the OPM reasoner
   matches**: for example, `htn-002` and `myo-001` rely on phrasing that is not
   an exact baseline keyword hit, while the OPM reasoner can use shared
   content tokens and OPM-style topic structure.
2. **One known misclassification exists.** On `mi-001` ("crushing chest pain
   and atherosclerotic coronary artery blockage"), the keyword baseline
   matches `angina` because "chest pain" appears verbatim in the angina
   keyword list. The OPM reasoner correctly matches `myocardial infarction`
   thanks to phrase scoring across reasoning-path and OPM-link content. This
   is a representative example of how a keyword-only matcher can both miss
   correct topics and confidently match the wrong one when an unrelated
   keyword happens to appear.
3. **The OPM reasoner additionally produces structured artifacts.** On all 16
   matched records it returns a reasoning path and emits an OPM graph; the
   baseline produces neither. The comparison is therefore not just about
   match counts — the OPM reasoner produces auditable intermediate output for
   every matched question, which is the prototype's main research value.

These interpretations are properties of this specific synthetic sample. They
are not a statement about MedQA, real clinical questions, or any other
matcher's behavior in deployment.

## Manual Evaluation and Error Analysis

Two completed manual audit files were compared to assess whether the optional
LLM-supervised filtering stage improves candidate selection for cardiology QA
construction. The audit evaluates semantic relevance, topic-match quality, and
dataset usability; it is not an answer-accuracy benchmark and does not provide
clinical validation. The source artifacts are
`annotations/manual_audit_baseline_v2.csv`,
`annotations/manual_audit_llm_supervised_v1.csv`, and the generated comparison
report `annotations/manual_audit_comparison_report.md`.

The comparison setup used `baseline_no_llm` with 100 manually audited samples
and `llm_supervised` with 100 manually audited samples. Both files use the
same 13-column annotation schema, allowing direct comparison of relevance,
topic correctness, error type, and keep/discard decisions.

### Overall comparison metrics

| Metric | baseline_no_llm | llm_supervised | Change |
| --- | ---: | ---: | ---: |
| `keep_for_cardiology_dataset` yes | 56 (56.0%) | 88 (88.0%) | +32.0 pp |
| `topic_correctness` correct + partial | 33 (33.0%) | 59 (59.0%) | +26.0 pp |
| `topic_correctness` incorrect | 67 (67.0%) | 41 (41.0%) | -26.0 pp |
| `topic_correctness` correct only | 3 (3.0%) | 6 (6.0%) | +3.0 pp |

These results indicate that LLM supervision substantially improves cardiology
relevance and downstream dataset usability. The proportion of samples kept for
the cardiology dataset increased from 56.0% to 88.0%, and the usable
topic-match band (`correct + partial`) increased from 33.0% to 59.0%. At the
same time, incorrect topic matches decreased from 67.0% to 41.0%. However,
strictly correct matching remains low, rising only from 3.0% to 6.0%, so the
main gain is better semantic routing rather than reliably exact topic
identification.

### Major error reduction

| Error type | baseline_no_llm | llm_supervised | Change |
| --- | ---: | ---: | ---: |
| `out_of_scope` | 12 (12.0%) | 0 (0.0%) | -12.0 pp |
| `manifestation_vs_cause` | 11 (11.0%) | 0 (0.0%) | -11.0 pp |
| `past_history_distraction` | 17 (17.0%) | 9 (9.0%) | -8.0 pp |

The largest improvements occur in severe mismatch categories. Out-of-scope
matches were eliminated in this 100-sample audit, and
manifestation-versus-cause errors also dropped from 11.0% to 0.0%. Past
history distraction decreased from 17.0% to 9.0%, suggesting that LLM
supervision helps separate the primary tested concept from incidental
cardiology terms in background history.

### Remaining error types

| Error type | baseline_no_llm | llm_supervised | Change |
| --- | ---: | ---: | ---: |
| `partial_match` | 28 (28.0%) | 51 (51.0%) | +23.0 pp |
| `vague_topic` | 15 (15.0%) | 27 (27.0%) | +12.0 pp |
| `past_history_distraction` | 17 (17.0%) | 9 (9.0%) | -8.0 pp |
| `treatment_context_confusion` | 4 (4.0%) | 5 (5.0%) | +1.0 pp |
| `calculation_context_confusion` | 1 (1.0%) | 2 (2.0%) | +1.0 pp |

The remaining error profile shows the tradeoff introduced by LLM supervision:
the filter removes many severe mismatches, but it often lands on a broad or
adjacent topic rather than the exact primary concept. `partial_match` rose
from 28.0% to 51.0%, and `vague_topic` rose from 15.0% to 27.0%. This means
that LLM supervision improves cardiology relevance and reduces severe mismatch
errors, but most improvements are partial matches. Therefore, fine-grained
OPM/OPL-based explainable graph verification is still necessary to verify
whether the matched topic, reasoning path, OPM graph elements, and OPL-style
relationships align with the actual tested concept.

Automatically selected case studies for this audit are written to
`experiments/results/manual_audit_case_studies.md`. They include examples of
baseline incorrect cases that improved under LLM supervision, persistent
`partial_match` cases, and persistent `vague_topic` cases.

## Automatic OPM Graph Evaluation

An additional automatic evaluation was conducted to assess the structural
quality of the exported OPM graph JSON files and their alignment with the
corresponding QA outputs. The purpose of this evaluation is to quantify graph
well-formedness, simplified OPM constraint satisfaction, source grounding,
and answer-graph consistency for the prototype's generated explanation
artifacts.

The evaluation used `experiments/results/llm_relevant_batch_qa_results.jsonl`
and `outputs/graphs/llm_relevant_batch/`. In total, 543 graph JSON files were
evaluated and matched against 546 QA result rows; all 543 graph files had a
corresponding result row. The full per-sample metrics are written to
`experiments/results/opm_auto_evaluation_metrics.csv`, with aggregate results
summarized in `experiments/results/opm_auto_evaluation_summary.md`.

The automatic evaluation covers four categories:

- **Schema validity**: node and edge validity, graph validity, isolated nodes,
  and duplicate nodes or edges.
- **OPM constraint satisfaction**: object-process connectivity, state
  attachment, valid type transitions, and existence of an explanatory path.
- **Source grounding**: whether object, process, and state labels appear in
  the question, generated knowledge, explanation, or final answer.
- **Answer-graph consistency**: whether final-answer concepts are covered by
  graph labels and supported by graph/path evidence.

| Category | Metric | Mean |
| --- | --- | ---: |
| Schema validity | `valid_graph_rate` | 1.0000 |
| Schema validity | `isolated_node_ratio` | 0.0078 |
| Schema validity | `duplicate_node_ratio` | 0.0000 |
| OPM constraint satisfaction | `process_object_connectivity_rate` | 0.9435 |
| OPM constraint satisfaction | `state_object_attachment_rate` | 0.9509 |
| OPM constraint satisfaction | `valid_type_transition_rate` | 1.0000 |
| OPM constraint satisfaction | `explanation_path_rate` | 1.0000 |
| Source grounding | `object_grounding_rate` | 0.5273 |
| Source grounding | `process_grounding_rate` | 0.3996 |
| Source grounding | `state_grounding_rate` | 0.2670 |
| Source grounding | `overall_grounding_rate` | 0.3980 |
| Answer-graph consistency | `answer_concept_coverage` | 0.4103 |
| Answer-graph consistency | `graph_evidence_usage_rate` | 0.3364 |
| Answer-graph consistency | `path_support_rate` | 1.0000 |

The results indicate strong graph schema validity: node validity, edge
validity, valid graph rate, and duplicate checks are near perfect, with only a
small isolated-node ratio. The simplified OPM structural constraints are also
mostly satisfied, as process-object connectivity and state attachment both
exceed 0.94 and all evaluated graphs contain an explanatory path. In contrast,
source grounding is substantially lower, especially for state labels, and the
final answers are only partially grounded in graph evidence. This suggests
that the graph generator produces structurally coherent artifacts, but the
surface correspondence between graph labels, source text, and answer text
remains incomplete.

This automatic evaluation is heuristic and should not be interpreted as
clinical validation. Because grounding is based on normalized surface-form
matching, it may underestimate semantic grounding when the graph uses
synonyms, paraphrases, or clinically equivalent concepts. Future work should
therefore improve semantic grounding and graph-grounded answer generation, so
that final answers are explicitly supported by the OPM/OPL explanation graph
rather than only loosely associated with it.

## Limitations

- **Synthetic sample only.** Every input question, option, and explanation in
  `data/raw/medqa_sample.jsonl` was hand-authored for this prototype. The
  real MedQA dataset is not bundled and no experiments in this repository
  use it.
- **Not a full MedQA evaluation.** No standard MedQA splits are used, no
  accuracy metric is reported, and no comparison to published MedQA results
  is made.
- **Not clinically validated.** The knowledge-base content is a small,
  hand-built scaffold for prototype testing. It has not been reviewed by
  clinicians, is not aligned to any clinical guideline, and must not be used
  for diagnosis, triage, or clinical decision-making.
- **Hand-built, narrow knowledge base.** 21 cardiology topics with
  illustrative reasoning paths and OPM elements. Coverage outside these
  topics is by construction nil.
- **Simple core matching strategy.** Substring phrase scoring plus
  content-token overlap. The QA reasoner itself uses no embeddings, no LLM,
  and no learned scoring; consequently small rephrasings can fall back
  unexpectedly.
- **Optional LLM filter is audit-only.** `scripts/llm_filter_medqa.py` can add
  second-stage topic relevance metadata for locally held MedQA-derived
  candidates, but it is not part of the answer generator, is not clinically
  validated, and must not be interpreted as a medical accuracy measure.
- **Optional LLM route audit is qualitative.** `scripts/llm_route_audit.py`
  can inspect OPM `matched_topic` decisions and label likely routing-error
  patterns, but it is a triage aid for human review rather than an accuracy
  benchmark or clinical validation.
- **Simplified OPM representation.** Only four link relationships are used
  and the JSON export shape is bespoke. This is **not** a standard-compliant
  OPM serialization; it is a compact prototype shape chosen for
  readability.
- **Baseline comparison is single-sample, prototype-only.** It demonstrates
  qualitative differences on this specific synthetic sample. It is not a
  benchmark and must not be interpreted as evidence of superiority over any
  other approach on real data.

## Manual Evaluation Export

For qualitative review, `scripts/export_manual_eval_sample.py` can sample a
batch QA results JSONL and write two local artifacts:

- an annotation JSONL with nullable manual fields
  (`manual_is_cardiology_relevant`, `manual_topic_correct`,
  `manual_expected_topic`, `manual_notes`),
- a Markdown checklist with the question, matched topic, status, matched
  terms, filter confidence, answer preview, graph path, and blank annotation
  fields.

Example:

```bash
python scripts/export_manual_eval_sample.py \
    --input experiments/results/real_medqa_high_confidence_batch_qa_results.jsonl \
    --output-jsonl experiments/manual_eval/high_confidence_sample_100.jsonl \
    --output-md experiments/manual_eval/high_confidence_sample_100.md \
    --sample-size 100 \
    --seed 42
```

This is a manual/qualitative assessment aid only. It does not compute
accuracy, does not validate clinical correctness, and does not constitute a
full MedQA evaluation. The output path is git-ignored because local
real-data-derived samples may include dataset text.

## Optional LLM-Assisted Filtering

For local audit/triage of real MedQA-derived candidate rows, the repository
includes an optional second-stage classifier:

```bash
python scripts/llm_filter_medqa.py \
    --input data/processed/medqa_cardiology_real_high_confidence.jsonl \
    --output data/processed/medqa_cardiology_llm_filtered.jsonl \
    --relevant-output data/processed/medqa_cardiology_llm_relevant.jsonl \
    --summary experiments/results/llm_filter_summary.md \
    --model gpt-4o-mini \
    --limit 50 \
    --dry-run
```

`--dry-run` prints the prompt and a small record preview without making an API
call. A real run requires a local `OPENAI_API_KEY` and should usually start
with `--limit 20` or `--limit 50` before processing a larger file.

The script preserves each input row and adds:

- `llm_is_cardiology_relevant`
- `llm_primary_topic`
- `llm_confidence`
- `llm_is_incidental_history_only`
- `llm_reason`
- `llm_model`

If `--relevant-output` is supplied, the script writes an additional JSONL
containing only records where `llm_is_cardiology_relevant` is `true` and
`llm_is_incidental_history_only` is `false`. The summary includes this path
and the count of relevant-only rows written.

The prompt asks the model to distinguish the main tested concept from
cardiology terms that appear only in past medical history, medication lists,
vital signs, or incidental context. The implementation uses structured output
for the OpenAI Responses API, retries one failed or malformed classification
once, and records row-level error metadata if classification still fails.

This feature is optional and should be used only to prioritize human review of
candidate rows. It does not generate medical answers, does not claim medical
accuracy, and does not constitute a benchmark result. Real MedQA-derived LLM
outputs under `data/processed/` or `experiments/` are local artifacts and must
not be committed.

## Optional LLM Topic Routing Audit

Manual review can reveal a second class of errors after relevance filtering:
the row is cardiology-adjacent, but the OPM `matched_topic` is not the primary
tested concept. Examples include past-medical-history distraction, family
history distraction, vignette distraction, manifestation-versus-cause errors,
temporal state-transition failures, anatomy/laterality failures, and physical
sign recognition failures.

The optional route-audit script reviews batch QA results:

```bash
python scripts/llm_route_audit.py \
    --input experiments/results/llm_relevant_batch_qa_results.jsonl \
    --output experiments/results/llm_route_audit_100.jsonl \
    --summary experiments/results/llm_route_audit_summary_100.md \
    --model gpt-5.4-nano \
    --limit 100 \
    --dry-run
```

`--dry-run` prints the prompt and a small preview without calling the API. A
real run requires a local `OPENAI_API_KEY`. For each record, the script sends
only the question, current `matched_topic`, `matched_terms`, and generated
answer.

The model returns structured output:

- `primary_tested_concept`
- `is_current_topic_acceptable`
- `recommended_topic`
- `is_out_of_scope_for_current_kb`
- `error_type`
- `evidence_sentence`
- `short_reason`
- `confidence`

The supported `error_type` values are:
`past_medical_history_distraction`, `family_history_distraction`,
`vignette_distraction`, `manifestation_vs_cause`,
`generic_downstream_outcome`, `physical_sign_recognition_failure`,
`anatomy_laterality_failure`, `temporal_state_transition_failure`,
`medication_management_focus`, `correct_or_acceptable`, and `other`.

The script uses structured output for the OpenAI Responses API, retries one
failed or malformed audit once, writes row-level error metadata if audit still
fails, and summarizes acceptable/unacceptable route counts, out-of-scope
recommendations, and error-type frequencies.

This is a qualitative audit/triage layer only. It does not generate medical
answers, does not claim medical accuracy, and does not produce a benchmark
result. Real MedQA-derived route-audit outputs under `experiments/` are local
artifacts and must not be committed.

## Future Work

The following directions are sketched in the repository roadmap and are
called out here for completeness. None of them are commitments; all of them
preserve the project's prototype scope unless explicitly redesigned.

- Carefully expand the cardiology knowledge base with curated examples and
  clearer mechanism-step semantics.
- Introduce richer OPM link types and graph-level validation (for example,
  asserting that every OPM element appears in a connected component) while
  staying explicit about the non-standard-compliant subset in use.
- Connect retrieved evidence passages to individual reasoning-path steps so
  that each step can carry a justification, not just a label.
- Improve matching while keeping the prototype interpretable — for example,
  light synonym handling or normalization that does not silently change the
  reasoner's behavior.
- Add reproducible experiment scripts under `experiments/` that run multiple
  configurations and produce comparison artifacts (counts, per-question
  outcomes, OPM graphs, Mermaid renderings) into versioned subdirectories.
- Define and document evaluation metrics for answer quality, reasoning-path
  faithfulness, and explanation usefulness, and apply them on a sample
  designed for that purpose. Any such evaluation must be explicit about its
  data source and its scope.
- Document failure cases more systematically: for every fallback or
  misclassification observed on the synthetic sample, record what the
  matcher saw and which signal it missed.
- If real MedQA data is integrated in the future, do so behind an opt-in
  data path (the existing `prepare_medqa.py --input` flag is the intended
  entry point) and clearly separate any results obtained on it from the
  synthetic-sample results reported here.

---

*This document is a living draft for project documentation; it is not a
paper submission and contains no external citations.*
