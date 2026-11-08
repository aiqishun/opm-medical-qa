"""Conservative state-transition auditing for a controlled-language prototype.

This is not an unrestricted medical NLP extractor. Unknown, negated, ambiguous,
or out-of-grammar statements abstain instead of inheriting reference states.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Mapping, Sequence


def normalize(value: str | None) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip().lower().replace("_", " ")).strip(" .")
    return "" if text in {"unknown", "null", "none", "unspecified", "not given", "未给出"} else text


@dataclass(frozen=True)
class Transition:
    id: str
    object: str | None
    process: str | None
    from_state: str | None
    to_state: str | None
    state_owner: str | None = None
    context: str | None = None
    modality: str | None = None
    span: tuple[int, int] | None = None

    @classmethod
    def from_dict(cls, item: Mapping) -> "Transition":
        keys = cls.__dataclass_fields__
        return cls(**{k: v for k, v in item.items() if k in keys})


class Vocabulary:
    """Aliases are typed; state aliases belong to an object, not a global pool."""

    def __init__(self, data: Mapping | None = None):
        self.data = data or {}

    def canonical(self, kind: str, value: str | None, owner: str | None = None) -> str:
        term = normalize(value)
        if not term:
            return ""
        aliases = self.data.get(kind, {})
        if kind == "states":
            aliases = aliases.get(self.canonical("objects", owner), {})
        matches = {normalize(canon) for canon, names in aliases.items()
                   if term in {normalize(canon), *(normalize(n) for n in names)}}
        if len(matches) > 1:
            return ""  # Conflicting aliases must not choose an arbitrary match.
        return next(iter(matches)) if matches else term


_PATTERNS = [
    r"(?P<process>.+?) (?:can |may |usually )?changes? (?P<object>.+?) from (?P<before>.+?) to (?P<after>[^.;]+)",
    r"During (?P<process>[^,]+), (?P<object>.+?) (?:can |may |usually )?moves? to (?P<after>.+?) from (?P<before>[^.;]+)",
    r"(?P<object>.+?) (?:can |may |usually )?moves? from (?P<before>.+?) to (?P<after>.+?) during (?P<process>[^.;]+)",
    r"With (?P<process>[^,]+), (?P<object>.+?) (?:can |may |usually )?changes? from (?P<before>.+?) to (?P<after>[^.;]+)",
    r"Before (?P<process>[^,]+), (?P<object>.+?) is (?P<before>[^;]+); after the process, it (?:can |may |usually )?becomes? (?P<after>[^.;]+)",
]
_COMPILED = [re.compile(r"\A" + p + r"\.?\Z", re.I) for p in _PATTERNS]
_UNSAFE = re.compile(r"\b(?:not|never|no|cannot|can't|without|neither|denies)\b", re.I)


def extract_transitions(text: str) -> dict:
    """Extract one explicit transition; consume text only, never gold metadata."""
    if not isinstance(text, str) or not text.strip():
        return {"transitions": [], "reason": "empty_input"}
    context = None
    body = text.strip()
    if body.startswith("Context: ") and "\n" in body:
        head, body = body.split("\n", 1)
        context = head[len("Context: "):].strip()
    if _UNSAFE.search(body):
        return {"transitions": [], "reason": "negation_or_exclusion_out_of_scope"}
    matches = [p.fullmatch(body.strip()) for p in _COMPILED]
    matches = [m for m in matches if m is not None]
    if len(matches) != 1:
        return {"transitions": [], "reason": "unsupported_or_ambiguous_grammar"}
    m = matches[0]
    modal = "possible" if re.search(r"\b(can|may)\b", body, re.I) else (
        "usually" if re.search(r"\busually\b", body, re.I) else "asserted")
    if re.search(r"\b(and|or)\b", m["before"] + " " + m["after"], re.I):
        return {"transitions": [], "reason": "branch_or_composite_state"}
    start = text.index(body)
    t = Transition("candidate_T1", m["object"].strip(), m["process"].strip(),
                   m["before"].strip(), m["after"].strip(), m["object"].strip(),
                   context, modal, (start, start + len(body)))
    return {"transitions": [asdict(t)], "reason": None}


def audit_transitions(reference: Sequence[Transition], candidate: Sequence[Transition],
                      vocabulary: Vocabulary | None = None) -> dict:
    vocab = vocabulary or Vocabulary()
    findings, unresolved, aligned = [], [], 0
    if not reference or not candidate:
        return {"status": "unresolved", "predicted_error": False, "findings": [],
                "unresolved": [{"reason": "no_reference_or_extracted_transition"}]}
    used = set()
    for c in candidate:
        obj = vocab.canonical("objects", c.object)
        proc = vocab.canonical("processes", c.process)
        if not obj or not proc:
            unresolved.append({"candidate_id": c.id, "reason": "missing_alignment_key"})
            continue
        possible = [r for r in reference
                    if obj == vocab.canonical("objects", r.object)
                    and proc == vocab.canonical("processes", r.process)]
        if len(possible) != 1:
            unresolved.append({"candidate_id": c.id, "reason": "alignment_missing_or_ambiguous"})
            continue
        r = possible[0]
        if r.id in used:
            unresolved.append({"candidate_id": c.id, "reason": "duplicate_candidate_alignment"})
            continue
        used.add(r.id)
        if (not c.context or not r.context or normalize(c.context) != normalize(r.context)
                or not c.modality or not r.modality or c.modality != r.modality):
            unresolved.append({"candidate_id": c.id, "reason": "context_or_modality_mismatch"})
            continue
        if (vocab.canonical("objects", c.state_owner) != obj
                or vocab.canonical("objects", r.state_owner) != obj):
            unresolved.append({"candidate_id": c.id, "reason": "state_owner_mismatch"})
            continue
        a, b = [vocab.canonical("states", x, obj) for x in (r.from_state, r.to_state)]
        x, y = [vocab.canonical("states", s, obj) for s in (c.from_state, c.to_state)]
        if not all((a, b, x, y)) or a == b or x == y:
            unresolved.append({"candidate_id": c.id, "reason": "unknown_or_degenerate_states"})
            continue
        aligned += 1
        if (x, y) == (b, a):
            findings.append({"type": "direction_reversed", "reference_transition_id": r.id,
                             "candidate_transition_id": c.id, "span": c.span,
                             "reference_direction": [a, b], "candidate_direction": [x, y]})
        elif (x, y) != (a, b):
            unresolved.append({"candidate_id": c.id, "reason": "different_states_not_reversal"})
    for r in reference:
        if r.id not in used:
            unresolved.append({"reference_id": r.id, "reason": "unmatched_reference"})
    status = "direction_reversed" if findings else (
        "consistent" if aligned and not unresolved else "unresolved")
    return {"status": status, "predicted_error": bool(findings), "findings": findings,
            "unresolved": unresolved}


def score_predictions(predictions: Sequence[Mapping], gold: Mapping[str, Mapping]) -> dict:
    """Include every sample; preserve abstentions and score localization separately."""
    ids = [p["sample_id"] for p in predictions]
    if len(ids) != len(set(ids)) or set(ids) != set(gold):
        raise ValueError("Prediction/gold sample IDs must match exactly, with no duplicates")
    tp = fp = fn = tn = abstain = negative_abstain = 0
    loc_pred, loc_gold = set(), set()
    for p in predictions:
        key = p["sample_id"]
        g = gold[key]
        actual, predicted = bool(g["is_direction_error"]), bool(p["predicted_error"])
        tp += actual and predicted
        fp += not actual and predicted
        fn += actual and not predicted
        tn += not actual and not predicted
        abstain += p["status"] == "unresolved"
        negative_abstain += not actual and p["status"] == "unresolved"
        loc_gold.update((key, t) for t in g.get("target_transition_ids", []))
        loc_pred.update((key, f["reference_transition_id"]) for f in p.get("findings", [])
                        if f["type"] == "direction_reversed")
    def measures(t, f, n, positive_count):
        precision = t / (t + f) if t + f else 0.0
        recall = t / positive_count if positive_count else None
        f1 = 2*t/(2*t+f+n) if positive_count else None
        return {"precision": precision, "recall": recall, "f1": f1,
                "precision_denominator_zero": not bool(t + f)}
    n = len(predictions)
    return {"n": n, "positives": tp+fn, "negatives": fp+tn,
            "tp": tp, "fp": fp, "fn": fn, "tn_binary": tn,
            "unresolved": abstain, "negative_unresolved": negative_abstain,
            "coverage": (n-abstain)/n if n else None,
            "false_positive_rate": fp/(fp+tn) if fp+tn else None,
            "detection": measures(tp, fp, fn, tp+fn),
            "localization": measures(len(loc_pred & loc_gold), len(loc_pred-loc_gold),
                                     len(loc_gold-loc_pred), len(loc_gold)),
            "note": "Unresolved positive -> FN. Binary TN includes negative abstentions; "
                    "these are not confirmed-consistent answers."}


def require_formal_reference(references: Sequence[Mapping]) -> None:
    if not references or any(not r.get("approved_for_formal_evaluation")
                             or not r.get("human_review", {}).get("reviewer")
                             or not r.get("human_review", {}).get("date")
                             or r.get("human_review", {}).get("decision") != "approved"
                             for r in references):
        raise ValueError("Formal evaluation blocked: references lack actual human approval")
