from pathlib import Path
import tempfile
import unittest
from scripts.validate_direction_dataset import validate
from scripts.run_direction_audit import run

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data/direction_audit/prototype_v0_1"


class DatasetTests(unittest.TestCase):
    def test_traceability_mutations_no_label_leakage_and_snapshot(self):
        result=validate(DATA)
        self.assertEqual(result["cases"],10)
        self.assertEqual(result["fields"],50)
        self.assertEqual(result["candidates"],30)

    def test_default_runner_cannot_score_drafts_as_formal(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,"human approval"):
                run(DATA,directory)
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_pipeline_keeps_failures_and_separate_source_language_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            result=run(DATA,directory,allow_draft=True)
            self.assertEqual(result["conditions"]["automatic_rule_text"]["test"]["n"],24)
            self.assertEqual(result["source_language_challenge"]["n"],10)
            self.assertIsNone(result["source_language_challenge"]["direction_metrics"])
            self.assertEqual(result["formal_eligible_reference_count"],0)
            self.assertEqual(result["llm_baseline"],"not_run_no_configured_model")


if __name__=="__main__":
    unittest.main()
