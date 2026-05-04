# OPM Medical QA

**Explainable, OPM-style cardiology question answering for research prototyping.**

`opm-medical-qa` is a small Python research prototype for exploring how
Object-Process Methodology (OPM) can make medical question answering more
transparent. It currently uses a hand-built cardiology knowledge base, simple
keyword matching, and structured OPM output.

> **Non-clinical-use disclaimer:** This repository is for research and education
> only. It is not a medical device, has not been clinically validated, and must
> not be used for diagnosis, treatment, triage, or clinical decision-making. The
> bundled answer text is illustrative prototype content, not medical advice.

## Overview

The prototype returns more than a final answer. For each matched cardiology
topic, it prints:

- an answer
- a natural-language explanation
- a reasoning path
- OPM objects, processes, states, and links

The current system is intentionally dependency-light and beginner-friendly. It
uses only the Python standard library for the core demo and tests.

## Architecture

```mermaid
flowchart TD
    Q[User question] --> CLI[scripts/run_qa.py]
    CLI --> KB[data/processed/cardiology_knowledge.json]
    KB --> TOPIC[CardiologyTopic loader]
    TOPIC --> MATCH[Keyword matcher]
    MATCH --> REASON[Rule-based reasoner]
    REASON --> OPM[OPMGraph formatter]
    OPM --> OUT[Answer + explanation + path + OPM structure]

    RAW[data/raw/medqa_sample.jsonl] --> PREP[scripts/prepare_medqa.py]
    PREP --> FILTERED[data/processed/medqa_cardiology_sample.jsonl]
    FILTERED --> BATCH[scripts/run_batch_qa.py]
    BATCH --> RESULTS[experiments/results/batch_qa_results.jsonl]
    BATCH --> GRAPHS[outputs/graphs/batch/*.json]
```

## Research Goal

The long-term research goal is to investigate whether OPM-style representations
can support explainable medical QA by exposing intermediate reasoning structure.
The current repository focuses on a narrow first step: a clean, runnable
cardiology prototype with mock knowledge and explicit structured output.

## Module Responsibilities

| Area | Files | Responsibility |
| --- | --- | --- |
| CLI demos | `scripts/run_qa.py` | Parse a question, load the KB, run QA, print structured output |
| Batch experiments | `scripts/run_batch_qa.py` | Run the reasoner over a JSONL file and save per-question results plus OPM graphs |
| MedQA placeholder preprocessing | `scripts/prepare_medqa.py` | Filter a JSONL file for cardiology-related examples using simple keywords |
| Data helpers | `src/data_io.py` | Read and write JSON/JSONL files with friendly errors |
| Topic model | `src/reasoning/topic.py` | Load and validate cardiology topic records |
| Matching | `src/reasoning/matcher.py` | Score a question against topic keywords and patterns |
| Reasoning | `src/reasoning/reasoner.py` | Select the best topic or return a fallback response |
| OPM formatting | `src/graph/opm_graph.py` | Represent and format objects, processes, states, and links |
| OPM JSON export | `src/graph/exporter.py` | Atomically write an `OPMGraph` to a JSON file |
| Mermaid export | `src/graph/mermaid.py` | Convert an `OPMGraph` to a Mermaid flowchart diagram and write to `.mmd` |
| Output formatting | `src/formatting.py` | Render answer, explanation, reasoning path, and OPM sections |
| Batch summaries | `src/evaluation/summary.py` | Render a Markdown report from a batch QA run |
| Baseline comparison | `src/evaluation/baseline.py`, `scripts/run_baseline_comparison.py` | Keyword-only baseline matcher and Markdown report comparing it against the OPM reasoner |
| Tests | `tests/` | Unit and CLI behavior checks |

## Quick Start

```bash
cd opm-medical-qa
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_qa.py --question "What causes myocardial infarction?"
```

If your environment uses `python3` instead of `python`:

```bash
python3 scripts/run_qa.py --question "What causes myocardial infarction?"
```

## Demo Output

Command:

```bash
python scripts/run_qa.py --question "What causes myocardial infarction?"
```

Example output:

```text
answer:
Myocardial infarction can be caused by atherosclerosis that leads to coronary artery blockage and reduced blood flow to heart tissue.

explanation:
In this rule-based example, atherosclerosis contributes to plaque build-up in the coronary arteries. This can narrow or block the artery, reduce blood flow, and deprive heart muscle of oxygen, which may lead to myocardial infarction.

reasoning path:
Atherosclerosis -> Coronary artery blockage -> Reduced blood flow -> Myocardial infarction

OPM objects:
- Coronary artery
- Atherosclerotic plaque
- Heart muscle

OPM processes:
- Plaque build-up
- Artery blockage
- Blood flow reduction

OPM states:
- Narrowed artery
- Low oxygen supply
- Injured myocardium

OPM links:
- Coronary artery --[object participates in process]--> Plaque build-up
- Plaque build-up --[process changes state]--> Narrowed artery
- Artery blockage --[process changes state]--> Low oxygen supply
- Blood flow reduction --[process leads to disease outcome]--> Myocardial infarction
```

More demo notes are in [`demos/example_qa.md`](demos/example_qa.md).

## Graph Export

The OPM-style graph for any answered question can be saved as JSON for further
analysis (notebook inspection, comparison runs, downstream tooling). Pass
`--export-graph` to point at a destination file:

```bash
python scripts/run_qa.py \
    --question "What causes myocardial infarction?" \
    --export-graph outputs/graphs/myocardial_infarction.json
```

The CLI still prints the answer, explanation, reasoning path, and OPM sections
exactly as before, then appends a confirmation line:

```text
Graph exported to: outputs/graphs/myocardial_infarction.json
```

The exported JSON has the following shape (fields mirror the knowledge base so
the file can be re-loaded into an `OPMGraph`):

```json
{
  "objects": ["Coronary artery", "Atherosclerotic plaque", "Heart muscle"],
  "processes": ["Plaque build-up", "Artery blockage", "Blood flow reduction"],
  "states": ["Narrowed artery", "Low oxygen supply", "Injured myocardium"],
  "links": [
    {
      "source": "Coronary artery",
      "relationship": "object participates in process",
      "target": "Plaque build-up"
    }
  ]
}
```

Parent directories are created automatically and writes are atomic (the file
is staged via a sibling temporary file and renamed into place). Generated graph
files under `outputs/graphs/` are git-ignored.

> Exported graphs are **OPM-style research artifacts** produced by this
> prototype's rule-based reasoner over a small, hand-built knowledge base. They
> are not curated clinical knowledge graphs, are not validated against medical
> literature, and must not be used for clinical decision-making. The export
> format is also not a standard-compliant OPM serialization — it is a compact
> JSON shape chosen for prototype use.

## Mermaid Export

The OPM-style graph can also be exported as a [Mermaid](https://mermaid.js.org/)
flowchart for visual inspection in any Mermaid-compatible viewer (GitHub,
VS Code, Obsidian, etc.). Pass `--export-mermaid` with a `.mmd` destination:

```bash
python scripts/run_qa.py \
    --question "What causes myocardial infarction?" \
    --export-mermaid outputs/graphs/myocardial_infarction.mmd
```

The CLI appends a confirmation line and the file is valid Mermaid:

```text
Mermaid diagram exported to: outputs/graphs/myocardial_infarction.mmd
```

Example `.mmd` output for the myocardial-infarction topic:

```
flowchart TD
    obj_coronary_artery["Coronary artery"]
    obj_atherosclerotic_plaque["Atherosclerotic plaque"]
    obj_heart_muscle["Heart muscle"]
    proc_plaque_build_up(["Plaque build-up"])
    proc_artery_blockage(["Artery blockage"])
    proc_blood_flow_reduction(["Blood flow reduction"])
    state_narrowed_artery("Narrowed artery")
    state_low_oxygen_supply("Low oxygen supply")
    state_injured_myocardium("Injured myocardium")
    out_myocardial_infarction{{"Myocardial infarction"}}
    step_atherosclerosis{{"Atherosclerosis"}}
    step_coronary_artery_blockage{{"Coronary artery blockage"}}
    step_reduced_blood_flow{{"Reduced blood flow"}}
    obj_coronary_artery -->|"object participates in process"| proc_plaque_build_up
    proc_plaque_build_up -->|"process changes state"| state_narrowed_artery
    proc_artery_blockage -->|"process changes state"| state_low_oxygen_supply
    proc_blood_flow_reduction -->|"process leads to disease outcome"| out_myocardial_infarction
    step_atherosclerosis ==>|"leads to"| step_coronary_artery_blockage
    step_coronary_artery_blockage ==>|"leads to"| step_reduced_blood_flow
    step_reduced_blood_flow ==>|"leads to"| out_myocardial_infarction
    step_atherosclerosis -.->|"involves"| obj_atherosclerotic_plaque
    out_myocardial_infarction -.->|"involves"| obj_heart_muscle
    out_myocardial_infarction -.->|"involves"| state_injured_myocardium
```

Node shapes map to OPM element types:

| Shape | Mermaid syntax | OPM element |
| --- | --- | --- |
| Rectangle | `["label"]` | Object |
| Stadium | `(["label"])` | Process |
| Rounded rectangle | `("label")` | State |
| Hexagon | `{{"label"}}` | Terminal outcome (link endpoint not in O/P/S) or reasoning-path step |

Edge styles convey the kind of relationship:

| Arrow | Meaning |
| --- | --- |
| `-->` | OPM link from the knowledge base |
| `==>` | Reasoning-path spine (`leads to`) — connects upstream cause to final outcome |
| `-.->` | `involves` — wires an otherwise-isolated OPM element into the spine |

The reasoning chain is reflected as a connected `==>` spine, terminal outcomes
are explicitly defined, and isolated OPM elements are attached to the most
relevant reasoning step (best-step matching uses substring containment, then
content-word overlap, then a 5-character common-prefix fuzzy match, with a
fallback to the final step). All shapes and arrow styles render in standard
GitHub-flavored Mermaid.

Both `--export-graph` and `--export-mermaid` can be used together in a single
invocation. Parent directories are created automatically.

### Batch Mermaid export

Pass `--mermaid-dir` to `run_batch_qa.py` to write one `.mmd` file per matched
question alongside the JSON graphs:

```bash
python scripts/run_batch_qa.py \
    --input data/processed/medqa_cardiology_sample.jsonl \
    --output experiments/results/batch_qa_results.jsonl \
    --graphs-dir outputs/graphs/batch/ \
    --mermaid-dir outputs/graphs/batch/
```

Each matched result row gains a `mermaid_path` field pointing to the generated
`.mmd` file (fallback rows have `mermaid_path: null`). When `--mermaid-dir` is
omitted the field is not present in the output at all, so existing pipelines
that do not request Mermaid output are unaffected.

The script prints a confirmation line when diagrams are written:

```text
Exported Mermaid diagrams to: outputs/graphs/batch
```

## Example Outputs

The snippets below come from a real run of this prototype against the bundled
synthetic sample. They are reproduced verbatim from files in this repository so
the documentation stays accurate.

> **Reminder:** every output here was produced by the rule-based reasoner over
> a small, hand-built knowledge base and a synthetic JSONL sample. This is a
> research prototype, **not** a full MedQA evaluation, and the artifacts are
> not validated medical knowledge. Do **not** use any of this for diagnosis,
> triage, or clinical decision-making.

### Single-question CLI run

Command:

```bash
python scripts/run_qa.py --question "What causes angina?"
```

Output:

```text
answer:
Angina is commonly caused by reduced oxygen supply to heart muscle, often due to narrowed coronary arteries.

explanation:
In this rule-based example, coronary artery narrowing limits blood flow during increased demand. The resulting oxygen mismatch in the heart muscle produces ischemia, which manifests as chest discomfort known as angina.

reasoning path:
Coronary artery narrowing -> Reduced myocardial oxygen supply -> Ischemic myocardium -> Angina

OPM objects:
- Coronary artery
- Heart muscle
- Oxygen

OPM processes:
- Artery narrowing
- Oxygen delivery reduction
- Pain signal generation

OPM states:
- Oxygen mismatch
- Ischemic myocardium
- Chest discomfort

OPM links:
- Coronary artery --[object participates in process]--> Artery narrowing
- Oxygen --[object participates in process]--> Oxygen delivery reduction
- Heart muscle --[object participates in process]--> Pain signal generation
- Artery narrowing --[process changes state]--> Oxygen mismatch
- Oxygen delivery reduction --[process changes state]--> Ischemic myocardium
- Pain signal generation --[process changes state]--> Chest discomfort
- Oxygen mismatch --[state contributes to outcome]--> Angina
- Ischemic myocardium --[state contributes to outcome]--> Angina
- Chest discomfort --[state contributes to outcome]--> Angina
```

### JSON graph (excerpt)

The OPM graph for the same angina topic, exported by the batch run to
[`outputs/graphs/batch/angina-001.json`](outputs/graphs/batch/angina-001.json):

```json
{
  "objects": ["Coronary artery", "Heart muscle", "Oxygen"],
  "processes": [
    "Artery narrowing",
    "Oxygen delivery reduction",
    "Pain signal generation"
  ],
  "states": [
    "Oxygen mismatch",
    "Ischemic myocardium",
    "Chest discomfort"
  ],
  "links": [
    {
      "source": "Coronary artery",
      "relationship": "object participates in process",
      "target": "Artery narrowing"
    },
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

The full file contains all 9 links (3 object→process, 3 process→state, 3
state→outcome). The shape mirrors the knowledge base so it can be re-loaded
into an `OPMGraph`.

### Mermaid graph

The same angina run also produces
[`outputs/graphs/batch_mermaid/angina-001.mmd`](outputs/graphs/batch_mermaid/angina-001.mmd).
GitHub renders the block below as an actual diagram:

```mermaid
flowchart TD
    obj_coronary_artery["Coronary artery"]
    obj_heart_muscle["Heart muscle"]
    obj_oxygen["Oxygen"]
    proc_artery_narrowing(["Artery narrowing"])
    proc_oxygen_delivery_reduction(["Oxygen delivery reduction"])
    proc_pain_signal_generation(["Pain signal generation"])
    state_oxygen_mismatch("Oxygen mismatch")
    state_ischemic_myocardium("Ischemic myocardium")
    state_chest_discomfort("Chest discomfort")
    out_angina{{"Angina"}}
    step_coronary_artery_narrowing{{"Coronary artery narrowing"}}
    step_reduced_myocardial_oxygen_supply{{"Reduced myocardial oxygen supply"}}
    obj_coronary_artery -->|"object participates in process"| proc_artery_narrowing
    obj_oxygen -->|"object participates in process"| proc_oxygen_delivery_reduction
    obj_heart_muscle -->|"object participates in process"| proc_pain_signal_generation
    proc_artery_narrowing -->|"process changes state"| state_oxygen_mismatch
    proc_oxygen_delivery_reduction -->|"process changes state"| state_ischemic_myocardium
    proc_pain_signal_generation -->|"process changes state"| state_chest_discomfort
    state_oxygen_mismatch -->|"state contributes to outcome"| out_angina
    state_ischemic_myocardium -->|"state contributes to outcome"| out_angina
    state_chest_discomfort -->|"state contributes to outcome"| out_angina
    step_coronary_artery_narrowing ==>|"leads to"| step_reduced_myocardial_oxygen_supply
    step_reduced_myocardial_oxygen_supply ==>|"leads to"| state_ischemic_myocardium
    state_ischemic_myocardium ==>|"leads to"| out_angina
```

Notice that the reasoning-path spine (`==>` arrows) reuses the existing
`state_ischemic_myocardium` node rather than duplicating it — the path step
"Ischemic myocardium" exactly matches the OPM state of the same name.

### Batch summary (excerpt)

The full report lives at
[`experiments/results/batch_summary.md`](experiments/results/batch_summary.md);
the excerpt below shows the headline counts and topic frequencies from the
bundled synthetic sample run:

```markdown
# OPM Medical QA — Batch Summary

> Prototype run on a small synthetic sample. This is **not** a full MedQA
> evaluation and reports no medical performance metrics. Generated graphs are
> research artifacts, not clinical knowledge.

## Counts

| Metric | Value |
| --- | ---: |
| Total input records | 16 |
| Questions processed | 16 |
| Skipped (missing question) | 0 |
| Matched | 14 |
| Fallback | 2 |
| Match rate | 87.5% |
| Graph files generated | 14 |

## Matched topic frequency

| Topic | Count |
| --- | ---: |
| hypertension | 2 |
| myocardial infarction | 2 |
| angina | 1 |
| arrhythmia | 1 |
| atherosclerosis | 1 |
| cardiac arrest | 1 |
| cardiomyopathy | 1 |
| coronary artery disease | 1 |
| heart failure | 1 |
| myocarditis | 1 |
| pericarditis | 1 |
| valvular heart disease | 1 |
```

The two fallback rows correspond to the cardiology-adjacent synthetic
questions about post-valve-replacement anticoagulation and cardiac
rehabilitation — both pass the keyword preprocessing filter but intentionally
fall outside the prototype knowledge base, so the reasoner returns its
fallback response and no OPM graph is exported.

## Knowledge Base

The current hand-built cardiology knowledge base is:

```text
data/processed/cardiology_knowledge.json
```

It includes 12 prototype topics: myocardial infarction, hypertension, heart
failure, angina, arrhythmia, atherosclerosis, coronary artery disease, cardiac
arrest, valvular heart disease, cardiomyopathy, myocarditis, and pericarditis.
Each topic uses the same schema (`name`, `question_patterns`, `keywords`,
`answer`, `explanation`, `reasoning_path`, `opm_objects`, `opm_processes`,
`opm_states`, `opm_links`) and is structured so that every OPM element
participates in at least one link, the link chain runs from object → process →
state → outcome, and the reasoning path runs from an upstream cause/mechanism
to the disease outcome in 3–5 simplified, non-clinical-decision steps.

## Dataset Status

The full MedQA dataset is **not included** in this repository.

This repository only contains a small, hand-written synthetic JSONL sample for
exercising the preprocessing, batch QA, and summary report pipelines end to
end:

```text
data/raw/medqa_sample.jsonl
```

### Synthetic sample coverage

The sample contains 19 synthetic, MedQA-style records — every question, option,
and explanation was authored for this prototype and **does not** come from the
real MedQA dataset. The split is designed to exercise each stage of the
pipeline:

| Bucket | Count | Purpose |
| --- | ---: | --- |
| Supported topics (matched in batch QA) | 14 | One question per knowledge-base topic, with hypertension and myocardial infarction covered twice to exercise topic-frequency counts |
| Cardiology-adjacent fallbacks | 2 | Pass the keyword preprocessing filter but intentionally fall outside the prototype knowledge base (post-valve-replacement anticoagulation, cardiac rehabilitation) |
| Non-cardiology controls | 3 | Endocrine, dermatology, gastroenterology — used to confirm the preprocessing filter excludes them |

Running `scripts/prepare_medqa.py` on the raw file therefore yields **16**
cardiology-related records (14 supported + 2 fallback). Running
`scripts/run_batch_qa.py` over those 16 then produces 14 matched results, 2
fallbacks, and 14 OPM graph JSON files.

Run the placeholder cardiology filter with:

```bash
python scripts/prepare_medqa.py
```

It writes:

```text
data/processed/medqa_cardiology_sample.jsonl
```

Future users with access to the real MedQA dataset should place their JSONL file
under `data/raw/` and pass it explicitly:

```bash
python scripts/prepare_medqa.py --input data/raw/your_medqa_file.jsonl
```

No full MedQA evaluation is included or claimed.

## Batch Experiments

`scripts/run_batch_qa.py` runs the existing rule-based reasoner over every
question in a JSONL file and saves a structured result row per question, plus
one OPM graph JSON per matched question.

```bash
python scripts/run_batch_qa.py \
    --input data/processed/medqa_cardiology_sample.jsonl \
    --output experiments/results/batch_qa_results.jsonl \
    --graphs-dir outputs/graphs/batch/
```

All three flags default to those paths, so the bundled synthetic sample can be
processed with just:

```bash
python scripts/run_batch_qa.py
```

The script prints a short summary and exits non-zero on missing input, invalid
JSONL, or a missing knowledge base:

```text
Read 2 records from: data/processed/medqa_cardiology_sample.jsonl
Matched: 2
Fallback: 0
Skipped (missing question): 0
Wrote results to: experiments/results/batch_qa_results.jsonl
Exported graphs to: outputs/graphs/batch
```

Each line of the output JSONL has this shape:

```json
{
  "id": "case-001",
  "question": "What causes myocardial infarction?",
  "matched_topic": "myocardial infarction",
  "answer": "...",
  "explanation": "...",
  "reasoning_path": ["Atherosclerosis", "Coronary artery blockage", "Reduced blood flow", "Myocardial infarction"],
  "graph_path": "outputs/graphs/batch/case-001.json",
  "status": "matched"
}
```

Behavior notes:

- `id` is preserved when the input record has one and used as the graph
  filename stem (sanitized to `[A-Za-z0-9_-]`). When absent, the filename
  falls back to `q{index:04d}.json`.
- Records without a string `question` field are skipped and counted in the
  summary rather than aborting the run.
- Unmatched questions still produce an output row, but `matched_topic` and
  `graph_path` are `null` and `status` is `"fallback"`.
- The same non-clinical-use disclaimer applies to all generated artifacts.

### Markdown summary report

Pass `--summary` to also generate a human-readable Markdown report alongside
the JSONL results:

```bash
python scripts/run_batch_qa.py \
    --input data/processed/medqa_cardiology_sample.jsonl \
    --output experiments/results/batch_qa_results.jsonl \
    --graphs-dir outputs/graphs/batch/ \
    --summary experiments/results/batch_summary.md
```

The example summary path is:

```text
experiments/results/batch_summary.md
```

The report is rendered by `src/evaluation/summary.py` and contains:

- the input file, results JSONL, and graphs directory paths
- counts: total input records, questions processed, skipped, matched, fallback
- match rate (percentage of *processed* questions that matched, or `n/a` if
  none were processed)
- number of graph files generated
- a matched-topic frequency table (sorted by count desc, then topic name)
- a list of fallback questions, if any
- a prototype-only disclaimer noting that this is a synthetic-sample run, not
  a full MedQA evaluation, and that exported graphs are research artifacts

The CLI behavior is unchanged when `--summary` is omitted; passing it just
appends a single `Wrote summary report to: …` line to stdout.

## Baseline Comparison

`scripts/run_baseline_comparison.py` runs a deliberately weak keyword-only
baseline alongside the OPM reasoner over the same JSONL sample and reports how
they differ. The baseline (`src/evaluation/baseline.py`) only checks whether a
topic's name or any of its keywords appears as a lowercase substring of the
question — no scoring weights, no content-token overlap, no fuzzy matching. It
returns just a topic name or a fallback; it produces **no** reasoning path,
OPM graph, or natural-language answer.

Run the comparison with:

```bash
python scripts/run_baseline_comparison.py \
    --input data/processed/medqa_cardiology_sample.jsonl \
    --output experiments/results/baseline_comparison.jsonl \
    --summary experiments/results/baseline_comparison_summary.md
```

All flags default to those paths plus the bundled knowledge base, so the
synthetic sample can be processed with just:

```bash
python scripts/run_baseline_comparison.py
```

The script always writes both the per-question JSONL **and** the Markdown
summary, and prints a short stdout report:

```text
Read 16 records from: data/processed/medqa_cardiology_sample.jsonl
Skipped (missing question): 0
Baseline matched / fallback: 11 / 5
OPM QA matched / fallback:   14 / 2
OPM reasoning paths produced: 14
OPM graphs produced:          14
Wrote results to: experiments/results/baseline_comparison.jsonl
Wrote summary report to: experiments/results/baseline_comparison_summary.md
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

The Markdown summary
([`experiments/results/baseline_comparison_summary.md`](experiments/results/baseline_comparison_summary.md))
contains:

- the input and results paths,
- a counts table with: total input records, questions processed, skipped,
  baseline matched / fallback, OPM matched / fallback, OPM reasoning paths
  produced, OPM graphs produced,
- a per-question table showing both matchers' chosen topics and whether the
  OPM reasoner produced a reasoning path and a graph,
- a notes section reminding the reader that "matched" only means a topic was
  returned (not that it is clinically correct) and that the baseline can both
  miss and pick the wrong topic.

> **Important:** this is a prototype-level comparison on a small synthetic
> sample. It makes **no** medical accuracy claims, demonstrates **no**
> superiority on the real MedQA dataset, and the baseline is intentionally
> weak. The numbers are useful only for prototype-level introspection, not for
> any clinical or benchmark conclusion.

## Tests

Run the test suite from the project root:

```bash
python -m unittest discover -t . -s tests
```

Current local status:

```text
Ran 163 tests
OK
```

The tests cover JSON/JSONL helpers, topic loading, keyword matching, reasoning
fallbacks, OPM formatting, OPM JSON export (including the `--export-graph` CLI
flag), Mermaid diagram conversion and export (including the `--export-mermaid`
and `--mermaid-dir` CLI flags), the batch experiment script (happy path,
fallbacks, missing/blank questions, filename rules, error reporting, and the
`--summary` Markdown report), the keyword-only baseline matcher and the
`run_baseline_comparison.py` script (per-question row shape, count
aggregations, divergence between baseline and OPM, missing input/KB error
reporting), CLI output, and the placeholder MedQA preprocessing script.

## Roadmap

- Expand the cardiology knowledge base with more carefully curated examples
- Add richer OPM link types and graph validation
- Connect extracted evidence passages to reasoning-path steps
- Improve matching while keeping the prototype interpretable
- Add reproducible experiment scripts under `experiments/`
- Define evaluation metrics for answer quality, path faithfulness, and
  explanation usefulness
- Document limitations and failure cases more systematically

## Citation

If you use this repository in academic work, please cite it using the placeholder
below until a formal publication or archived release is available.

```bibtex
@misc{opm_medical_qa,
  title        = {OPM Medical QA: An Explainable Medical Question Answering Prototype for Cardiology},
  author       = {Your Name},
  year         = {2026},
  howpublished = {\url{https://github.com/your-username/opm-medical-qa}},
  note         = {Research prototype}
}
```
