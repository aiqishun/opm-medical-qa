"""Check referential integrity, mutation labels, topic splits, and snapshot hashes."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.evaluation.state_direction import Transition, Vocabulary, audit_transitions, extract_transitions


def validate(directory):
    root = Path(directory)
    load = lambda name: json.loads((root/name).read_text(encoding="utf-8"))
    lines = lambda name: [json.loads(x) for x in (root/name).read_text(encoding="utf-8").splitlines() if x]
    refs = load("references.json")
    sources = load("sources.json")
    inputs, labels, structures = [lines(n) for n in
        ("candidates.public.jsonl","labels.private.jsonl","structures.private.jsonl")]
    manifest = load("snapshot_manifest.json")
    rmap, smap = {r["case_id"]:r for r in refs}, {s["source_id"]:s for s in sources}
    assert len(rmap)==len(refs), "duplicate case"
    assert len(smap)==len(sources), "duplicate source"
    ids=[{r["sample_id"] for r in rows} for rows in (inputs,labels,structures)]
    assert ids[0] == ids[1] == ids[2] and all(
        len(idset)==len(rows)==len(inputs)
        for idset,rows in zip(ids,(inputs,labels,structures))), "sample ID mismatch"
    assert all(set(r)=={"sample_id","case_id","text"} for r in inputs), "public label leakage"
    groups={}
    for r in refs:
        groups.setdefault(r["mechanism_group"],set()).add(r["split"])
        assert all(s in smap for s in r["source_ids"]), "missing source"
        assert len(r["transitions"])==1, "pilot requires one nominated main transition"
        assert not r["approved_for_formal_evaluation"], "draft promoted without adjudication"
        t=r["transitions"][0]
        assert all(t[k] for k in ("id","object","process","from_state","to_state","state_owner","context","modality"))
    assert all(len(splits)==1 for splits in groups.values()), "mechanism group split leakage"
    emap=list(csv.DictReader((root/"field_evidence.csv").open(encoding="utf-8-sig")))
    expected={(r["case_id"],"T1",f) for r in refs for f in
              ("object","process","from_state","to_state","state_owner")}
    actual={(r["case_id"],r["transition_id"],r["field"]) for r in emap}
    assert actual==expected and len(emap)==len(actual), "evidence rows missing/duplicated"
    for row in emap:
        assert row["source_id"] in smap and row["case_id"] in rmap
    lmap={r["sample_id"]:r for r in labels}
    tmap={r["sample_id"]:r["transitions"][0] for r in structures}
    vocab=Vocabulary(load("vocabulary.json"))
    per_case={}
    for item in inputs:
        label=lmap[item["sample_id"]]
        assert label["case_id"]==item["case_id"]
        r=rmap[item["case_id"]]
        assert label["split"]==r["split"]
        per_case.setdefault(item["case_id"],[]).append(label["variant"])
        t, ref=tmap[item["sample_id"]],r["transitions"][0]
        unchanged=("object","process","state_owner","context","modality")
        assert all(t[k]==ref[k] for k in unchanged), "unintended controlled mutation"
        expected_states=(ref["to_state"],ref["from_state"]) if label["is_direction_error"] else (
            ref["from_state"],ref["to_state"])
        assert (t["from_state"],t["to_state"])==expected_states, "mutation/label mismatch"
        extracted=extract_transitions(item["text"])["transitions"]
        assert len(extracted)==1, "controlled template not parsed"
        result=audit_transitions([Transition.from_dict(t)],
                                 [Transition.from_dict(extracted[0])],vocab)
        assert result["status"]=="consistent", "text does not preserve intended controlled structure"
    assert all(sorted(v)==["original","paraphrase","reversed"] for v in per_case.values())
    assert not manifest["formal_reference_freeze"]
    for name, digest in manifest["hashes"].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest, f"snapshot changed: {name}"
    return {"cases":len(refs),"sources":len(sources),"fields":len(emap),"candidates":len(inputs),
            "mechanism_groups":len(groups),"checks":"PASS","formal_reference_freeze":False}


if __name__ == "__main__":
    target=sys.argv[1] if len(sys.argv)>1 else "data/direction_audit/prototype_v0_1"
    print(json.dumps(validate(target),ensure_ascii=False,indent=2))
