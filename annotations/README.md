# Manual Audit Annotations

## LLM-Supervised Audit Pass

`manual_audit_llm_supervised_v1.csv` is a 100-record manual-audit sample for
the LLM-supervised cardiology pipeline. It uses the exact same CSV schema as
`manual_audit_baseline_v2.csv` so the baseline and LLM-supervised passes can be
compared column-by-column after human labeling.

The sample was drawn with fixed seed `42` from:

```text
experiments/results/llm_relevant_batch_qa_results.jsonl
```

That source is the downstream batch QA output produced from the LLM-filtered
relevant set (`data/processed/medqa_cardiology_llm_relevant.jsonl`). In the new
CSV, `source_version` is set to `llm_supervised`, `matched_topic` comes from
the batch output, and `question_summary` / `original_note` use the upstream
LLM-filter metadata rather than copying raw question stems. All human-judgment
fields are initialized to `unclear` with `reason = 待人工标注。`.

Do not treat this file as an evaluation result until the rows have been
manually labeled.
