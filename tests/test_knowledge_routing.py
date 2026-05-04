"""Routing checks for the bundled cardiology knowledge base.

These tests use synthetic questions only. They guard against common audit
failure modes where specific cardiology concepts fall into broader topics.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from reasoning import RuleBasedCardiologyReasoner, load_topics


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE = PROJECT_ROOT / "data" / "processed" / "cardiology_knowledge.json"


class KnowledgeRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reasoner = RuleBasedCardiologyReasoner(load_topics(KNOWLEDGE_BASE))

    def assert_routes_to(self, question: str, expected_topic: str) -> None:
        result = self.reasoner.answer(question)
        self.assertEqual(result.matched_topic, expected_topic)

    def test_atrial_fibrillation_does_not_route_to_generic_arrhythmia(self) -> None:
        self.assert_routes_to(
            "ECG shows absent P waves and an irregularly irregular rhythm.",
            "atrial fibrillation",
        )

    def test_endocarditis_does_not_route_to_heart_failure_or_angina(self) -> None:
        self.assert_routes_to(
            "Fever with positive blood cultures and valve vegetations suggests what?",
            "infective endocarditis",
        )

    def test_aortic_stenosis_routes_to_specific_valve_topic(self) -> None:
        self.assert_routes_to(
            "Harsh systolic ejection murmur radiating to the carotids.",
            "aortic stenosis",
        )

    def test_mitral_regurgitation_routes_to_specific_valve_topic(self) -> None:
        self.assert_routes_to(
            "Holosystolic murmur at the apex with backflow into the left atrium.",
            "mitral regurgitation",
        )

    def test_mitral_valve_prolapse_routes_to_specific_valve_topic(self) -> None:
        self.assert_routes_to(
            "Midsystolic click followed by a late systolic murmur.",
            "mitral valve prolapse",
        )

    def test_pda_does_not_route_to_hypertension(self) -> None:
        self.assert_routes_to(
            "Continuous machine-like murmur from a patent ductus arteriosus.",
            "patent ductus arteriosus",
        )

    def test_tetralogy_of_fallot_does_not_route_to_hypertension(self) -> None:
        self.assert_routes_to(
            "Cyanotic congenital heart disease with VSD and overriding aorta.",
            "tetralogy of Fallot",
        )

    def test_coarctation_does_not_route_to_hypertension(self) -> None:
        self.assert_routes_to(
            "Upper extremity hypertension with weak femoral pulses and rib notching.",
            "coarctation of the aorta",
        )

    def test_pulmonary_embolism_routes_to_specific_topic(self) -> None:
        self.assert_routes_to(
            "Sudden dyspnea and pleuritic chest pain after deep vein thrombosis.",
            "pulmonary embolism",
        )


if __name__ == "__main__":
    unittest.main()
