"""Tests for the automatic OPM graph evaluation script."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "evaluate_opm_graphs_auto.py"

spec = importlib.util.spec_from_file_location("evaluate_opm_graphs_auto", SCRIPT_PATH)
evaluate_opm_graphs_auto = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(evaluate_opm_graphs_auto)


def _valid_graph() -> dict:
    return {
        "objects": ["Heart"],
        "processes": ["Blood pumping"],
        "states": ["Perfused tissue"],
        "links": [
            {
                "source": "Heart",
                "relationship": "object participates in process",
                "target": "Blood pumping",
            },
            {
                "source": "Blood pumping",
                "relationship": "process changes state",
                "target": "Perfused tissue",
            },
            {
                "source": "Perfused tissue",
                "relationship": "state contributes to outcome",
                "target": "Cardiac output",
            },
        ],
    }


def _result_row(graph_path: str = "graphs/g1.json") -> dict:
    return {
        "question": "How does the heart support blood pumping?",
        "answer": "Heart blood pumping supports cardiac output.",
        "explanation": "Blood pumping creates perfused tissue.",
        "reasoning_path": ["Heart", "Blood pumping", "Perfused tissue"],
        "matched_topic": "cardiac output",
        "graph_path": graph_path,
        "status": "matched",
    }


class NormalizeTextTests(unittest.TestCase):
    def test_lowercases_removes_punctuation_and_strips(self) -> None:
        self.assertEqual(
            evaluate_opm_graphs_auto.normalize_text("  Heart, Blood-Flow! "),
            "heart blood flow",
        )


class EvaluateGraphTests(unittest.TestCase):
    def test_valid_graph_scores_core_metrics_as_one(self) -> None:
        metrics = evaluate_opm_graphs_auto.evaluate_graph(
            _valid_graph(),
            _result_row(),
        )

        self.assertEqual(metrics["node_validity_rate"], 1.0)
        self.assertEqual(metrics["edge_validity_rate"], 1.0)
        self.assertEqual(metrics["valid_graph_rate"], 1.0)
        self.assertEqual(metrics["process_object_connectivity_rate"], 1.0)
        self.assertEqual(metrics["state_object_attachment_rate"], 1.0)
        self.assertEqual(metrics["valid_type_transition_rate"], 1.0)
        self.assertEqual(metrics["explanation_path_rate"], 1.0)
        self.assertEqual(metrics["path_support_rate"], 1.0)
        self.assertGreater(metrics["answer_concept_coverage"], 0.0)

    def test_detects_duplicate_and_isolated_nodes(self) -> None:
        graph = _valid_graph()
        graph["objects"] = ["Heart", "Heart", "Unused object"]

        metrics = evaluate_opm_graphs_auto.evaluate_graph(graph, _result_row())

        self.assertGreater(metrics["duplicate_node_ratio"], 0.0)
        self.assertGreater(metrics["isolated_node_ratio"], 0.0)


class RunEvaluationTests(unittest.TestCase):
    def test_run_evaluation_writes_csv_and_summary(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            graphs_dir = tmp_path / "graphs"
            graphs_dir.mkdir()
            graph_path = graphs_dir / "g1.json"
            graph_path.write_text(json.dumps(_valid_graph()), encoding="utf-8")

            results_path = tmp_path / "results.jsonl"
            results_path.write_text(
                json.dumps(_result_row(str(graph_path))) + "\n",
                encoding="utf-8",
            )
            output_csv = tmp_path / "metrics.csv"
            summary_path = tmp_path / "summary.md"

            result = evaluate_opm_graphs_auto.run_evaluation(
                results_path=results_path,
                graphs_dir=graphs_dir,
                output_csv=output_csv,
                summary_path=summary_path,
            )

            self.assertEqual(result["metadata"]["graph_files_evaluated"], 1)
            self.assertTrue(output_csv.exists())
            self.assertTrue(summary_path.exists())
            self.assertIn("valid_graph_rate", output_csv.read_text(encoding="utf-8"))
            self.assertIn(
                "OPM Auto Evaluation Summary",
                summary_path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
