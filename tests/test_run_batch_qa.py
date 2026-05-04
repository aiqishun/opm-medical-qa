"""Tests for the ``run_batch_qa.py`` CLI script."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import run_batch_qa


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KB = PROJECT_ROOT / "data" / "processed" / "cardiology_knowledge.json"
BUNDLED_INPUT = PROJECT_ROOT / "data" / "processed" / "medqa_cardiology_sample.jsonl"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_batch_qa.py"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class SafeFilenameStemTests(unittest.TestCase):
    def test_uses_id_when_present(self) -> None:
        self.assertEqual(run_batch_qa._safe_filename_stem("med_qa_001", 0), "med_qa_001")

    def test_sanitizes_id_special_characters(self) -> None:
        self.assertEqual(
            run_batch_qa._safe_filename_stem("MedQA / case 12!", 0),
            "MedQA_case_12",
        )

    def test_falls_back_to_index_when_id_missing(self) -> None:
        self.assertEqual(run_batch_qa._safe_filename_stem(None, 7), "q0007")

    def test_falls_back_to_index_when_id_sanitizes_to_empty(self) -> None:
        self.assertEqual(run_batch_qa._safe_filename_stem("///", 3), "q0003")

    def test_truncates_long_ids(self) -> None:
        long_id = "x" * 200
        stem = run_batch_qa._safe_filename_stem(long_id, 0)
        self.assertEqual(len(stem), 80)


class RunBatchTests(unittest.TestCase):
    def test_happy_path_writes_results_and_graphs(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            output_path = tmp_path / "results.jsonl"
            graphs_dir = tmp_path / "graphs"
            _write_jsonl(
                input_path,
                [
                    {
                        "id": "case-001",
                        "question": "What causes myocardial infarction?",
                        "matched_terms": ["myocardial infarction"],
                        "filter_confidence": "high_confidence",
                    },
                    {
                        "id": "case-002",
                        "question": "What causes hypertension?",
                    },
                ],
            )

            summary = run_batch_qa.run_batch(
                input_path=input_path,
                output_path=output_path,
                graphs_dir=graphs_dir,
                knowledge_base_path=DEFAULT_KB,
            )

            self.assertEqual(summary.total_records, 2)
            self.assertEqual(summary.matched, 2)
            self.assertEqual(summary.fallback, 0)
            self.assertEqual(summary.skipped_missing_question, 0)

            results = _read_jsonl(output_path)
            self.assertEqual(len(results), 2)

            first = results[0]
            self.assertEqual(first["id"], "case-001")
            self.assertEqual(first["matched_topic"], "myocardial infarction")
            self.assertEqual(first["status"], "matched")
            self.assertGreater(first["match_score"], 0)
            self.assertEqual(first["matched_terms"], ["myocardial infarction"])
            self.assertEqual(first["filter_confidence"], "high_confidence")
            self.assertEqual(first["graph_path"], str(graphs_dir / "case-001.json"))
            self.assertTrue(Path(first["graph_path"]).exists())
            self.assertEqual(
                first["reasoning_path"],
                [
                    "Atherosclerosis",
                    "Coronary artery blockage",
                    "Reduced blood flow",
                    "Myocardial infarction",
                ],
            )

            graph_payload = json.loads(Path(first["graph_path"]).read_text("utf-8"))
            self.assertIn("Coronary artery", graph_payload["objects"])

    def test_records_without_id_get_indexed_filenames(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            output_path = tmp_path / "results.jsonl"
            graphs_dir = tmp_path / "graphs"
            _write_jsonl(
                input_path,
                [
                    {"question": "What causes myocardial infarction?"},
                    {"question": "What causes hypertension?"},
                ],
            )

            run_batch_qa.run_batch(
                input_path=input_path,
                output_path=output_path,
                graphs_dir=graphs_dir,
                knowledge_base_path=DEFAULT_KB,
            )

            results = _read_jsonl(output_path)
            self.assertIsNone(results[0]["id"])
            self.assertEqual(Path(results[0]["graph_path"]).name, "q0000.json")
            self.assertEqual(Path(results[1]["graph_path"]).name, "q0001.json")
            self.assertIn("match_score", results[0])

    def test_unmatched_record_has_null_graph_path_and_fallback_status(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            output_path = tmp_path / "results.jsonl"
            graphs_dir = tmp_path / "graphs"
            _write_jsonl(
                input_path,
                [
                    {"id": "off-topic", "question": "How do glaciers form?"},
                    {"id": "cardio", "question": "What causes hypertension?"},
                ],
            )

            summary = run_batch_qa.run_batch(
                input_path=input_path,
                output_path=output_path,
                graphs_dir=graphs_dir,
                knowledge_base_path=DEFAULT_KB,
            )

            results = _read_jsonl(output_path)
            self.assertEqual(summary.matched, 1)
            self.assertEqual(summary.fallback, 1)
            self.assertEqual(results[0]["status"], "fallback")
            self.assertIsNone(results[0]["graph_path"])
            self.assertEqual(results[0]["matched_topic"], None)
            self.assertEqual(results[0]["match_score"], 0)
            self.assertEqual(results[1]["status"], "matched")
            self.assertFalse((graphs_dir / "off-topic.json").exists())
            self.assertTrue((graphs_dir / "cardio.json").exists())

    def test_records_without_question_are_skipped(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            output_path = tmp_path / "results.jsonl"
            graphs_dir = tmp_path / "graphs"
            _write_jsonl(
                input_path,
                [
                    {"id": "no-question"},
                    {"id": "blank", "question": "   "},
                    {"id": "wrong-type", "question": 123},
                    {"id": "ok", "question": "What causes hypertension?"},
                ],
            )

            summary = run_batch_qa.run_batch(
                input_path=input_path,
                output_path=output_path,
                graphs_dir=graphs_dir,
                knowledge_base_path=DEFAULT_KB,
            )

            self.assertEqual(summary.total_records, 4)
            self.assertEqual(summary.skipped_missing_question, 3)
            self.assertEqual(summary.matched, 1)

            results = _read_jsonl(output_path)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["id"], "ok")

    def test_run_batch_exports_mermaid_when_mermaid_dir_given(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            output_path = tmp_path / "results.jsonl"
            graphs_dir = tmp_path / "graphs"
            mermaid_dir = tmp_path / "mermaid"
            _write_jsonl(
                input_path,
                [
                    {"id": "mi-001", "question": "What causes myocardial infarction?"},
                    {"id": "fallback", "question": "How do glaciers form?"},
                ],
            )

            summary = run_batch_qa.run_batch(
                input_path=input_path,
                output_path=output_path,
                graphs_dir=graphs_dir,
                knowledge_base_path=DEFAULT_KB,
                mermaid_dir=mermaid_dir,
            )

            self.assertEqual(summary.mermaid_dir, mermaid_dir)
            results = _read_jsonl(output_path)
            matched = next(r for r in results if r["status"] == "matched")
            fallback = next(r for r in results if r["status"] == "fallback")

            self.assertIsNotNone(matched["mermaid_path"])
            mmd = Path(matched["mermaid_path"])
            self.assertTrue(mmd.exists())
            self.assertEqual(mmd.suffix, ".mmd")
            self.assertIn("flowchart TD", mmd.read_text(encoding="utf-8"))
            self.assertIsNone(fallback["mermaid_path"])

    def test_run_batch_no_mermaid_when_mermaid_dir_not_given(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            _write_jsonl(input_path, [{"question": "What causes hypertension?"}])

            summary = run_batch_qa.run_batch(
                input_path=input_path,
                output_path=tmp_path / "results.jsonl",
                graphs_dir=tmp_path / "graphs",
                knowledge_base_path=DEFAULT_KB,
            )

            self.assertIsNone(summary.mermaid_dir)
            results = _read_jsonl(tmp_path / "results.jsonl")
            self.assertNotIn("mermaid_path", results[0])

    def test_empty_input_writes_empty_results_and_no_graphs(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            output_path = tmp_path / "results.jsonl"
            graphs_dir = tmp_path / "graphs"
            input_path.write_text("", encoding="utf-8")

            summary = run_batch_qa.run_batch(
                input_path=input_path,
                output_path=output_path,
                graphs_dir=graphs_dir,
                knowledge_base_path=DEFAULT_KB,
            )

            self.assertEqual(summary.total_records, 0)
            self.assertEqual(summary.matched, 0)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "")
            self.assertFalse(graphs_dir.exists())


class MainTests(unittest.TestCase):
    def test_main_runs_against_bundled_sample(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_path = tmp_path / "results.jsonl"
            graphs_dir = tmp_path / "graphs"

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = run_batch_qa.main(
                    [
                        "--input",
                        str(BUNDLED_INPUT),
                        "--output",
                        str(output_path),
                        "--graphs-dir",
                        str(graphs_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            stdout = buffer.getvalue()
            # Bundled processed sample: 16 cardiology records — 14 supported
            # topics + 2 cardiology-adjacent fallback questions.
            self.assertIn(f"Read 16 records from: {BUNDLED_INPUT}", stdout)
            self.assertIn("Matched: 14", stdout)
            self.assertIn("Fallback: 2", stdout)
            self.assertIn(f"Wrote results to: {output_path}", stdout)
            results = _read_jsonl(output_path)
            self.assertEqual(len(results), 16)
            matched = [r for r in results if r["status"] == "matched"]
            fallback = [r for r in results if r["status"] == "fallback"]
            self.assertEqual(len(matched), 14)
            self.assertEqual(len(fallback), 2)
            self.assertIn("match_score", results[0])
            self.assertIn("matched_terms", results[0])
            self.assertIn("filter_confidence", results[0])

    def test_main_reports_missing_input(self) -> None:
        with TemporaryDirectory() as tmp:
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                exit_code = run_batch_qa.main(
                    [
                        "--input",
                        str(Path(tmp) / "missing.jsonl"),
                        "--output",
                        str(Path(tmp) / "out.jsonl"),
                        "--graphs-dir",
                        str(Path(tmp) / "graphs"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("File not found", err.getvalue())

    def test_main_reports_invalid_jsonl(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            input_path.write_text(
                '{"question": "ok"}\n{not valid}\n',
                encoding="utf-8",
            )

            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                exit_code = run_batch_qa.main(
                    [
                        "--input",
                        str(input_path),
                        "--output",
                        str(tmp_path / "out.jsonl"),
                        "--graphs-dir",
                        str(tmp_path / "graphs"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("Invalid JSON", err.getvalue())
            self.assertIn("line 2", err.getvalue())

    def test_main_writes_summary_when_requested(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            output_path = tmp_path / "results.jsonl"
            graphs_dir = tmp_path / "graphs"
            summary_path = tmp_path / "reports" / "summary.md"
            _write_jsonl(
                input_path,
                [
                    {"question": "What causes hypertension?"},
                    {"question": "How do glaciers form?"},
                ],
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = run_batch_qa.main(
                    [
                        "--input",
                        str(input_path),
                        "--output",
                        str(output_path),
                        "--graphs-dir",
                        str(graphs_dir),
                        "--summary",
                        str(summary_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn(
                f"Wrote summary report to: {summary_path}", buffer.getvalue()
            )
            self.assertTrue(summary_path.exists())

            text = summary_path.read_text(encoding="utf-8")
            self.assertIn("# OPM Medical QA — Batch Summary", text)
            self.assertIn("| Matched | 1 |", text)
            self.assertIn("| Fallback | 1 |", text)
            self.assertIn("| hypertension | 1 |", text)
            self.assertIn("- How do glaciers form?", text)

    def test_main_exports_mermaid_diagrams_when_requested(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            output_path = tmp_path / "results.jsonl"
            graphs_dir = tmp_path / "graphs"
            mermaid_dir = tmp_path / "mermaid"
            _write_jsonl(
                input_path,
                [
                    {"id": "case-001", "question": "What causes hypertension?"},
                    {"id": "case-002", "question": "How do glaciers form?"},
                ],
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = run_batch_qa.main(
                    [
                        "--input", str(input_path),
                        "--output", str(output_path),
                        "--graphs-dir", str(graphs_dir),
                        "--mermaid-dir", str(mermaid_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            stdout = buffer.getvalue()
            self.assertIn(f"Exported Mermaid diagrams to: {mermaid_dir}", stdout)

            results = _read_jsonl(output_path)
            matched = [r for r in results if r["status"] == "matched"]
            fallback = [r for r in results if r["status"] == "fallback"]

            self.assertEqual(len(matched), 1)
            self.assertIsNotNone(matched[0]["mermaid_path"])
            mmd_path = Path(matched[0]["mermaid_path"])
            self.assertTrue(mmd_path.exists())
            self.assertIn("flowchart TD", mmd_path.read_text(encoding="utf-8"))

            self.assertIsNone(fallback[0]["mermaid_path"])

    def test_main_mermaid_dir_result_has_mermaid_path_field(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            _write_jsonl(input_path, [{"id": "q1", "question": "What causes hypertension?"}])

            with redirect_stdout(io.StringIO()):
                run_batch_qa.main(
                    [
                        "--input", str(input_path),
                        "--output", str(tmp_path / "out.jsonl"),
                        "--graphs-dir", str(tmp_path / "graphs"),
                        "--mermaid-dir", str(tmp_path / "mermaid"),
                    ]
                )

            results = _read_jsonl(tmp_path / "out.jsonl")
            self.assertIn("mermaid_path", results[0])

    def test_main_without_mermaid_dir_has_no_mermaid_path_field(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            _write_jsonl(input_path, [{"question": "What causes hypertension?"}])

            with redirect_stdout(io.StringIO()):
                run_batch_qa.main(
                    [
                        "--input", str(input_path),
                        "--output", str(tmp_path / "out.jsonl"),
                        "--graphs-dir", str(tmp_path / "graphs"),
                    ]
                )

            results = _read_jsonl(tmp_path / "out.jsonl")
            self.assertNotIn("mermaid_path", results[0])

    def test_main_mermaid_filenames_match_graph_stems(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            _write_jsonl(input_path, [{"id": "mi-001", "question": "What causes myocardial infarction?"}])

            with redirect_stdout(io.StringIO()):
                run_batch_qa.main(
                    [
                        "--input", str(input_path),
                        "--output", str(tmp_path / "out.jsonl"),
                        "--graphs-dir", str(tmp_path / "graphs"),
                        "--mermaid-dir", str(tmp_path / "mermaid"),
                    ]
                )

            results = _read_jsonl(tmp_path / "out.jsonl")
            self.assertEqual(Path(results[0]["graph_path"]).stem, "mi-001")
            self.assertEqual(Path(results[0]["mermaid_path"]).stem, "mi-001")

    def test_main_without_summary_does_not_write_report(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            output_path = tmp_path / "results.jsonl"
            graphs_dir = tmp_path / "graphs"
            _write_jsonl(input_path, [{"question": "What causes hypertension?"}])

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = run_batch_qa.main(
                    [
                        "--input",
                        str(input_path),
                        "--output",
                        str(output_path),
                        "--graphs-dir",
                        str(graphs_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertNotIn("summary report", buffer.getvalue())

    def test_main_reports_missing_knowledge_base(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "input.jsonl"
            _write_jsonl(input_path, [{"question": "What causes hypertension?"}])

            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                exit_code = run_batch_qa.main(
                    [
                        "--input",
                        str(input_path),
                        "--output",
                        str(tmp_path / "out.jsonl"),
                        "--graphs-dir",
                        str(tmp_path / "graphs"),
                        "--knowledge-base",
                        str(tmp_path / "missing-kb.json"),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("File not found", err.getvalue())


class ScriptInvocationTests(unittest.TestCase):
    def test_script_runs_against_bundled_sample(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_path = tmp_path / "results.jsonl"
            graphs_dir = tmp_path / "graphs"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input",
                    str(BUNDLED_INPUT),
                    "--output",
                    str(output_path),
                    "--graphs-dir",
                    str(graphs_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("Matched:", result.stdout)
            self.assertTrue(output_path.exists())
            results = _read_jsonl(output_path)
            self.assertEqual(len(results), 16)
            statuses = {r["status"] for r in results}
            self.assertEqual(statuses, {"matched", "fallback"})
            for record in results:
                if record["status"] == "matched":
                    self.assertTrue(Path(record["graph_path"]).exists())
                else:
                    self.assertIsNone(record["graph_path"])


if __name__ == "__main__":
    unittest.main()
