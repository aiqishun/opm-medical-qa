# Manual Audit Labeling Guideline (v2)

## Purpose

This schema is used to manually audit the cardiology-QA pipeline at the
sample level. The previous baseline annotation (in
`experiments/manual_eval/high_confidence_sample_100.md`) only captured a
binary `cardiology_relevant` and `topic_correct` plus free-form notes.
That format conflated several distinct failure modes (past-history
distraction, manifestation-vs-cause confusion, anatomy errors, vague
topic routing, etc.) into a single bucket and made it hard to reason
about which samples should stay in the cardiology dataset and which
should be routed to error analysis.

`annotations/manual_audit_baseline_v2.csv` decomposes the same
information into discrete, controlled-vocabulary columns so that:

- The pipeline's filtering and topic-routing errors can be counted by
  type (past-history distraction vs. anatomy failure vs. ...).
- Samples can be split into two parallel datasets — one for the curated
  cardiology training set and one for downstream error analysis.
- The exact same schema can later be reused for the LLM-supervised
  version (`source_version = llm_supervised_v1`, etc.) for direct A/B
  comparison.

The original markdown annotation file is **not** modified; this CSV is
an append-only derivative.

## Columns

| Column | Type | Description |
| --- | --- | --- |
| `sample_id` | string | Stable per-question identifier (e.g. `q0025`). Pulled from the graph-path stem in the source markdown. |
| `source_version` | string | Which pipeline version produced the prediction being audited. For migrated baseline samples this is `baseline_no_llm`. Future LLM-supervised passes will use a different value. |
| `question_summary` | string | One-line summary of the clinical vignette. Must be a paraphrase, not invented content. |
| `matched_topic` | string | The topic the pipeline routed the sample to. |
| `expected_topic` | string | The annotator's view of the correct/expected topic. May be a slash-separated list when several phrasings are acceptable. |
| `cardiology_relevance` | enum | Whether the sample is genuinely cardiology-relevant. |
| `topic_correctness` | enum | Whether the matched topic is the right topic for this question. |
| `matched_term_role` | enum | The role the matched cardiac term plays inside the vignette (background, manifestation, etc.). Drives explainability. |
| `error_type` | enum | What kind of pipeline failure (if any) this sample illustrates. |
| `keep_for_cardiology_dataset` | enum | Whether this sample should be kept in the curated cardiology training/eval dataset. |
| `keep_for_error_analysis` | enum | Whether this sample should be kept as an error-analysis exemplar. |
| `reason` | string (Chinese) | Short Chinese explanation of why the labels were assigned. |
| `original_note` | string | Verbatim copy of the `Notes:` field from the original markdown annotation. |

## Allowed values

### `cardiology_relevance`
- `yes` — the question is fundamentally about a cardiology condition, sign, or treatment.
- `partial` — cardiac terms appear but only as background, treatment context, or a manifestation of a non-cardiac primary disease.
- `no` — the question is not cardiology-relevant.
- `unclear` — cannot be determined from the existing annotation.

### `topic_correctness`
- `correct` — matched topic equals (or is a strict synonym of) expected topic.
- `partial` — matched and expected topics are related only through a prerequisite, complication, trigger event, broader concept, or downstream consequence (e.g. matched `myocardial infarction` when expected is `Dressler syndrome`).
- `incorrect` — matched topic is wrong.
- `unclear` — original annotation did not commit to yes/no.

### `matched_term_role`
- `primary_disease` — matched term IS the central disease the question asks about.
- `prerequisite` — matched term is the precursor or trigger of the actual primary disease (e.g. recent MI → Dressler).
- `complication` — matched term is a downstream complication of the actual primary disease.
- `manifestation` — matched term is a clinical manifestation/finding of a non-cardiac primary disease.
- `past_history` — matched term appears in the patient's PMH but is not active.
- `family_history` — matched term appears only in family history.
- `physical_sign` — matched term came from a physical-exam sign (murmur, JVD, etc.) rather than a named disease.
- `treatment_context` — matched term identifies the disease being treated, but the question is about the drug/procedure mechanism.
- `calculation_context` — matched term is the disease setup for a math/biostats question.
- `distractor` — matched term appears in the vignette but plays no diagnostic role.
- `out_of_scope` — the true topic is outside the current cardiology KB scope.
- `unclear` — cannot be determined.

### `error_type`
- `correct` — no error; matched topic is right.
- `partial_match` — related but not exact (pairs with `topic_correctness = partial`).
- `past_history_distraction` — pipeline matched a PMH cardiac term as the topic.
- `family_history_distraction` — pipeline matched a family-history cardiac term as the topic.
- `manifestation_vs_cause` — pipeline matched a cardiac manifestation instead of the underlying non-cardiac cause.
- `physical_sign_failure` — pipeline mis-routed because a physical sign (murmur, pulsus, clubbing) was not interpreted correctly.
- `anatomy_failure` — wrong cardiac structure / laterality (e.g. mitral instead of tricuspid; left vs right heart).
- `treatment_context_confusion` — pipeline routed to the disease being treated instead of the drug/mechanism actually being asked about.
- `calculation_context_confusion` — pipeline routed to the clinical setup instead of the math being asked about.
- `out_of_scope` — true topic outside KB; current KB cannot represent it.
- `vague_topic` — matched topic is too broad / not specific enough.
- `unclear` — cannot be determined.

### `keep_for_cardiology_dataset` / `keep_for_error_analysis`
- `yes` / `no` / `unclear`.

## Migration rules from the v1 markdown annotation

1. Original `Cardiology relevant: yes` → `cardiology_relevance = yes`,
   except when the cardiac term is clearly only background (PMH, family
   history, treatment context only); then use `partial`.
2. Original `Cardiology relevant: no` → `cardiology_relevance = no`.
3. Original `Topic correct: yes` → `correct`, **except** when the matched
   and expected topics are only related through a prerequisite,
   complication, trigger event, broader concept, or downstream
   consequence — then `partial`.
4. Original `Topic correct: no` → `incorrect`.
5. If neither yes nor no was checked → `unclear`.
6. If notes mention past medical history / history / previous disease /
   background condition → prefer `matched_term_role = past_history`,
   `error_type = past_history_distraction`.
7. If notes mention family history → prefer
   `matched_term_role = family_history`,
   `error_type = family_history_distraction`.
8. If notes mention manifestation / symptom / sign / consequence →
   choose between `manifestation` + `manifestation_vs_cause` and
   `physical_sign` + `physical_sign_failure` based on whether the cue is
   a named manifestation vs. an exam-only sign.
9. If the sample is not primarily cardiology even with cardiac terms,
   set `keep_for_cardiology_dataset = no`.
10. If the sample illustrates a filtering / matching / role / explain
    error, set `keep_for_error_analysis = yes`.
11. Put the original `Notes:` content verbatim into `original_note`.
12. Write a short Chinese justification in `reason`.
13. Anything ambiguous → `unclear`. Do not invent question content.

## Worked examples

### Example A — Cardiac term appears only as past medical history
A 58-year-old man with **erectile dysfunction** is on isosorbide for
prior **angina**. Question is about ED treatment.

| field | value |
| --- | --- |
| matched_topic | `angina` |
| expected_topic | `Erectile dysfunction` |
| cardiology_relevance | `no` |
| topic_correctness | `incorrect` |
| matched_term_role | `past_history` |
| error_type | `past_history_distraction` |
| keep_for_cardiology_dataset | `no` |
| keep_for_error_analysis | `yes` |

Reasoning: angina lives in PMH only; primary question is ED. Classic
PMH distraction; useful as an error-analysis exemplar but should not
enter the cardiology training set.

### Example B — Cardiac disease is a prerequisite / trigger event
A 70-year-old man returns 10 days after MI/PCI with diffuse ST
elevations and pain that improves leaning forward — Dressler syndrome /
acute pericarditis.

| field | value |
| --- | --- |
| matched_topic | `myocardial infarction` |
| expected_topic | `Dressler syndrome/Acute pericarditis` |
| cardiology_relevance | `yes` |
| topic_correctness | `partial` |
| matched_term_role | `past_history` *(or `prerequisite`; choose
`past_history` when notes use that phrasing)* |
| error_type | `partial_match` |
| keep_for_cardiology_dataset | `yes` |
| keep_for_error_analysis | `yes` |

Reasoning: MI is the trigger event for Dressler. Original annotation
checked "Topic correct: yes", but per migration rule 3 we downgrade to
`partial` because the relationship is prerequisite, not equality.

### Example C — Physical sign / manifestation treated as the main topic
A 38-year-old woman with diarrhea, flushing, wheezing, holosystolic
murmur and elevated 5-HIAA — carcinoid syndrome with right-sided valve
involvement, but the pipeline routed to `mitral regurgitation`.

| field | value |
| --- | --- |
| matched_topic | `mitral regurgitation` |
| expected_topic | `Carcinoid syndrome` |
| cardiology_relevance | `yes` |
| topic_correctness | `incorrect` |
| matched_term_role | `manifestation` |
| error_type | `manifestation_vs_cause` |
| keep_for_cardiology_dataset | `no` |
| keep_for_error_analysis | `yes` |

Reasoning: the cardiac valve finding is a manifestation of a non-cardiac
systemic disease. The pipeline's mistake is treating a manifestation as
the underlying disease topic. Primary teaching point is non-cardiology,
so it does not belong in the cardiology training set, but it is a
canonical manifestation-vs-cause error and should be kept for error
analysis.

## Notes for future LLM-supervised passes

When auditing the LLM-supervised pipeline, write a new CSV
`annotations/manual_audit_llm_supervised_v1.csv` (or similar) using the
**same schema and the same `sample_id`s**. Set `source_version` to the
pipeline version under audit. Diffs between baseline and LLM versions
can then be computed by joining on `sample_id`.
