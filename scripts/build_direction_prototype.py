"""Rebuild the source-traceable, NON-ADJUDICATED pilot from a fixed specification."""
from __future__ import annotations
import copy
import csv
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/"data/direction_audit/prototype_v0_1"
DATE = "2026-11-09"
BASE_COMMIT = "71611178ba8d04fe9e2e04f38c8ea0b46ea39ba8"

# At most 25 verbatim source words per source URL. Further evidence is a
# paraphrase plus a section locator, not copied full web pages.
SPECS = [
    dict(id="cardio_001", topic="冠脉介入开放狭窄冠状动脉", group="mechanical_dilation",
         object="Coronary Artery", process="Coronary Angioplasty", before="narrowed", after="open",
         context="Selected coronary artery with plaque-related narrowing, successful opening branch",
         modality="possible", process_alias="PCI", object_alias="coronary vessel",
         source="https://www.nhlbi.nih.gov/health/coronary-heart-disease/treatment",
         organization="NHLBI / NIH", section="Procedures — percutaneous coronary intervention",
         quote="opens coronary arteries that are narrowed or blocked by the buildup of plaque.",
         mapping="选择 narrowed 分支；open 仅指开放，不表示完全正常，也不声称永久不再狭窄。",
         source_paraphrase="PCI is used to reopen a coronary vessel affected by plaque."),
    dict(id="cardio_002", topic="起搏改善心动过缓", group="rhythm_control",
         object="Heart Rate", process="Cardiac Pacing", before="slower than normal", after="normal",
         context="Slow heartbeat sensed by a traditional pacemaker, intended response branch",
         modality="possible", process_alias="pacemaker stimulation", object_alias="cardiac rate",
         source="https://www.nhlbi.nih.gov/health/pacemakers/how-it-works",
         organization="NHLBI / NIH", section="Traditional transvenous pacemakers — electrodes",
         quote="When your heartbeat is slower than normal, the electrodes deliver electrical impulses to your heart to make it beat normally.",
         mapping="正常心率是该段给出的目标反应；本案例不包含设备失效或未响应分支。",
         source_paraphrase="The pacemaker can deliver an impulse when it senses bradycardia."),
    dict(id="cardio_003", topic="电复律恢复规则心律", group="rhythm_control",
         object="Heart Rhythm", process="Electrical Cardioversion", before="irregular", after="regular",
         context="Irregular heartbeat, successful electrical cardioversion branch",
         modality="possible", process_alias="electrical rhythm resetting", object_alias="cardiac rhythm",
         source="https://www.heart.org/en/health-topics/arrhythmia/prevention--treatment-of-arrhythmia/cardioversion",
         organization="American Heart Association", section="Cardioversion — introductory paragraph; electrical cardioversion",
         quote="If your heart has an irregular (uneven) beat or is beating too fast, cardioversion is a way to restore a regular rhythm.",
         mapping="选择 irregular 而不是 too fast 分支；选择电复律而不是药物复律；不保证每次成功。",
         source_paraphrase="An electric shock is one way clinicians try to restore an orderly cardiac rhythm."),
    dict(id="cardio_004", topic="主动脉瓣球囊扩张", group="mechanical_dilation",
         object="Aortic Valve Opening", process="Balloon Valvuloplasty", before="narrowed", after="wider",
         context="Childhood aortic stenosis, balloon widens the opening without implying a fully normal valve",
         modality="possible", process_alias="balloon valvotomy", object_alias="aortic orifice",
         source="https://www.heart.org/en/health-topics/congenital-heart-defects/about-congenital-heart-defects/aortic-valve-stenosis-avs",
         organization="American Heart Association", section="Aortic valve stenosis in children — How can the aortic valve be treated?",
         quote="due to the narrowed valve. The balloon is briefly inflated to widen the valve opening",
         quote_is_joined=True,
         mapping="摘录由两处短片段组成，需分别定位；wider 是相对增宽，不是完全正常。",
         source_paraphrase="A balloon catheter may enlarge the stenotic aortic opening; residual valve disease can remain."),
    dict(id="cardio_005", topic="心衰利尿减少多余体液", group="volume_management",
         object="Body Fluid Volume", process="Diuretic Treatment", before="excessive", after="reduced",
         context="Heart failure with extra fluid, intended diuretic response without asserting normal volume",
         modality="possible", process_alias="diuresis treatment", object_alias="body fluid amount",
         source="https://www.nhlbi.nih.gov/health/heart-failure/treatment",
         organization="NHLBI / NIH", section="Medicines — Left-sided heart failure — medicines removing extra sodium and fluid",
         quote="Medicines that remove extra sodium and fluid from your body",
         mapping="volume 是对体液量的建模；excessive 对应 extra；reduced 表示量减少，不承诺正常。",
         source_paraphrase="Diuretic medicines help eliminate surplus water in heart failure."),
    dict(id="cardio_006", topic="降压治疗降低高血压", group="pressure_control",
         object="Blood Pressure", process="Antihypertensive Treatment", before="high", after="lower",
         context="High blood pressure treated with medicines, lowering response without a guaranteed normal target",
         modality="possible", process_alias="blood pressure lowering therapy", object_alias="arterial pressure",
         source="https://www.nhlbi.nih.gov/health/high-blood-pressure/treatment",
         organization="NHLBI / NIH", section="Medicines — introductory paragraph",
         quote="These medicines act in different ways to lower blood pressure.",
         fragments=["When healthy lifestyle changes alone do not control or lower high blood pressure",
                    "These medicines act in different ways to lower blood pressure."],
         mapping="初始 high 依据该节适用人群与前一句；lower 是相对降低，不等于正常血压。",
         source_paraphrase="A clinician may prescribe a medicine to reduce persistently elevated arterial pressure."),
    dict(id="cardio_007", topic="CRT 改善左室壁收缩不同步", group="rhythm_control",
         object="Left Ventricular Wall Motion", process="Cardiac Resynchronisation Therapy",
         before="out of sync", after="synchronized",
         context="Heart failure with left ventricular wall dyssynchrony, CRT response branch",
         modality="possible", process_alias="CRT", object_alias="left ventricular wall contraction",
         source="https://111.wales.nhs.uk/Heartfailure/",
         organization="NHS 111 Wales", section="Treatment — Devices for heart failure — Cardiac resynchronisation therapy",
         quote="contract out of sync with each other; making the walls of the left ventricle all contract at the same time",
         quote_is_joined=True,
         mapping="两个短片段分别来自相邻两句；synchronized 是同一时间收缩的解释映射。",
         source_paraphrase="CRT can coordinate contractions of left ventricular walls that previously lacked synchrony."),
    dict(id="cardio_008", topic="心包穿刺减少积液量", group="volume_management",
         object="Pericardial Fluid Amount", process="Pericardiocentesis", before="accumulated", after="reduced",
         context="Pericardial fluid accumulation being drained, not a guarantee of zero fluid or no recurrence",
         modality="possible", process_alias="pericardial drainage", object_alias="pericardial fluid volume",
         source="https://medlineplus.gov/ency/article/003872.htm",
         organization="MedlinePlus / NLM", section="Definition; How the Test is Performed; Why the Test is Performed",
         quote="Pericardiocentesis is a procedure that uses a needle to remove fluid from the pericardial sac.",
         fragments=["Pericardiocentesis is a procedure", "remove fluid from the pericardial sac",
                    "pericardial fluid accumulation"],
         mapping="起始 accumulated 需结合 Why/Abnormal Results；体液量降低由排液解释映射，不能写成无积液。",
         source_paraphrase="A catheter inserted for pericardiocentesis permits pericardial fluid to drain."),
    dict(id="cardio_009", topic="稳定型心绞痛休息后缓解", group="ischemic_symptom_response",
         object="Chest Pain Status", process="Resting", before="present", after="relieved",
         context="Known stable angina episode, usual response to a few minutes of rest",
         modality="usually", process_alias="taking rest", object_alias="anginal pain status",
         source="https://www.nhlbi.nih.gov/health/angina/types",
         organization="NHLBI / NIH", section="Stable angina",
         quote="The pain usually goes away after you rest for a few minutes or take your angina medicine.",
         mapping="只适用于该段稳定型心绞痛，保留 usually；不外推至不稳定型心绞痛或所有胸痛。",
         source_paraphrase="A typical stable-angina episode often improves after a brief pause in activity."),
    dict(id="cardio_010", topic="肺循环血液氧合", group="cardiopulmonary_oxygenation",
         object="Blood", process="Pulmonary Oxygenation", before="oxygen poor", after="oxygen rich",
         context="Typical pulmonary circulation through functioning lungs",
         modality="usually", process_alias="oxygen uptake in the lungs", object_alias="circulating blood",
         source="https://www.nhlbi.nih.gov/health/heart/blood-flow",
         organization="NHLBI / NIH", section="Adding oxygen to blood",
         quote="Your lungs add oxygen to your blood. The oxygen-rich blood returns to your heart through the pulmonary veins.",
         fragments=["The pulmonary artery then carries the oxygen-poor blood",
                    "Your lungs add oxygen to your blood.", "The oxygen-rich blood returns to your heart"],
         mapping="起始 oxygen poor 来自同段前句；通常生理情境，不声称在肺功能异常时仍然成立。",
         source_paraphrase="Blood visiting the lungs takes up oxygen before returning to the left side of the heart."),
]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def sentence(t, pattern, process=None, obj=None):
    p, o = process or t["process"], obj or t["object"]
    a, b = t["from_state"], t["to_state"]
    modal = "usually" if t["modality"] == "usually" else "can"
    if pattern == 0:
        body = f"{p} {modal} change {o} from {a} to {b}."
    elif pattern == 1:
        body = f"During {p}, {o} {modal} move to {b} from {a}."
    elif pattern == 2:
        body = f"{o} {modal} move from {a} to {b} during {p}."
    elif pattern == 3:
        body = f"With {p}, {o} {modal} change from {a} to {b}."
    else:
        body = f"Before {p}, {o} is {a}; after the process, it {modal} become {b}."
    # Usually needs a third-person singular verb; parser accepts both forms.
    if modal == "usually":
        body = body.replace("usually change ", "usually changes ").replace(
            "usually move ", "usually moves ").replace("usually become ", "usually becomes ")
    return f'Context: {t["context"]}\n{body}'


def build():
    DEST.mkdir(parents=True, exist_ok=True)
    refs, sources, audit, challenges, rows = [], [], [], [], []
    vocab = {"objects": {}, "processes": {}, "states": {}}
    for i, s in enumerate(SPECS):
        source_id = f"SRC_{i+1:02d}"
        # Store disjoint excerpts separately rather than presenting a joined
        # string as one contiguous quote.
        fragments = s.get("fragments", [s["quote"]])
        if s.get("quote_is_joined"):
            fragments = (s["quote"].split(". ",1) if i == 3 else s["quote"].split("; ",1))
        sources.append({"source_id": source_id, "organization": s["organization"],
                        "url": s["source"], "section": s["section"],
                        "assistant_accessed_on": DATE, "access_timezone": "Asia/Tokyo",
                        "excerpt_fragments": [{"excerpt_id": f"E{k+1}", "text": x}
                                              for k,x in enumerate(fragments)],
                        "context_paraphrase": s["mapping"], "human_verified": False})
        t = dict(id="T1", object=s["object"], process=s["process"], from_state=s["before"],
                 to_state=s["after"], state_owner=s["object"], context=s["context"],
                 modality=s["modality"])
        split = "development" if s["group"] == "mechanical_dilation" else "test"
        ref = {"case_id": s["id"], "topic_id": s["id"], "topic_zh": s["topic"],
               "mechanism_group": s["group"], "split": split,
               "question_origin": "source_based_synthetic_not_medqa",
               "medqa_question_id": None,
               "question": f'How can {s["process"]} affect {s["object"]}?',
               "source_ids": [source_id], "reference_status": "assistant_checked_pending_human",
               "approved_for_formal_evaluation": False,
               "human_review": {"reviewer": None, "date": None, "decision": "pending"},
               "assistant_check": {"date": DATE, "level": "source_traceability_and_model_mapping",
                                   "unresolved_items": ["Human medical/OPM adjudication required",
                                                        "Validate OPL wording in OPCloud"]},
               "scope_note": s["mapping"], "transitions": [t],
               "opl_draft": f'{s["process"]} changes {s["object"]} from {s["before"]} to {s["after"]}.',
               "opl_caveat": "Draft OPL skeleton only; context and modality remain in JSON. Not OPCloud-validated."}
        refs.append(ref)
        for field in ("object","process","from_state","to_state","state_owner"):
            needs_mapping = field in ("object","process","state_owner") or (
                field in ("from_state","to_state") and i in (4,7))
            audit.append({"case_id": s["id"], "transition_id": "T1", "field": field,
                          "value": t[field], "source_id": source_id,
                          "evidence_locator": (
                              "E1 + E2 + E3" if i in (7,9) else
                              "E1 + E2" if i in (3,5,6) else "E1"),
                          "section": s["section"], "support_label":
                          "解释映射" if needs_mapping else "明确支持",
                          "mapping_note": s["mapping"],
                          "assistant_checked_on": DATE, "human_reviewer": "",
                          "human_review_date": "", "human_decision": "pending"})
        vocab["objects"][s["object"].lower()] = [s["object_alias"]]
        vocab["processes"][s["process"].lower()] = [s["process_alias"]]
        vocab["states"][s["object"].lower()] = {s["before"]: [], s["after"]: []}
        challenges.append({"case_id": s["id"], "text": s["source_paraphrase"],
                           "origin": "assistant_paraphrase_of_source_not_verbatim",
                           "expected_complete_tuple": None,
                           "note": "Coverage probe only; source wording does not spell out a complete tuple."})
        for version in ("original", "paraphrase", "reversed"):
            cand = copy.deepcopy(t); cand["id"] = "candidate_T1"
            error = version == "reversed"
            if error:
                cand["from_state"], cand["to_state"] = cand["to_state"], cand["from_state"]
            para = version == "paraphrase"
            text = sentence(cand, (i+1 if para else i) % 5,
                            s["process_alias"] if para else None,
                            s["object_alias"] if para else None)
            rows.append({"case_id": s["id"], "text": text, "transition": cand,
                         "split": split, "version": version, "error": error})
    random.Random(20261109).shuffle(rows)
    candidates, labels, structures = [], [], []
    for i, row in enumerate(rows, 1):
        key = f"sample_{i:04d}"
        candidates.append({"sample_id": key, "case_id": row["case_id"], "text": row["text"]})
        labels.append({"sample_id": key, "case_id": row["case_id"], "split": row["split"],
                       "variant": row["version"], "is_direction_error": row["error"],
                       "target_transition_ids": ["T1"] if row["error"] else [],
                       "label_origin": "controlled_structural_mutation_not_human_annotation"})
        structures.append({"sample_id": key, "transitions": [row["transition"]],
                           "origin": "fixture_author_structures_not_human_gold"})
    write_json(DEST/"sources.json", sources)
    write_json(DEST/"references.json", refs)
    write_json(DEST/"vocabulary.json", vocab)
    for name, values in [("candidates.public.jsonl", candidates), ("labels.private.jsonl", labels),
                         ("structures.private.jsonl", structures),
                         ("source_language_challenge.jsonl", challenges)]:
        (DEST/name).write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in values),
                              encoding="utf-8")
    with (DEST/"field_evidence.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(audit[0]));writer.writeheader();writer.writerows(audit)
    checklist = {"date": DATE, "case_count":len(refs), "source_count": len(sources),
                 "field_checks": len(audit), "human_approved": 0,
                 "candidate_count": len(candidates), "mechanism_group_count":len({s["group"] for s in SPECS}),
                 "evidence_problems": "Pending interpretation/human review is not a measured contradiction rate"}
    write_json(DEST/"inventory.json",checklist)
    paths = sorted(p for p in DEST.iterdir() if p.is_file() and p.name != "snapshot_manifest.json")
    manifest = {"snapshot_kind": "technical_prototype_only", "snapshot_version":"0.1",
                "date":DATE, "base_repository_commit":BASE_COMMIT,
                "formal_reference_freeze":False, "human_approved_count":0,
                "split_unit":"mechanism_group", "development_cases":2,"test_cases":8,
                "hashes":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    write_json(DEST/"snapshot_manifest.json",manifest)
    print(json.dumps(checklist,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    build()
