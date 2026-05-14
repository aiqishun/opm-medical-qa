"""Tests for ``export_manual_eval_sample.py``.

All fixtures are synthetic. No real MedQA data is used.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import export_manual_eval_sample


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "export_manual_eval_sample.py"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _batch_row(index: int, **overrides) -> dict:
    row = {
        "id": f"case-{index}",
        "question": f"Synthetic cardiology question {index}?",
        "matched_topic": "atrial fibrillation",
        "status": "matched",
        "matched_terms": ["atrial fibrillation"],
        "filter_confidence": "high_confidence",
        "answer": "Synthetic answer.",
        "graph_path": f"outputs/graphs/case-{index}.json",
    }
    row.update(overrides)
    return row


class SampleRecordsTests(unittest.TestCase):
    def test_sampling_is_deterministic(self) -> None:
        records = [_batch_row(i) for i in range(20)]

        first = export_manual_eval_sample.sample_records(records, 5, seed=42)
        second = export_manual_eval_sample.sample_records(records, 5, seed=42)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 5)

    def test_sample_size_larger_than_population_returns_all_records(self) -> None:
        records = [_batch_row(i) for i in range(3)]

        sampled = export_manual_eval_sample.sample_records(records, 10, seed=42)

        self.assertEqual(sampled, records)

    def test_zero_sample_size_returns_empty(self) -> None:
        records = [_batch_row(i) for i in range(3)]

        self.assertEqual(export_manual_eval_sample.sample_records(records, 0, seed=42), [])


class RowBuilderTests(unittest.TestCase):
    def test_manual_eval_row_contains_annotation_fields(self) -> None:
        row = export_manual_eval_sample.build_manual_eval_row(_batch_row(1))

        self.assertEqual(row["id"], "case-1")
        self.assertEqual(row["matched_topic"], "atrial fibrillation")
        self.assertEqual(row["matched_terms"], ["atrial fibrillation"])
        self.assertEqual(row["filter_confidence"], "high_confidence")
        self.assertIsNone(row["manual_is_cardiology_relevant"])
        self.assertIsNone(row["manual_topic_correct"])
        self.assertIsNone(row["manual_expected_topic"])
        self.assertIsNone(row["manual_notes"])

    def test_optional_fields_are_omitted_when_absent(self) -> None:
        row = export_manual_eval_sample.build_manual_eval_row(
            {
                "question": "Synthetic fallback?",
                "matched_topic": None,
                "status": "fallback",
                "answer": "No topic.",
                "graph_path": None,
            }
        )

        self.assertNotIn("id", row)
        self.assertNotIn("matched_terms", row)
        self.assertNotIn("filter_confidence", row)
        self.assertEqual(row["status"], "fallback")


class MarkdownTests(unittest.TestCase):
    def test_markdown_contains_annotation_checkboxes(self) -> None:
        rows = [export_manual_eval_sample.build_manual_eval_row(_batch_row(1))]

        markdown = export_manual_eval_sample.render_markdown(
            rows,
            input_path=Path("input.jsonl"),
            output_jsonl=Path("manual.jsonl"),
            sample_size=1,
            seed=7,
        )

        self.assertIn("# Manual Evaluation Sample", markdown)
        self.assertIn("Qualitative/manual assessment", markdown)
        self.assertIn("- [ ] Cardiology relevant: yes", markdown)
        self.assertIn("- [ ] Topic correct: no", markdown)
        self.assertIn("Expected topic:", markdown)
        self.assertIn("`atrial fibrillation`", markdown)


class ExportTests(unittest.TestCase):
    def test_export_writes_jsonl_and_markdown(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "batch.jsonl"
            output_jsonl = tmp_path / "manual" / "sample.jsonl"
            output_md = tmp_path / "manual" / "sample.md"
            _write_jsonl(input_path, [_batch_row(i) for i in range(5)])

            summary = export_manual_eval_sample.export_manual_eval_sample(
                input_path=input_path,
                output_jsonl=output_jsonl,
                output_md=output_md,
                sample_size=3,
                seed=42,
            )

            self.assertEqual(summary["input_records"], 5)
            self.assertEqual(summary["sampled_records"], 3)
            self.assertTrue(output_jsonl.exists())
            self.assertTrue(output_md.exists())
            rows = _read_jsonl(output_jsonl)
            self.assertEqual(len(rows), 3)
            self.assertIn("manual_notes", rows[0])
            self.assertIn("Manual Evaluation Sample", output_md.read_text(encoding="utf-8"))


class MainTests(unittest.TestCase):
    def test_main_prints_summary(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "batch.jsonl"
            output_jsonl = tmp_path / "sample.jsonl"
            output_md = tmp_path / "sample.md"
            _write_jsonl(input_path, [_batch_row(i) for i in range(2)])

            out = io.StringIO()
            with redirect_stdout(out):
                exit_code = export_manual_eval_sample.main(
                    [
                        "--input", str(input_path),
                        "--output-jsonl", str(output_jsonl),
                        "--output-md", str(output_md),
                        "--sample-size", "1",
                        "--seed", "3",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("Sampled records: 1", out.getvalue())
            self.assertTrue(output_jsonl.exists())
            self.assertTrue(output_md.exists())

    def test_main_reports_missing_input(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                exit_code = export_manual_eval_sample.main(
                    [
                        "--input", str(tmp_path / "missing.jsonl"),
                        "--output-jsonl", str(tmp_path / "sample.jsonl"),
                        "--output-md", str(tmp_path / "sample.md"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("File not found", err.getvalue())


class ScriptInvocationTests(unittest.TestCase):
    def test_script_invocation(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "batch.jsonl"
            output_jsonl = tmp_path / "sample.jsonl"
            output_md = tmp_path / "sample.md"
            _write_jsonl(input_path, [_batch_row(i) for i in range(4)])

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input", str(input_path),
                    "--output-jsonl", str(output_jsonl),
                    "--output-md", str(output_md),
                    "--sample-size", "2",
                    "--seed", "9",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("Sampled records: 2", result.stdout)
            self.assertEqual(len(_read_jsonl(output_jsonl)), 2)
            self.assertIn("Manual Evaluation Sample", output_md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
