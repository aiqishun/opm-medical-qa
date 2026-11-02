"""Tests for the ``run_qa.py`` CLI script."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import run_qa


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KB = PROJECT_ROOT / "data" / "processed" / "cardiology_knowledge.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_qa.py"


class RunQAFunctionTests(unittest.TestCase):
    def test_run_returns_formatted_text_for_known_question(self) -> None:
        output = run_qa.run("What causes myocardial infarction?", DEFAULT_KB)

        self.assertIn("answer:", output)
        self.assertIn("myocardial infarction", output.lower())
        self.assertIn("OPM objects:", output)
        self.assertIn("Atherosclerosis -> Coronary artery blockage", output)

    def test_run_returns_fallback_text_for_unknown_question(self) -> None:
        output = run_qa.run("How do volcanoes form?", DEFAULT_KB)

        self.assertIn("could not find a matching cardiology topic", output)
        self.assertIn("(no reasoning path found)", output)


class MainTests(unittest.TestCase):
    def test_main_prints_answer_and_returns_zero(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = run_qa.main(
                [
                    "--question",
                    "What causes hypertension?",
                    "--knowledge-base",
                    str(DEFAULT_KB),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("hypertension", buffer.getvalue().lower())

    def test_main_reports_missing_knowledge_base(self) -> None:
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            err = io.StringIO()
            out = io.StringIO()
            with redirect_stderr(err), redirect_stdout(out):
                exit_code = run_qa.main(
                    ["--question", "Anything?", "--knowledge-base", str(missing)]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("File not found", err.getvalue())
        self.assertEqual(out.getvalue(), "")

    def test_main_reports_invalid_json(self) -> None:
        with TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken.json"
            broken.write_text("{not json", encoding="utf-8")

            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                exit_code = run_qa.main(
                    ["--question", "Anything?", "--knowledge-base", str(broken)]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("Invalid JSON", err.getvalue())

    def test_main_exports_graph_when_requested(self) -> None:
        with TemporaryDirectory() as tmp:
            export_path = Path(tmp) / "nested" / "graph.json"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = run_qa.main(
                    [
                        "--question",
                        "What causes myocardial infarction?",
                        "--knowledge-base",
                        str(DEFAULT_KB),
                        "--export-graph",
                        str(export_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn(f"Graph exported to: {export_path}", buffer.getvalue())
            self.assertTrue(export_path.exists())

            payload = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertIn("Coronary artery", payload["objects"])
            self.assertTrue(
                any(link["target"] == "Plaque build-up" for link in payload["links"])
            )

    def test_main_exports_mermaid_when_requested(self) -> None:
        with TemporaryDirectory() as tmp:
            mermaid_path = Path(tmp) / "nested" / "graph.mmd"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = run_qa.main(
                    [
                        "--question",
                        "What causes myocardial infarction?",
                        "--knowledge-base",
                        str(DEFAULT_KB),
                        "--export-mermaid",
                        str(mermaid_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn(f"Mermaid diagram exported to: {mermaid_path}", buffer.getvalue())
            self.assertTrue(mermaid_path.exists())
            text = mermaid_path.read_text(encoding="utf-8")
            self.assertIn("flowchart TD", text)
            self.assertIn("Coronary artery", text)

    def test_main_exports_both_graph_and_mermaid_when_both_flags_given(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graph_path = tmp_path / "graph.json"
            mermaid_path = tmp_path / "graph.mmd"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = run_qa.main(
                    [
                        "--question",
                        "What causes myocardial infarction?",
                        "--knowledge-base",
                        str(DEFAULT_KB),
                        "--export-graph",
                        str(graph_path),
                        "--export-mermaid",
                        str(mermaid_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(graph_path.exists())
            self.assertTrue(mermaid_path.exists())
            stdout = buffer.getvalue()
            self.assertIn(f"Graph exported to: {graph_path}", stdout)
            self.assertIn(f"Mermaid diagram exported to: {mermaid_path}", stdout)

    def test_main_without_export_flag_does_not_change_stdout(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = run_qa.main(
                [
                    "--question",
                    "What causes myocardial infarction?",
                    "--knowledge-base",
                    str(DEFAULT_KB),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertNotIn("Graph exported to", buffer.getvalue())

    def test_main_reports_export_error(self) -> None:
        with TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker"
            blocker.write_text("not a directory", encoding="utf-8")
            export_path = blocker / "graph.json"

            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                exit_code = run_qa.main(
                    [
                        "--question",
                        "What causes myocardial infarction?",
                        "--knowledge-base",
                        str(DEFAULT_KB),
                        "--export-graph",
                        str(export_path),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertTrue(err.getvalue().startswith("error:"))


class ScriptInvocationTests(unittest.TestCase):
    """End-to-end test invoking the script as a subprocess."""

    def test_script_runs_and_prints_demo_output(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--question",
                "What causes myocardial infarction?",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("answer:", result.stdout)
        self.assertIn("OPM links:", result.stdout)

    def test_script_export_graph_flag(self) -> None:
        with TemporaryDirectory() as tmp:
            export_path = Path(tmp) / "outputs" / "graphs" / "mi.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--question",
                    "What causes myocardial infarction?",
                    "--export-graph",
                    str(export_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("answer:", result.stdout)
            self.assertIn(f"Graph exported to: {export_path}", result.stdout)
            self.assertTrue(export_path.exists())
            payload = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(set(payload), {"objects", "processes", "states", "links"})

    def test_script_uses_custom_knowledge_base(self) -> None:
        with TemporaryDirectory() as tmp:
            kb = Path(tmp) / "kb.json"
            kb.write_text(
                json.dumps(
                    {
                        "topics": [
                            {
                                "name": "test topic",
                                "question_patterns": ["What causes test?"],
                                "keywords": ["test"],
                                "answer": "Test answer.",
                                "explanation": "Test explanation.",
                                "reasoning_path": ["A", "B"],
                                "opm_objects": ["O"],
                                "opm_processes": ["P"],
                                "opm_states": ["S"],
                                "opm_links": [
                                    {"source": "A", "relationship": "x", "target": "B"}
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--question",
                    "What causes test?",
                    "--knowledge-base",
                    str(kb),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("Test answer.", result.stdout)


if __name__ == "__main__":
    unittest.main()
