# Manual Audit Comparison Report

- Baseline file: `annotations/manual_audit_baseline_v2.csv`
- LLM-supervised file: `annotations/manual_audit_llm_supervised_v1.csv`
- Schema validation: passed (13 matching columns)
- Baseline rows: 100
- LLM-supervised rows: 100
- Rates use all rows in each file as the denominator.

## Key comparison metrics

| Metric | Baseline | LLM-supervised | Delta |
|---|---:|---:|---:|
| topic_correctness correct rate | 3 (3.0%) | 6 (6.0%) | +3.0 pp |
| topic_correctness correct + partial rate | 33 (33.0%) | 59 (59.0%) | +26.0 pp |
| topic_correctness incorrect rate | 67 (67.0%) | 41 (41.0%) | -26.0 pp |
| keep_for_cardiology_dataset yes rate | 56 (56.0%) | 88 (88.0%) | +32.0 pp |
| keep_for_error_analysis yes rate | 97 (97.0%) | 94 (94.0%) | -3.0 pp |
| out_of_scope error rate | 12 (12.0%) | 0 (0.0%) | -12.0 pp |
| past_history_distraction error rate | 17 (17.0%) | 9 (9.0%) | -8.0 pp |
| manifestation_vs_cause error rate | 11 (11.0%) | 0 (0.0%) | -11.0 pp |
| vague_topic error rate | 15 (15.0%) | 27 (27.0%) | +12.0 pp |

## Side-by-side distributions

### cardiology_relevance

| Value | Baseline count (%) | LLM-supervised count (%) | Delta |
|---|---:|---:|---:|
| yes | 59 (59.0%) | 88 (88.0%) | +29.0 pp |
| partial | 24 (24.0%) | 12 (12.0%) | -12.0 pp |
| no | 17 (17.0%) | 0 (0.0%) | -17.0 pp |

### topic_correctness

| Value | Baseline count (%) | LLM-supervised count (%) | Delta |
|---|---:|---:|---:|
| incorrect | 67 (67.0%) | 41 (41.0%) | -26.0 pp |
| partial | 30 (30.0%) | 53 (53.0%) | +23.0 pp |
| correct | 3 (3.0%) | 6 (6.0%) | +3.0 pp |

### matched_term_role

| Value | Baseline count (%) | LLM-supervised count (%) | Delta |
|---|---:|---:|---:|
| distractor | 26 (26.0%) | 24 (24.0%) | -2.0 pp |
| primary_disease | 9 (9.0%) | 25 (25.0%) | +16.0 pp |
| past_history | 22 (22.0%) | 11 (11.0%) | -11.0 pp |
| prerequisite | 11 (11.0%) | 17 (17.0%) | +6.0 pp |
| manifestation | 14 (14.0%) | 12 (12.0%) | -2.0 pp |
| treatment_context | 4 (4.0%) | 7 (7.0%) | +3.0 pp |
| family_history | 5 (5.0%) | 0 (0.0%) | -5.0 pp |
| physical_sign | 4 (4.0%) | 0 (0.0%) | -4.0 pp |
| complication | 2 (2.0%) | 2 (2.0%) | +0.0 pp |
| calculation_context | 1 (1.0%) | 2 (2.0%) | +1.0 pp |
| out_of_scope | 2 (2.0%) | 0 (0.0%) | -2.0 pp |

### error_type

| Value | Baseline count (%) | LLM-supervised count (%) | Delta |
|---|---:|---:|---:|
| partial_match | 28 (28.0%) | 51 (51.0%) | +23.0 pp |
| vague_topic | 15 (15.0%) | 27 (27.0%) | +12.0 pp |
| past_history_distraction | 17 (17.0%) | 9 (9.0%) | -8.0 pp |
| out_of_scope | 12 (12.0%) | 0 (0.0%) | -12.0 pp |
| manifestation_vs_cause | 11 (11.0%) | 0 (0.0%) | -11.0 pp |
| treatment_context_confusion | 4 (4.0%) | 5 (5.0%) | +1.0 pp |
| correct | 3 (3.0%) | 6 (6.0%) | +3.0 pp |
| family_history_distraction | 4 (4.0%) | 0 (0.0%) | -4.0 pp |
| anatomy_failure | 3 (3.0%) | 0 (0.0%) | -3.0 pp |
| calculation_context_confusion | 1 (1.0%) | 2 (2.0%) | +1.0 pp |
| physical_sign_failure | 2 (2.0%) | 0 (0.0%) | -2.0 pp |

### keep_for_cardiology_dataset

| Value | Baseline count (%) | LLM-supervised count (%) | Delta |
|---|---:|---:|---:|
| yes | 56 (56.0%) | 88 (88.0%) | +32.0 pp |
| no | 44 (44.0%) | 12 (12.0%) | -32.0 pp |

### keep_for_error_analysis

| Value | Baseline count (%) | LLM-supervised count (%) | Delta |
|---|---:|---:|---:|
| yes | 97 (97.0%) | 94 (94.0%) | -3.0 pp |
| no | 3 (3.0%) | 6 (6.0%) | +3.0 pp |

## Chinese interpretation

### Topic matching quality

LLM supervision 明显提升了 topic matching 的可用质量：`correct` 从 3.0% 升至 6.0%，`correct + partial` 从 33.0% 升至 59.0%，`incorrect` 从 67.0% 降至 41.0%。这说明 LLM supervision 更容易把样本保留在相关心血管主题附近，但提升主要体现为更多 partial match；严格的完全正确匹配比例仍然偏低。

### Error types

主要减少的错误包括 out_of_scope 12.0% -> 0.0%、past_history_distraction 17.0% -> 9.0%、manifestation_vs_cause 11.0% -> 0.0%。这些下降说明 LLM supervision 对排除非心血管主题、既往史干扰、以及表现与病因混淆有帮助。仍然突出的残留问题是 vague_topic 15.0% -> 27.0%，并且 partial_match 比例升高，提示模型常能找到相关方向，但仍会停留在过宽或不够精确的主题层级。
