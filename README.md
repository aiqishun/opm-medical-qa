# OPM Medical QA

An early research prototype for an Object-Process Methodology (OPM)-based
explainable medical question answering system for cardiology.

This repository explores how structured OPM-style knowledge representations can
support transparent answers to medical questions. The current implementation is
intentionally small: it uses a JSON cardiology knowledge base and simple
rule-based reasoning to demonstrate the expected system behavior before adding
real data, extraction models, or clinical evaluation.

> Research prototype only. This project is not a medical device, has not been
> clinically validated, and must not be used for diagnosis, treatment, or any
> clinical decision-making. The bundled answer text is illustrative content for
> testing the system shape, not medical advice.

## Overview

`opm-medical-qa` is designed around a simple idea: a medical QA system should not
only return an answer, but also explain how that answer was derived.

The prototype represents cardiology knowledge as OPM-inspired reasoning paths
over objects, processes, and causal relationships. A rule-based matcher searches
this structured representation and returns:

- an answer to the question
- a short explanation in natural language
- a reasoning path through the graph
- OPM objects, processes, states, and links

The first demonstration answers:

```text
What causes myocardial infarction?
```

using the knowledge base path:

```text
Atherosclerosis -> Coronary artery blockage -> Reduced blood flow -> Myocardial infarction
```

## Motivation

Medical question answering systems often rely on statistical or neural models
whose reasoning process is difficult to inspect. In high-stakes domains such as
cardiology, interpretability is essential for debugging, research analysis, and
responsible system design.

OPM offers a compact way to model systems in terms of objects, processes, and
relationships. This project investigates whether OPM-style representations can
make medical QA pipelines more explainable by exposing intermediate reasoning
steps rather than returning only final answers.

## Research Goal

The long-term goal is to build and evaluate an explainable medical QA pipeline
that combines:

- medical concept extraction from cardiology text
- OPM-style graph construction
- graph-based or hybrid reasoning
- answer generation grounded in explicit reasoning paths
- evaluation of answer correctness and explanation quality

The initial goal of this repository is narrower: establish a clean, runnable
prototype that demonstrates the expected answer-explanation-OPM interface.

## Pipeline

The intended research pipeline is:

```text
Medical sources
    -> extraction
    -> OPM graph construction
    -> reasoning
    -> answer + explanation + reasoning path + OPM structure
    -> evaluation
```

Current prototype status:

| Stage | Current implementation |
| --- | --- |
| Extraction | Placeholder package |
| Graph construction | Small JSON cardiology knowledge base |
| Reasoning | Simple rule-based similarity matcher |
| Answer generation | Template-based natural language response |
| Evaluation | Placeholder package |

## Folder Structure

```text
opm-medical-qa/
├── data/
│   ├── raw/                 # Original source data for future experiments
│   └── processed/           # Processed datasets and knowledge base files
├── demos/                   # Example runs and expected outputs
├── docs/                    # Research notes and design documentation
├── experiments/
│   └── results/             # Experiment outputs, metrics, and logs
├── scripts/                 # Command-line entry points (thin CLI shells)
│   ├── prepare_medqa.py     # Cardiology JSONL filter
│   └── run_qa.py            # Demo QA entry point
├── src/
│   ├── data_io.py           # JSON / JSONL helpers with friendly errors
│   ├── formatting.py        # Human-readable QA output formatting
│   ├── evaluation/          # Future evaluation utilities (placeholder)
│   ├── extraction/          # Future medical text extraction (placeholder)
│   ├── graph/
│   │   └── opm_graph.py     # OPM objects, processes, states, links
│   └── reasoning/
│       ├── topic.py         # CardiologyTopic data model + loader
│       ├── matcher.py       # Question-to-topic similarity scoring
│       └── reasoner.py      # RuleBasedCardiologyReasoner + QAResult
└── tests/                   # Unit and integration tests
```

### Module responsibilities

| Layer | Module | Responsibility |
| --- | --- | --- |
| Data loading | `src/data_io.py`, `src/reasoning/topic.py` | Read JSON/JSONL with clear errors; build `CardiologyTopic` instances |
| Question matching | `src/reasoning/matcher.py` | Score how well a question matches a topic |
| Reasoning | `src/reasoning/reasoner.py` | Pick the best topic and assemble a `QAResult` |
| Output | `src/formatting.py`, `src/graph/opm_graph.py` | Render answer, explanation, reasoning path, and OPM graph |
| Entry points | `scripts/run_qa.py`, `scripts/prepare_medqa.py` | Argument parsing, exit codes, error reporting |

## Quick Start

Clone the repository, create a Python environment, and run the demo.

```bash
cd opm-medical-qa
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_qa.py --question "What causes myocardial infarction?"
```

If your system uses `python3` instead of `python`, run:

```bash
python3 scripts/run_qa.py --question "What causes myocardial infarction?"
```

## MedQA Preprocessing

The full MedQA dataset is not included in this repository. The current project
only contains a tiny synthetic JSONL sample for testing the preprocessing
pipeline:

```text
data/raw/medqa_sample.jsonl
```

To filter the sample for cardiology-related examples, run:

```bash
python scripts/prepare_medqa.py
```

The filtered output is written to:

```text
data/processed/medqa_cardiology_sample.jsonl
```

Future users who have access to the real MedQA dataset should place the JSONL
file under `data/raw/` and pass it to the script:

```bash
python scripts/prepare_medqa.py --input data/raw/your_medqa_file.jsonl
```

The keyword vocabulary can be overridden for ad-hoc experiments:

```bash
python scripts/prepare_medqa.py --keyword angina --keyword arrhythmia
```

This repository has only ever been tested against the bundled synthetic sample.
No claim is made about evaluation on the full MedQA dataset.

## Demo Example

Command:

```bash
python scripts/run_qa.py --question "What causes myocardial infarction?"
```

Expected output:

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

Additional demo notes are available in
[`demos/example_qa.md`](demos/example_qa.md).

The current knowledge base includes topics for myocardial infarction,
hypertension, heart failure, angina, arrhythmia, atherosclerosis, coronary
artery disease, cardiac arrest, valvular heart disease, and cardiomyopathy.

## Tests

The test suite uses only the standard library (`unittest`). Run it from the
project root:

```bash
python -m unittest discover -t . -s tests
```

The suite covers:

- `data_io` — JSON / JSONL reading and writing, including missing-file and
  invalid-JSON error paths
- `reasoning.topic` — knowledge base loading and validation
- `reasoning.matcher` — question scoring, normalisation, and stopwords
- `reasoning.reasoner` — topic selection, fallback, and minimum match score
- `graph.opm_graph` — OPM section formatting and link rendering
- `scripts/run_qa.py` — CLI behavior, error handling, and end-to-end output
- `scripts/prepare_medqa.py` — filtering, error handling, and keyword overrides

## Future Work

Planned research and engineering directions include:

- add cardiology text ingestion and preprocessing
- extract medical entities, processes, and causal relations
- construct larger OPM-style graphs from real sources
- add graph search and path-ranking methods
- integrate evidence passages for each reasoning step
- compare rule-based, symbolic, and neural reasoning strategies
- evaluate answer accuracy, path faithfulness, and explanation usefulness
- add tests and reproducible experiment scripts
- document limitations, failure cases, and clinical safety boundaries

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
