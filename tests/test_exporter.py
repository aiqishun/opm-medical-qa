"""Tests for the OPM graph JSON exporter."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from graph.exporter import GraphExportError, export_graph
from graph.opm_graph import OPMGraph, OPMLink


def _sample_graph() -> OPMGraph:
    return OPMGraph(
        objects=["Heart"],
        processes=["Beating"],
        states=["Healthy"],
        links=[OPMLink("Heart", "performs", "Beating")],
    )


class ExportGraphTests(unittest.TestCase):
    def test_writes_expected_json_payload(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"

            returned = export_graph(_sample_graph(), path)

            self.assertEqual(returned, path)
            self.assertTrue(path.exists())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload, _sample_graph().to_dict())

    def test_creates_missing_parent_directories(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "deeply" / "nested" / "dir" / "graph.json"

            export_graph(_sample_graph(), path)

            self.assertTrue(path.exists())

    def test_overwrites_existing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"
            path.write_text("stale", encoding="utf-8")

            export_graph(_sample_graph(), path)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["objects"], ["Heart"])

    def test_empty_graph_round_trips(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.json"

            export_graph(OPMGraph(), path)

            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"objects": [], "processes": [], "states": [], "links": []},
            )

    def test_indent_is_configurable(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"

            export_graph(_sample_graph(), path, indent=4)

            text = path.read_text(encoding="utf-8")
            self.assertIn('\n    "objects"', text)

    def test_does_not_leave_temp_files_behind(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"

            export_graph(_sample_graph(), path)

            leftovers = [name for name in os.listdir(tmp) if name != "graph.json"]
            self.assertEqual(leftovers, [])

    def test_unwritable_parent_raises_graph_export_error(self) -> None:
        with TemporaryDirectory() as tmp:
            blocking_file = Path(tmp) / "blocker"
            blocking_file.write_text("not a directory", encoding="utf-8")
            target = blocking_file / "graph.json"

            with self.assertRaises(GraphExportError):
                export_graph(_sample_graph(), target)


if __name__ == "__main__":
    unittest.main()
