"""Tests for OPM graph formatting."""

from __future__ import annotations

import unittest

from graph.opm_graph import OPMGraph, OPMLink


class OPMLinkTests(unittest.TestCase):
    def test_format_renders_arrow(self) -> None:
        link = OPMLink(source="X", relationship="leads to", target="Y")
        self.assertEqual(link.format(), "X --[leads to]--> Y")

    def test_from_dict_builds_link(self) -> None:
        link = OPMLink.from_dict(
            {"source": "A", "relationship": "is part of", "target": "B"}
        )
        self.assertEqual(link.source, "A")
        self.assertEqual(link.target, "B")


class OPMGraphTests(unittest.TestCase):
    def test_empty_graph_reports_empty(self) -> None:
        self.assertTrue(OPMGraph().is_empty())

    def test_graph_with_objects_is_not_empty(self) -> None:
        graph = OPMGraph(objects=["Heart"])
        self.assertFalse(graph.is_empty())

    def test_format_as_text_includes_all_sections(self) -> None:
        graph = OPMGraph(
            objects=["Heart"],
            processes=["Beating"],
            states=["Healthy"],
            links=[OPMLink("Heart", "performs", "Beating")],
        )

        text = graph.format_as_text()

        self.assertIn("OPM objects:", text)
        self.assertIn("- Heart", text)
        self.assertIn("OPM processes:", text)
        self.assertIn("- Beating", text)
        self.assertIn("OPM states:", text)
        self.assertIn("- Healthy", text)
        self.assertIn("Heart --[performs]--> Beating", text)

    def test_format_as_text_marks_empty_sections(self) -> None:
        text = OPMGraph().format_as_text()

        self.assertIn("OPM objects:", text)
        self.assertIn("- (none)", text)

    def test_path_as_text_joins_steps(self) -> None:
        self.assertEqual(OPMGraph.path_as_text(["A", "B", "C"]), "A -> B -> C")

    def test_from_topic_parts_converts_link_dicts(self) -> None:
        graph = OPMGraph.from_topic_parts(
            objects=["O"],
            processes=["P"],
            states=["S"],
            links=[{"source": "O", "relationship": "in", "target": "P"}],
        )

        self.assertEqual(len(graph.links), 1)
        self.assertEqual(graph.links[0].relationship, "in")


if __name__ == "__main__":
    unittest.main()
