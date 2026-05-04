"""Tests for the ``audit_batch_results.py`` CLI script.

These tests use synthetic in-memory JSONL fixtures only — no real MedQA data
is involved.
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

import audit_batch_results


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "audit_batch_results.py"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record) + "\n")


def _matched_row(
    topic,
    *,
    rid,
    question="What causes …?",
    answer="An answer.",
    graph=None,
    matched_terms=None,
):
    return {
        "id": rid,
        "question": question,
        "matched_topic": topic,
        "answer": answer,
        "explanation": "",
        "reasoning_path": [],
        "graph_path": graph,
        "matched_terms": matched_terms,
        "status": "matched",
    }


def _fallback_row(*, rid, question="?"):
    return {
        "id": rid,
        "question": question,
        "matched_topic": None,
        "answer": "I could not find a matching cardiology topic …",
        "explanation": "",
        "reasoning_path": [],
        "graph_path": None,
        "status": "fallback",
    }


class RunAuditTests(unittest.TestCase):
    def test_writes_audit_report_with_expected_counts(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            output_path = tmp_path / "out.md"
            records = [
                _matched_row("angina", rid=f"m{i}", graph=f"g{i}.json")
                for i in range(8)
            ] + [_fallback_row(rid=f"f{i}") for i in range(2)]
            _write_jsonl(input_path, records)

            summary = audit_batch_results.run_audit(
                input_path=input_path,
                output_path=output_path,
                sample_size=5,
                seed=42,
            )

            self.assertEqual(summary["total_records"], 10)
            self.assertEqual(summary["matched"], 8)
            self.assertEqual(summary["fallback"], 2)
            self.assertEqual(summary["sampled_matched"], 5)
            # Fallback bucket only has 2 records; sampler caps at population.
            self.assertEqual(summary["sampled_fallback"], 2)

            md = output_path.read_text(encoding="utf-8")
            self.assertIn("# OPM Medical QA — Batch Results Audit", md)
            self.assertIn("| Total records | 10 |", md)
            self.assertIn("| Matched | 8 |", md)
            self.assertIn("| Fallback | 2 |", md)
            self.assertIn("| angina | 8 | 100.0% |", md)

    def test_sampled_records_show_matched_terms(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            output_path = tmp_path / "out.md"
            _write_jsonl(
                input_path,
                [
                    _matched_row(
                        "angina",
                        rid="m1",
                        matched_terms=["angina", "coronary"],
                    )
                ],
            )

            audit_batch_results.run_audit(
                input_path=input_path,
                output_path=output_path,
                sample_size=5,
                seed=42,
            )

            md = output_path.read_text(encoding="utf-8")
            self.assertIn("**Matched terms:** `angina`, `coronary`", md)

    def test_dominance_warning_triggered_above_40_percent(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            output_path = tmp_path / "out.md"
            # 6 angina, 2 hypertension, 2 arrhythmia → angina is 60%.
            records = (
                [_matched_row("angina", rid=f"a{i}") for i in range(6)]
                + [_matched_row("hypertension", rid=f"h{i}") for i in range(2)]
                + [_matched_row("arrhythmia", rid=f"r{i}") for i in range(2)]
            )
            _write_jsonl(input_path, records)

            summary = audit_batch_results.run_audit(
                input_path=input_path,
                output_path=output_path,
                sample_size=5,
                seed=42,
            )

            self.assertIsNotNone(summary["dominance"])
            topic, share = summary["dominance"]
            self.assertEqual(topic, "angina")
            self.assertAlmostEqual(share, 0.6, places=2)

            md = output_path.read_text(encoding="utf-8")
            self.assertIn("⚠", md)
            self.assertIn("**angina**", md)

    def test_no_dominance_warning_when_balanced(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            output_path = tmp_path / "out.md"
            records = [
                _matched_row("angina", rid="a1"),
                _matched_row("hypertension", rid="h1"),
                _matched_row("arrhythmia", rid="r1"),
            ]
            _write_jsonl(input_path, records)

            summary = audit_batch_results.run_audit(
                input_path=input_path,
                output_path=output_path,
                sample_size=5,
                seed=42,
            )

            self.assertIsNone(summary["dominance"])
            md = output_path.read_text(encoding="utf-8")
            self.assertIn("No single matched topic exceeds the 40% threshold", md)
            self.assertNotIn("⚠", md)

    def test_sampling_is_deterministic_for_fixed_seed(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            records = [_matched_row("angina", rid=f"r{i:03d}") for i in range(50)]
            _write_jsonl(input_path, records)

            audit_batch_results.run_audit(
                input_path=input_path,
                output_path=tmp_path / "out1.md",
                sample_size=5,
                seed=42,
            )
            audit_batch_results.run_audit(
                input_path=input_path,
                output_path=tmp_path / "out2.md",
                sample_size=5,
                seed=42,
            )
            self.assertEqual(
                (tmp_path / "out1.md").read_text(encoding="utf-8"),
                (tmp_path / "out2.md").read_text(encoding="utf-8"),
            )

    def test_different_seeds_change_sampled_records(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            records = [_matched_row("angina", rid=f"r{i:03d}") for i in range(50)]
            _write_jsonl(input_path, records)

            audit_batch_results.run_audit(
                input_path=input_path,
                output_path=tmp_path / "out1.md",
                sample_size=5,
                seed=1,
            )
            audit_batch_results.run_audit(
                input_path=input_path,
                output_path=tmp_path / "out2.md",
                sample_size=5,
                seed=2,
            )
            # Reports differ because their sampled record IDs differ.
            self.assertNotEqual(
                (tmp_path / "out1.md").read_text(encoding="utf-8"),
                (tmp_path / "out2.md").read_text(encoding="utf-8"),
            )

    def test_empty_input_renders_friendly_messages(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            input_path.write_text("", encoding="utf-8")

            summary = audit_batch_results.run_audit(
                input_path=input_path,
                output_path=tmp_path / "out.md",
                sample_size=5,
                seed=42,
            )
            self.assertEqual(summary["total_records"], 0)
            md = (tmp_path / "out.md").read_text(encoding="utf-8")
            self.assertIn("| Total records | 0 |", md)
            self.assertIn("| Match rate | n/a |", md)
            self.assertIn("_No matched topics._", md)

    def test_negative_sample_size_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(input_path, [_matched_row("angina", rid="a1")])

            with self.assertRaises(ValueError):
                audit_batch_results.run_audit(
                    input_path=input_path,
                    output_path=tmp_path / "out.md",
                    sample_size=-1,
                    seed=42,
                )


class MainTests(unittest.TestCase):
    def test_main_writes_report_and_prints_summary(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            output_path = tmp_path / "out.md"
            _write_jsonl(
                input_path,
                [_matched_row("angina", rid="a1"), _fallback_row(rid="f1")],
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = audit_batch_results.main(
                    [
                        "--input", str(input_path),
                        "--output", str(output_path),
                        "--sample-size", "5",
                        "--seed", "7",
                    ]
                )

            self.assertEqual(exit_code, 0)
            stdout = buffer.getvalue()
            self.assertIn("Read 2 records from:", stdout)
            self.assertIn("Matched: 1", stdout)
            self.assertIn("Fallback: 1", stdout)
            self.assertIn(f"Wrote audit report to: {output_path}", stdout)
            self.assertTrue(output_path.exists())

    def test_main_prints_dominance_warning_to_stdout(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(
                input_path,
                [_matched_row("angina", rid=f"a{i}") for i in range(8)]
                + [_matched_row("arrhythmia", rid="r1"), _matched_row("arrhythmia", rid="r2")],
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                audit_batch_results.main(
                    ["--input", str(input_path), "--output", str(tmp_path / "out.md")]
                )

            stdout = buffer.getvalue()
            self.assertIn("Topic dominance", stdout)
            self.assertIn("angina", stdout)

    def test_main_reports_missing_input(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                exit_code = audit_batch_results.main(
                    [
                        "--input", str(tmp_path / "missing.jsonl"),
                        "--output", str(tmp_path / "out.md"),
                    ]
                )
            self.assertEqual(exit_code, 1)
            self.assertIn("File not found", err.getvalue())

    def test_main_rejects_negative_sample_size(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(input_path, [_matched_row("angina", rid="a1")])

            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                exit_code = audit_batch_results.main(
                    [
                        "--input", str(input_path),
                        "--output", str(tmp_path / "out.md"),
                        "--sample-size", "-1",
                    ]
                )
            self.assertEqual(exit_code, 2)


class ScriptInvocationTests(unittest.TestCase):
    def test_script_runs_against_synthetic_jsonl(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            output_path = tmp_path / "out.md"
            _write_jsonl(
                input_path,
                [_matched_row("angina", rid="a1"), _fallback_row(rid="f1")],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input", str(input_path),
                    "--output", str(output_path),
                    "--sample-size", "5",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("Wrote audit report to:", result.stdout)
            self.assertTrue(output_path.exists())
            self.assertIn(
                "# OPM Medical QA — Batch Results Audit",
                output_path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
