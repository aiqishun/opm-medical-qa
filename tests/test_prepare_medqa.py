"""Tests for the ``prepare_medqa.py`` CLI script."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import prepare_medqa


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "prepare_medqa.py"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record) + "\n")


class RecordTextTests(unittest.TestCase):
    def test_collects_text_from_known_fields(self) -> None:
        text = prepare_medqa.record_text(
            {
                "question": "Heart attack?",
                "answer": "MI",
                "answer_idx": "A",
                "explanation": "Coronary blockage.",
                "options": {"A": "MI", "B": "Asthma"},
            }
        )

        self.assertIn("heart attack", text)
        self.assertIn("coronary blockage", text)
        self.assertIn("asthma", text)

    def test_handles_options_as_list(self) -> None:
        text = prepare_medqa.record_text({"options": ["Angina", "Migraine"]})
        self.assertIn("angina", text)
        self.assertIn("migraine", text)

    def test_handles_missing_fields(self) -> None:
        text = prepare_medqa.record_text({})
        self.assertEqual(text.strip(), "")


class IsCardiologyRelatedTests(unittest.TestCase):
    def test_matches_default_keyword(self) -> None:
        self.assertTrue(
            prepare_medqa.is_cardiology_related({"question": "What causes angina?"})
        )

    def test_skips_unrelated_record(self) -> None:
        self.assertFalse(
            prepare_medqa.is_cardiology_related(
                {"question": "Which organ produces insulin?"}
            )
        )

    def test_custom_keywords(self) -> None:
        self.assertTrue(
            prepare_medqa.is_cardiology_related(
                {"question": "Treatment for diabetes"},
                keywords=("diabetes",),
            )
        )


class MatchedTermsTests(unittest.TestCase):
    def test_reports_all_matching_terms_once(self) -> None:
        record = {
            "question": "Myocardial infarction after coronary artery disease.",
            "explanation": "Myocardial infarction is repeated.",
        }

        terms = prepare_medqa.matched_terms_for_record(
            record,
            keywords=("myocardial infarction", "coronary artery disease"),
        )

        self.assertEqual(terms, ["myocardial infarction", "coronary artery disease"])

    def test_strict_terms_avoid_generic_vital_sign_mentions(self) -> None:
        record = {
            "question": "Past medical history includes hypertension.",
            "explanation": "Vital signs show heart rate 80 and normal blood pressure.",
        }

        broad_terms = prepare_medqa.matched_terms_for_record(
            record,
            prepare_medqa.CARDIOLOGY_KEYWORDS,
        )
        strict_terms = prepare_medqa.matched_terms_for_record(
            record,
            prepare_medqa.STRICT_CARDIOLOGY_KEYWORDS,
        )

        self.assertIn("heart", broad_terms)
        self.assertIn("blood pressure", broad_terms)
        self.assertEqual(strict_terms, [])

    def test_high_confidence_disease_term_selects_directly(self) -> None:
        record = {"question": "Chest pain from myocardial infarction."}

        terms = prepare_medqa.high_confidence_matched_terms(record)

        self.assertEqual(terms, ["myocardial infarction"])

    def test_high_confidence_rejects_ecg_without_specific_context(self) -> None:
        record = {"question": "An ECG was ordered during routine evaluation."}

        self.assertEqual(prepare_medqa.high_confidence_matched_terms(record), [])

    def test_high_confidence_allows_ecg_with_specific_context(self) -> None:
        record = {"question": "ECG shows ST elevation in the anterior leads."}

        terms = prepare_medqa.high_confidence_matched_terms(record)

        self.assertEqual(terms, ["ecg", "st elevation"])

    def test_high_confidence_allows_ekg_with_arrhythmia_context(self) -> None:
        record = {"question": "EKG reveals absent P waves."}

        terms = prepare_medqa.high_confidence_matched_terms(record)

        self.assertEqual(terms, ["ekg", "absent p waves"])

    def test_high_confidence_rejects_murmur_without_specific_context(self) -> None:
        record = {"question": "A soft murmur is noted on exam."}

        self.assertEqual(prepare_medqa.high_confidence_matched_terms(record), [])

    def test_high_confidence_allows_murmur_with_valve_context(self) -> None:
        record = {"question": "A harsh murmur suggests aortic stenosis."}

        terms = prepare_medqa.high_confidence_matched_terms(record)

        self.assertEqual(terms, ["aortic stenosis", "murmur"])


class FilterCardiologyRecordsTests(unittest.TestCase):
    def test_keeps_only_matching_records(self) -> None:
        records = [
            {"question": "What causes angina?"},
            {"question": "Pancreas function?"},
            {"question": "Coronary artery anatomy"},
        ]
        filtered = prepare_medqa.filter_cardiology_records(records)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0]["question"], "What causes angina?")
        self.assertEqual(filtered[0]["matched_terms"], ["angina"])
        self.assertEqual(filtered[0]["filter_confidence"], "broad")

    def test_strict_mode_keeps_topic_specific_terms_only(self) -> None:
        records = [
            {"question": "Past medical history includes hypertension."},
            {"question": "ECG shows atrial fibrillation."},
            {"question": "Blood pressure is 120 over 80."},
        ]

        filtered = prepare_medqa.filter_cardiology_records(
            records,
            keywords=prepare_medqa.STRICT_CARDIOLOGY_KEYWORDS,
        )

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["question"], "ECG shows atrial fibrillation.")
        self.assertEqual(filtered[0]["matched_terms"], ["ecg", "atrial fibrillation"])

    def test_high_confidence_mode_filters_contextually(self) -> None:
        records = [
            {"question": "ECG was performed for screening."},
            {"question": "ECG shows QT prolongation."},
            {"question": "Murmur heard on exam."},
            {"question": "Murmur with cyanosis is concerning."},
            {"question": "Past medical history includes hypertension."},
            {"question": "Cardiac arrest occurred suddenly."},
        ]

        filtered = prepare_medqa.filter_cardiology_records(
            records,
            keywords=prepare_medqa.FILTER_MODE_KEYWORDS["high_confidence"],
            filter_confidence="high_confidence",
        )

        self.assertEqual(len(filtered), 3)
        self.assertEqual(
            [record["matched_terms"] for record in filtered],
            [
                ["ecg", "qt prolongation"],
                ["murmur", "cyanosis"],
                ["cardiac arrest"],
            ],
        )
        self.assertEqual(
            {record["filter_confidence"] for record in filtered},
            {"high_confidence"},
        )


class MainTests(unittest.TestCase):
    def test_main_writes_filtered_file(self) -> None:
        with TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "in.jsonl"
            output_path = Path(tmp) / "out.jsonl"
            _write_jsonl(
                input_path,
                [
                    {"question": "What causes angina?"},
                    {"question": "Pancreas function?"},
                ],
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = prepare_medqa.main(
                    ["--input", str(input_path), "--output", str(output_path)]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("Cardiology examples: 1", buffer.getvalue())
            written = output_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(written), 1)
            row = json.loads(written[0])
            self.assertEqual(row["question"], "What causes angina?")
            self.assertEqual(row["matched_terms"], ["angina"])
            self.assertEqual(row["filter_confidence"], "broad")

    def test_main_strict_mode_excludes_generic_broad_terms(self) -> None:
        with TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "in.jsonl"
            output_path = Path(tmp) / "out.jsonl"
            _write_jsonl(
                input_path,
                [
                    {"question": "Past medical history includes hypertension."},
                    {"question": "What finding on ECG suggests arrhythmia?"},
                ],
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = prepare_medqa.main(
                    [
                        "--input", str(input_path),
                        "--output", str(output_path),
                        "--filter-mode", "strict",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("Filter mode: strict", buffer.getvalue())
            written = output_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(written), 1)
            row = json.loads(written[0])
            self.assertEqual(row["matched_terms"], ["arrhythmia", "ecg"])
            self.assertEqual(row["filter_confidence"], "strict")

    def test_main_high_confidence_mode_uses_context_rules(self) -> None:
        with TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "in.jsonl"
            output_path = Path(tmp) / "out.jsonl"
            _write_jsonl(
                input_path,
                [
                    {"question": "ECG was normal."},
                    {"question": "EKG shows ventricular tachycardia."},
                    {"question": "Murmur suggests mitral regurgitation."},
                    {"question": "Blood pressure is elevated."},
                ],
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = prepare_medqa.main(
                    [
                        "--input", str(input_path),
                        "--output", str(output_path),
                        "--filter-mode", "high_confidence",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("Filter mode: high_confidence", buffer.getvalue())
            rows = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["matched_terms"], ["ekg", "ventricular tachycardia"])
            self.assertEqual(rows[1]["matched_terms"], ["mitral regurgitation", "murmur"])
            self.assertEqual(
                {row["filter_confidence"] for row in rows},
                {"high_confidence"},
            )

    def test_main_reports_missing_input(self) -> None:
        with TemporaryDirectory() as tmp:
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                exit_code = prepare_medqa.main(
                    [
                        "--input",
                        str(Path(tmp) / "missing.jsonl"),
                        "--output",
                        str(Path(tmp) / "out.jsonl"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("File not found", err.getvalue())

    def test_main_reports_invalid_json(self) -> None:
        with TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "in.jsonl"
            input_path.write_text('{"x": 1}\n{not json}\n', encoding="utf-8")

            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                exit_code = prepare_medqa.main(
                    [
                        "--input",
                        str(input_path),
                        "--output",
                        str(Path(tmp) / "out.jsonl"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("Invalid JSON", err.getvalue())

    def test_keyword_override(self) -> None:
        with TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "in.jsonl"
            output_path = Path(tmp) / "out.jsonl"
            _write_jsonl(
                input_path,
                [
                    {"question": "Treatment for diabetes"},
                    {"question": "What causes angina?"},
                ],
            )

            with redirect_stdout(io.StringIO()):
                exit_code = prepare_medqa.main(
                    [
                        "--input",
                        str(input_path),
                        "--output",
                        str(output_path),
                        "--keyword",
                        "diabetes",
                    ]
                )

            self.assertEqual(exit_code, 0)
            written = output_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(written), 1)
            row = json.loads(written[0])
            self.assertEqual(row["question"], "Treatment for diabetes")
            self.assertEqual(row["matched_terms"], ["diabetes"])
            self.assertEqual(row["filter_confidence"], "custom")


class ScriptInvocationTests(unittest.TestCase):
    def test_script_runs_with_bundled_sample(self) -> None:
        with TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "filtered.jsonl"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input",
                    str(PROJECT_ROOT / "data" / "raw" / "medqa_sample.jsonl"),
                    "--output",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("Cardiology examples:", result.stdout)
            self.assertTrue(output_path.exists())
            lines = output_path.read_text(encoding="utf-8").splitlines()
            # The bundled raw sample has 19 synthetic records: 16 cardiology
            # (14 supported topics + 2 cardiology-adjacent fallbacks) and
            # 3 non-cardiology controls that should be filtered out.
            self.assertEqual(len(lines), 16)


if __name__ == "__main__":
    unittest.main()
