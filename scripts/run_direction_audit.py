"""Run the reproducible direction-audit pilot without a model API or extra packages."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.evaluation.state_direction import (Transition, Vocabulary, audit_transitions,
    extract_transitions, require_formal_reference, score_predictions)


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run(data_dir, output_dir, allow_draft=False):
    data_dir, output_dir = Path(data_dir), Path(output_dir)
    references = json.loads((data_dir/"references.json").read_text(encoding="utf-8"))
    if not allow_draft:
        require_formal_reference(references)
    index = {r["case_id"]: r for r in references}
    vocab = Vocabulary(json.loads((data_dir/"vocabulary.json").read_text(encoding="utf-8")))
    inputs = read_jsonl(data_dir/"candidates.public.jsonl")
    gold_rows = read_jsonl(data_dir/"labels.private.jsonl")
    gold = {g["sample_id"]: g for g in gold_rows}
    structures = {r["sample_id"]: r["transitions"]
                  for r in read_jsonl(data_dir/"structures.private.jsonl")}
    all_predictions = []
    summary = {"evaluation_status": "draft_synthetic_template_pilot" if allow_draft else "formal",
               "formal_eligible_reference_count": sum(r["approved_for_formal_evaluation"]
                                                       for r in references),
               "llm_baseline": "not_run_no_configured_model",
               "conditions": {}}
    output_dir.mkdir(parents=True, exist_ok=True)
    for condition in ("provided_structures", "automatic_rule_text", "bag_of_states_baseline"):
        predictions = []
        for item in inputs:
            ref = [Transition.from_dict(t) for t in index[item["case_id"]]["transitions"]]
            if condition == "provided_structures":
                candidate = [Transition.from_dict(t) for t in structures[item["sample_id"]]]
                result = audit_transitions(ref, candidate, vocab)
            elif condition == "automatic_rule_text":
                extracted = extract_transitions(item["text"])
                result = audit_transitions(ref, [Transition.from_dict(t)
                                           for t in extracted["transitions"]], vocab)
                result["extraction_reason"] = extracted["reason"]
                result["extracted_transitions"] = extracted["transitions"]
            else:
                # Deliberately direction-blind comparison: unordered state sets agree
                # for originals AND swaps. It is a lexical control, not FActScore.
                extracted = extract_transitions(item["text"])
                matched = bool(extracted["transitions"])
                if matched:
                    c = Transition.from_dict(extracted["transitions"][0])
                    matched = (vocab.canonical("objects", c.object) ==
                               vocab.canonical("objects", ref[0].object)
                               and {vocab.canonical("states", c.from_state, c.object),
                                    vocab.canonical("states", c.to_state, c.object)} ==
                               {vocab.canonical("states", ref[0].from_state, ref[0].object),
                                vocab.canonical("states", ref[0].to_state, ref[0].object)})
                result = {"status": "consistent" if matched else "unresolved",
                          "predicted_error": False, "findings": [], "unresolved": []}
            predictions.append({"sample_id": item["sample_id"], "case_id": item["case_id"],
                                **result})
        condition_results = {}
        for split in ("development", "test", "all"):
            selected = [p for p in predictions if split == "all"
                        or gold[p["sample_id"]]["split"] == split]
            expected = {p["sample_id"]: gold[p["sample_id"]] for p in selected}
            condition_results[split] = score_predictions(selected, expected)
        summary["conditions"][condition] = condition_results
        all_predictions.extend({"condition": condition, **p} for p in predictions)
    challenge = read_jsonl(data_dir/"source_language_challenge.jsonl")
    covered = [bool(extract_transitions(r["text"])["transitions"]) for r in challenge]
    summary["source_language_challenge"] = {
        "n": len(challenge), "explicit_transition_extractions": sum(covered),
        "extraction_coverage": sum(covered)/len(covered) if covered else None,
        "direction_metrics": None,
        "note": "Source-language snippets lack adjudicated complete tuple labels; "
                "coverage only. This is not an independently annotated benchmark."}
    (output_dir/"metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n",
                                         encoding="utf-8")
    (output_dir/"predictions.jsonl").write_text(
        "".join(json.dumps(p, ensure_ascii=False)+"\n" for p in all_predictions), encoding="utf-8")
    with (output_dir/"metrics.csv").open("w", newline="", encoding="utf-8-sig") as f:
        fields = ["condition", "split", "n", "tp", "fp", "fn", "tn_binary", "unresolved",
                  "coverage", "precision", "recall", "f1", "localization_f1"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for condition, splits in summary["conditions"].items():
            for split, values in splits.items():
                w.writerow({
                    "condition": condition, "split": split,
                    **{k: values[k] for k in ("n","tp","fp","fn","tn_binary","unresolved","coverage")},
                    **{k: values["detection"][k] for k in ("precision","recall","f1")},
                    "localization_f1": values["localization"]["f1"]})
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", default="data/direction_audit/prototype_v0_1")
    p.add_argument("--output-dir", default="experiments/results/direction_prototype_v0_1")
    p.add_argument("--allow-draft", action="store_true",
                   help="Explicitly permit non-adjudicated synthetic pilot data")
    a = p.parse_args()
    try:
        s = run(a.data_dir, a.output_dir, a.allow_draft)
    except (ValueError, KeyError) as e:
        p.exit(2, str(e)+"\n")
    print(json.dumps({"status": s["evaluation_status"],
                      "test": s["conditions"]["automatic_rule_text"]["test"],
                      "source_language_challenge": s["source_language_challenge"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
