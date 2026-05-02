# OPM Medical QA

An early research prototype for an Object-Process Methodology (OPM)-based
explainable medical question answering system for cardiology.

This repository explores how structured OPM-style knowledge representations can
support transparent answers to medical questions. The current implementation is
intentionally small: it uses a JSON cardiology knowledge base and simple
rule-based reasoning to demonstrate the expected system behavior before adding
real data, extraction models, or clinical evaluation.

> Research prototype only. This project is not a medical device and must not be
> used for diagnosis, treatment, or clinical decision-making.

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
├── scripts/                 # Command-line entry points
├── src/
│   ├── evaluation/          # Future evaluation utilities
│   ├── extraction/          # Future medical text extraction components
│   ├── graph/               # OPM graph representation
│   └── reasoning/           # QA and reasoning components
└── tests/                   # Unit and integration tests
```

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
