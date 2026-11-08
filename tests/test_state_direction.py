from dataclasses import replace
import unittest
from src.evaluation.state_direction import (Transition, Vocabulary, audit_transitions,
    extract_transitions, require_formal_reference, score_predictions)


class DirectionTests(unittest.TestCase):
    def setUp(self):
        self.r = Transition("T1", "Blood", "Oxygenating", "poor", "rich", "Blood",
                            "pulmonary circulation", "possible")

    def audit(self, c, refs=None, vocab=None):
        return audit_transitions(refs or [self.r], [c], vocab)

    def test_reversal_and_exact_localization(self):
        result=self.audit(replace(self.r,id="C9",from_state="rich",to_state="poor",span=(4,30)))
        self.assertTrue(result["predicted_error"])
        self.assertEqual(result["findings"][0]["reference_transition_id"],"T1")
        self.assertEqual(result["findings"][0]["span"],(4,30))

    def test_identical_states_consistent(self):
        self.assertEqual(self.audit(self.r)["status"],"consistent")

    def test_unknown_states_cannot_be_assumed(self):
        for field in ("from_state","to_state"):
            with self.subTest(field=field):
                self.assertEqual(self.audit(replace(self.r,**{field:None}))["status"],"unresolved")

    def test_ambiguous_object_process_alignment(self):
        self.assertEqual(self.audit(self.r,[self.r,replace(self.r,id="T2")])["status"],"unresolved")

    def test_wrong_owner_abstains(self):
        self.assertEqual(self.audit(replace(self.r,state_owner="Lung"))["status"],"unresolved")

    def test_changed_context_or_modality_abstains(self):
        for field,value in [("context","systemic circulation"),("modality","asserted")]:
            self.assertEqual(self.audit(replace(self.r,**{field:value}))["status"],"unresolved")

    def test_unrelated_process_does_not_align(self):
        self.assertEqual(self.audit(replace(self.r,process="Deoxygenating"))["status"],"unresolved")

    def test_aliases_are_typed_and_states_are_scoped(self):
        v=Vocabulary({"objects":{"blood":["circulating blood"]},
                      "processes":{"oxygenating":["oxygen uptake"]},
                      "states":{"blood":{"poor":["low"],"rich":["high"]},
                                "artery":{"narrow":["low"]}}})
        c=replace(self.r,object="Circulating Blood",state_owner="Blood",
                  process="oxygen uptake",from_state="high",to_state="low")
        self.assertTrue(self.audit(c,vocab=v)["predicted_error"])
        self.assertEqual(v.canonical("states","low","artery"),"narrow")

    def test_colliding_aliases_abstain(self):
        v=Vocabulary({"objects":{"blood":["ambiguous"],"lung":["ambiguous"]}})
        self.assertEqual(v.canonical("objects","ambiguous"),"")

    def test_parser_preserves_direction_in_to_from_order(self):
        text="Context: pulmonary circulation\nDuring Oxygenating, Blood can move to rich from poor."
        out=extract_transitions(text)["transitions"][0]
        self.assertEqual((out["from_state"],out["to_state"]),("poor","rich"))
        self.assertEqual(text[slice(*out["span"])],text.split("\n")[1])

    def test_negated_or_compound_text_abstains(self):
        for text in ["Oxygenating does not change Blood from poor to rich.",
                     "Oxygenating can change Blood from poor to rich or poor.",
                     "Oxygenating can change Blood from poor to rich. The reverse also occurs."]:
            self.assertEqual(extract_transitions(text)["transitions"],[])

    def test_empty_text_abstains(self):
        self.assertEqual(extract_transitions("")["transitions"],[])

    def test_missing_context_cannot_be_silently_copied(self):
        out=extract_transitions("Oxygenating can change Blood from poor to rich.")
        c=Transition.from_dict(out["transitions"][0])
        self.assertEqual(self.audit(c)["status"],"unresolved")

    def test_unmatched_reference_not_called_consistent(self):
        refs=[self.r,replace(self.r,id="T2",object="Lung",state_owner="Lung")]
        self.assertEqual(self.audit(self.r,refs)["status"],"unresolved")

    def test_unknown_reference_not_direction_gold(self):
        self.assertEqual(self.audit(self.r,[replace(self.r,from_state=None)])["status"],"unresolved")
        self.assertEqual(self.audit(replace(self.r,from_state="unknown"),
                                    [replace(self.r,from_state="unknown")])["status"],"unresolved")

    def test_score_abstention_and_bad_localization(self):
        gold={"p":{"is_direction_error":True,"target_transition_ids":["T1"]},
              "n":{"is_direction_error":False,"target_transition_ids":[]}}
        pred=[{"sample_id":"p","predicted_error":True,"status":"direction_reversed",
               "findings":[{"type":"direction_reversed","reference_transition_id":"WRONG"}]},
              {"sample_id":"n","predicted_error":False,"status":"unresolved","findings":[]}]
        score=score_predictions(pred,gold)
        self.assertEqual(score["detection"]["f1"],1.0)
        self.assertEqual(score["localization"]["f1"],0)
        self.assertEqual(score["negative_unresolved"],1)
        self.assertEqual(score["coverage"],0.5)

    def test_positive_abstention_is_false_negative(self):
        s=score_predictions([{"sample_id":"p","status":"unresolved","predicted_error":False}],
                            {"p":{"is_direction_error":True}})
        self.assertEqual(s["fn"],1)
        self.assertEqual(s["detection"]["f1"],0)

    def test_score_rejects_missing_and_duplicate_samples(self):
        with self.assertRaises(ValueError):
            score_predictions([],{"a":{"is_direction_error":True}})
        with self.assertRaises(ValueError):
            score_predictions([{"sample_id":"a"},{"sample_id":"a"}],{"a":{}})

    def test_formal_gate_rejects_pending_review(self):
        with self.assertRaises(ValueError):
            require_formal_reference([{"approved_for_formal_evaluation":False}])


if __name__ == "__main__":
    unittest.main()
