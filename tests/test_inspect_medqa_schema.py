"""Tests for the ``inspect_medqa_schema.py`` CLI script."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import inspect_medqa_schema


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "inspect_medqa_schema.py"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record) + "\n")


class PreviewTests(unittest.TestCase):
    def test_truncate_text_shortens_long_content(self) -> None:
        text = "A " + ("very " * 80) + "long question"

        preview = inspect_medqa_schema.truncate_text(text, max_length=40)

        self.assertLessEqual(len(preview), 40)
        self.assertTrue(preview.endswith("..."))

    def test_preview_record_truncates_nested_options(self) -> None:
        record = {
            "question": "Short question?",
            "options": {"A": "x" * 200, "B": "short"},
        }

        preview = inspect_medqa_schema.preview_record(record)

        self.assertEqual(preview["question"], "Short question?")
        self.assertTrue(preview["options"]["A"].endswith("..."))
        self.assertEqual(preview["options"]["B"], "short")


class InspectRecordsTests(unittest.TestCase):
    def test_counts_records_fields_and_previews(self) -> None:
        records = [
            {
                "question": "What causes angina?",
                "options": {"A": "Angina"},
                "answer": "Angina",
                "answer_idx": "A",
                "extra": "field",
            },
            {"question": "What causes arrhythmia?", "answer": "Arrhythmia"},
            {"options": {"A": "Pancreas"}},
        ]

        summary = inspect_medqa_schema.inspect_records(records, max_preview=2)

        self.assertEqual(summary["record_count"], 3)
        self.assertEqual(summary["field_counts"]["question"], 2)
        self.assertEqual(summary["field_counts"]["options"], 2)
        self.assertEqual(summary["field_counts"]["answer"], 2)
        self.assertEqual(summary["field_counts"]["answer_idx"], 1)
        self.assertEqual(summary["observed_fields"], ["answer", "answer_idx", "extra", "options", "question"])
        self.assertEqual(len(summary["previews"]), 2)

    def test_max_preview_zero_suppresses_previews(self) -> None:
        summary = inspect_medqa_schema.inspect_records(
            [{"question": "What causes angina?"}],
            max_preview=0,
        )

        self.assertEqual(summary["previews"], [])


class FormatReportTests(unittest.TestCase):
    def test_report_contains_schema_summary(self) -> None:
        summary = {
            "record_count": 1,
            "observed_fields": ["answer", "question"],
            "field_counts": {
                "question": 1,
                "options": 0,
                "answer": 1,
                "answer_idx": 0,
            },
            "previews": [{"question": "What causes angina?", "answer": "Angina"}],
        }

        report = inspect_medqa_schema.format_report(Path("sample.jsonl"), summary)

        self.assertIn("Records: 1", report)
        self.assertIn("- question", report)
        self.assertIn("- answer_idx: 0", report)
        self.assertIn("Redacted preview", report)


class MainTests(unittest.TestCase):
    def test_main_prints_summary_for_synthetic_jsonl(self) -> None:
        with TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "synthetic.jsonl"
            _write_jsonl(
                input_path,
                [
                    {"question": "What causes angina?", "answer": "Angina"},
                    {"options": {"A": "Arrhythmia"}, "answer_idx": "A"},
                ],
            )

            out = io.StringIO()
            with redirect_stdout(out):
                exit_code = inspect_medqa_schema.main(
                    ["--input", str(input_path), "--max-preview", "1"]
                )

            output = out.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("Records: 2", output)
            self.assertIn("- question: 1", output)
            self.assertIn("- options: 1", output)
            self.assertIn("Record 1:", output)
            self.assertNotIn("Record 2:", output)

    def test_main_reports_missing_input(self) -> None:
        with TemporaryDirectory() as tmp:
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                exit_code = inspect_medqa_schema.main(
                    ["--input", str(Path(tmp) / "missing.jsonl")]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("File not found", err.getvalue())

    def test_main_reports_invalid_json(self) -> None:
        with TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "broken.jsonl"
            input_path.write_text('{"question": "ok"}\n{not json}\n', encoding="utf-8")

            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                exit_code = inspect_medqa_schema.main(["--input", str(input_path)])

        self.assertEqual(exit_code, 1)
        self.assertIn("Invalid JSON", err.getvalue())


class ScriptInvocationTests(unittest.TestCase):
    def test_script_runs_on_synthetic_fixture(self) -> None:
        with TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "synthetic.jsonl"
            _write_jsonl(
                input_path,
                [{"question": "What causes hypertension?", "answer": "Hypertension"}],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input",
                    str(input_path),
                    "--max-preview",
                    "1",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("Records: 1", result.stdout)
            self.assertIn("Observed top-level fields", result.stdout)


if __name__ == "__main__":
    unittest.main()
