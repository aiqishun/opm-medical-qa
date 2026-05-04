"""Tests for the ``run_baseline_comparison.py`` CLI script."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import run_baseline_comparison


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KB = PROJECT_ROOT / "data" / "processed" / "cardiology_knowledge.json"
BUNDLED_INPUT = PROJECT_ROOT / "data" / "processed" / "medqa_cardiology_sample.jsonl"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_baseline_comparison.py"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class RunComparisonTests(unittest.TestCase):
    def test_writes_jsonl_and_summary(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            output_path = tmp_path / "results.jsonl"
            summary_path = tmp_path / "summary.md"
            _write_jsonl(
                input_path,
                [
                    {"id": "a", "question": "Coronary blockage triggering an acute heart attack."},
                    {"id": "b", "question": "How do glaciers form?"},
                ],
            )

            summary = run_baseline_comparison.run_comparison(
                input_path=input_path,
                output_path=output_path,
                summary_path=summary_path,
                knowledge_base_path=DEFAULT_KB,
            )

            self.assertEqual(summary.total_records, 2)
            self.assertEqual(summary.skipped_missing_question, 0)
            results = _read_jsonl(output_path)
            self.assertEqual(len(results), 2)
            ids = {r["id"] for r in results}
            self.assertEqual(ids, {"a", "b"})
            self.assertTrue(summary_path.exists())
            self.assertIn(
                "# OPM Medical QA — Baseline Comparison",
                summary_path.read_text(encoding="utf-8"),
            )

    def test_row_shape_includes_all_comparison_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            output_path = tmp_path / "results.jsonl"
            summary_path = tmp_path / "summary.md"
            _write_jsonl(
                input_path,
                [{"id": "case-1", "question": "What causes hypertension?"}],
            )

            run_baseline_comparison.run_comparison(
                input_path=input_path,
                output_path=output_path,
                summary_path=summary_path,
                knowledge_base_path=DEFAULT_KB,
            )

            row = _read_jsonl(output_path)[0]
            self.assertEqual(
                set(row.keys()),
                {
                    "id",
                    "question",
                    "baseline_matched_topic",
                    "baseline_status",
                    "opm_matched_topic",
                    "opm_status",
                    "opm_has_reasoning_path",
                    "opm_has_graph",
                },
            )
            self.assertEqual(row["baseline_matched_topic"], "hypertension")
            self.assertEqual(row["opm_matched_topic"], "hypertension")
            self.assertTrue(row["opm_has_reasoning_path"])
            self.assertTrue(row["opm_has_graph"])

    def test_opm_fallback_has_no_path_or_graph(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(input_path, [{"id": "off", "question": "How do glaciers form?"}])

            run_baseline_comparison.run_comparison(
                input_path=input_path,
                output_path=tmp_path / "results.jsonl",
                summary_path=tmp_path / "summary.md",
                knowledge_base_path=DEFAULT_KB,
            )
            row = _read_jsonl(tmp_path / "results.jsonl")[0]
            self.assertEqual(row["opm_status"], "fallback")
            self.assertIsNone(row["opm_matched_topic"])
            self.assertFalse(row["opm_has_reasoning_path"])
            self.assertFalse(row["opm_has_graph"])

    def test_records_without_question_are_skipped(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(
                input_path,
                [
                    {"id": "missing"},
                    {"id": "blank", "question": "   "},
                    {"id": "ok", "question": "What causes hypertension?"},
                ],
            )

            summary = run_baseline_comparison.run_comparison(
                input_path=input_path,
                output_path=tmp_path / "results.jsonl",
                summary_path=tmp_path / "summary.md",
                knowledge_base_path=DEFAULT_KB,
            )

            self.assertEqual(summary.total_records, 3)
            self.assertEqual(summary.skipped_missing_question, 2)
            results = _read_jsonl(tmp_path / "results.jsonl")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["id"], "ok")

    def test_baseline_can_diverge_from_opm(self) -> None:
        # mi-001 is the canonical example — baseline matches angina (only
        # "chest pain" appears as a literal keyword), OPM matches MI thanks to
        # phrase + token scoring. We assert that divergence is captured.
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(
                input_path,
                [
                    {
                        "id": "mi-like",
                        "question": (
                            "A patient with crushing chest pain and atherosclerotic "
                            "coronary artery blockage is most consistent with which "
                            "acute event?"
                        ),
                    }
                ],
            )

            run_baseline_comparison.run_comparison(
                input_path=input_path,
                output_path=tmp_path / "results.jsonl",
                summary_path=tmp_path / "summary.md",
                knowledge_base_path=DEFAULT_KB,
            )
            row = _read_jsonl(tmp_path / "results.jsonl")[0]
            self.assertEqual(row["baseline_matched_topic"], "angina")
            self.assertEqual(row["opm_matched_topic"], "myocardial infarction")
            self.assertNotEqual(
                row["baseline_matched_topic"], row["opm_matched_topic"]
            )


class MainTests(unittest.TestCase):
    def test_main_runs_against_bundled_sample(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_path = tmp_path / "results.jsonl"
            summary_path = tmp_path / "summary.md"

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = run_baseline_comparison.main(
                    [
                        "--input", str(BUNDLED_INPUT),
                        "--output", str(output_path),
                        "--summary", str(summary_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            stdout = buffer.getvalue()
            # Bundled processed sample has 16 cardiology records.
            self.assertIn(f"Read 16 records from: {BUNDLED_INPUT}", stdout)
            self.assertIn("Baseline matched / fallback: 14 / 2", stdout)
            self.assertIn("OPM QA matched / fallback:   16 / 0", stdout)
            self.assertIn("OPM reasoning paths produced: 16", stdout)
            self.assertIn("OPM graphs produced:          16", stdout)

            results = _read_jsonl(output_path)
            self.assertEqual(len(results), 16)
            self.assertTrue(summary_path.exists())
            md = summary_path.read_text(encoding="utf-8")
            self.assertIn("| Baseline matched | 14 |", md)
            self.assertIn("| OPM QA matched | 16 |", md)

    def test_main_reports_missing_input(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                exit_code = run_baseline_comparison.main(
                    [
                        "--input", str(tmp_path / "missing.jsonl"),
                        "--output", str(tmp_path / "out.jsonl"),
                        "--summary", str(tmp_path / "summary.md"),
                    ]
                )
            self.assertEqual(exit_code, 1)
            self.assertIn("File not found", err.getvalue())

    def test_main_reports_missing_knowledge_base(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(input_path, [{"question": "What causes hypertension?"}])

            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                exit_code = run_baseline_comparison.main(
                    [
                        "--input", str(input_path),
                        "--output", str(tmp_path / "out.jsonl"),
                        "--summary", str(tmp_path / "summary.md"),
                        "--knowledge-base", str(tmp_path / "missing-kb.json"),
                    ]
                )
            self.assertEqual(exit_code, 1)
            self.assertIn("File not found", err.getvalue())


class ScriptInvocationTests(unittest.TestCase):
    def test_script_runs_against_bundled_sample(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_path = tmp_path / "results.jsonl"
            summary_path = tmp_path / "summary.md"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input", str(BUNDLED_INPUT),
                    "--output", str(output_path),
                    "--summary", str(summary_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("Baseline matched / fallback:", result.stdout)
            self.assertIn("OPM QA matched / fallback:", result.stdout)
            self.assertTrue(output_path.exists())
            self.assertTrue(summary_path.exists())
            results = _read_jsonl(output_path)
            self.assertEqual(len(results), 16)


if __name__ == "__main__":
    unittest.main()
