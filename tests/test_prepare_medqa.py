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
            self.assertEqual(json.loads(written[0])["question"], "What causes angina?")

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
            self.assertEqual(json.loads(written[0])["question"], "Treatment for diabetes")


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
