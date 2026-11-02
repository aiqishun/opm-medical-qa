"""Tests for the Mermaid flowchart exporter."""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from graph.mermaid import MermaidExportError, export_mermaid, graph_to_mermaid
from graph.opm_graph import OPMGraph, OPMLink


def _sample_graph() -> OPMGraph:
    return OPMGraph(
        objects=["Coronary artery"],
        processes=["Plaque build-up"],
        states=["Narrowed artery"],
        links=[OPMLink("Coronary artery", "object participates in process", "Plaque build-up")],
    )


class GraphToMermaidTests(unittest.TestCase):
    def test_starts_with_flowchart_header(self) -> None:
        text = graph_to_mermaid(_sample_graph())
        self.assertTrue(text.startswith("flowchart TD\n"))

    def test_ends_with_newline(self) -> None:
        self.assertTrue(graph_to_mermaid(_sample_graph()).endswith("\n"))

    def test_object_node_uses_rectangle_syntax(self) -> None:
        text = graph_to_mermaid(_sample_graph())
        self.assertIn('["Coronary artery"]', text)

    def test_process_node_uses_stadium_syntax(self) -> None:
        text = graph_to_mermaid(_sample_graph())
        self.assertIn('(["Plaque build-up"])', text)

    def test_state_node_uses_rounded_rectangle_syntax(self) -> None:
        text = graph_to_mermaid(_sample_graph())
        self.assertIn('("Narrowed artery")', text)

    def test_link_edge_is_labelled(self) -> None:
        text = graph_to_mermaid(_sample_graph())
        self.assertIn('-->|"object participates in process"|', text)

    def test_link_source_and_target_nodes_are_present(self) -> None:
        text = graph_to_mermaid(_sample_graph())
        src_id = "obj_coronary_artery"
        tgt_id = "proc_plaque_build_up"
        self.assertIn(src_id, text)
        self.assertIn(tgt_id, text)
        self.assertIn(f"{src_id} -->", text)
        self.assertIn(f"| {tgt_id}", text)

    def test_empty_graph_produces_only_header(self) -> None:
        text = graph_to_mermaid(OPMGraph())
        self.assertEqual(text, "flowchart TD\n")

    def test_double_quotes_in_names_are_escaped_to_single(self) -> None:
        graph = OPMGraph(objects=['He said "hello"'])
        text = graph_to_mermaid(graph)
        self.assertIn("He said 'hello'", text)
        self.assertNotIn('He said "hello"', text)

    def test_link_with_unknown_source_defines_implicit_outcome_node(self) -> None:
        graph = OPMGraph(
            objects=["Heart"],
            links=[OPMLink("Unknown node", "leads to", "Heart")],
        )
        text = graph_to_mermaid(graph)
        self.assertIn("out_unknown_node", text)
        self.assertIn('out_unknown_node{{"Unknown node"}}', text)
        self.assertIn("obj_heart", text)
        self.assertIn('out_unknown_node -->|"leads to"| obj_heart', text)

    def test_multiple_nodes_and_links_all_appear(self) -> None:
        graph = OPMGraph(
            objects=["A", "B"],
            processes=["P"],
            states=["S"],
            links=[
                OPMLink("A", "feeds", "P"),
                OPMLink("P", "produces", "S"),
            ],
        )
        text = graph_to_mermaid(graph)
        self.assertIn('"A"', text)
        self.assertIn('"B"', text)
        self.assertIn('"P"', text)
        self.assertIn('"S"', text)
        self.assertIn('-->|"feeds"|', text)
        self.assertIn('-->|"produces"|', text)


def _mi_graph() -> OPMGraph:
    """Mirror of the bundled myocardial-infarction KB topic."""
    return OPMGraph(
        objects=["Coronary artery", "Atherosclerotic plaque", "Heart muscle"],
        processes=["Plaque build-up", "Artery blockage", "Blood flow reduction"],
        states=["Narrowed artery", "Low oxygen supply", "Injured myocardium"],
        links=[
            OPMLink("Coronary artery", "object participates in process", "Plaque build-up"),
            OPMLink("Plaque build-up", "process changes state", "Narrowed artery"),
            OPMLink("Artery blockage", "process changes state", "Low oxygen supply"),
            OPMLink("Blood flow reduction", "process leads to disease outcome", "Myocardial infarction"),
        ],
    )


_MI_REASONING_PATH = [
    "Atherosclerosis",
    "Coronary artery blockage",
    "Reduced blood flow",
    "Myocardial infarction",
]


def _node_ids_in_edges(text: str) -> set[str]:
    """Return the set of node IDs that appear on either side of an edge line."""
    edge_re = re.compile(r"^\s*(\w+)\s*(?:-->|==>|-\.->)")
    target_re = re.compile(r"\|\s*(\w+)\s*$")
    appearance: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not ("-->" in line or "==>" in line or "-.->" in line):
            continue
        m = edge_re.match(line)
        if m:
            appearance.add(m.group(1))
        # Target is the trailing word after the closing pipe of the label
        for tail in line.split("|"):
            t = tail.strip()
            tm = re.match(r"^(\w+)\b", t)
            if tm and tm.group(1) not in {"leads", "involves", "object", "process", "to"}:
                pass  # not a reliable signal alone
        # Use a stricter pass: split the line on the arrow and parse the right side
        for arrow in ("==>", "-.->", "-->"):
            if arrow in line:
                _, _, rhs = line.partition(arrow)
                rhs = rhs.strip()
                if rhs.startswith("|"):
                    rhs = rhs[1:]
                    end = rhs.find("|")
                    if end != -1:
                        rhs = rhs[end + 1 :].strip()
                m2 = re.match(r"^(\w+)", rhs)
                if m2:
                    appearance.add(m2.group(1))
                break
    return appearance


def _defined_node_ids(text: str) -> set[str]:
    """Return the set of node IDs defined as nodes (id followed by a shape opener)."""
    ids: set[str] = set()
    for raw in text.splitlines():
        m = re.match(r"^\s*(\w+)[\[\(\{]", raw)
        if m:
            ids.add(m.group(1))
    return ids


class ReasoningPathConnectivityTests(unittest.TestCase):
    def test_reasoning_path_renders_connected_chain(self) -> None:
        text = graph_to_mermaid(OPMGraph(), reasoning_path=["Cause", "Effect"])
        self.assertIn('step_cause{{"Cause"}}', text)
        self.assertIn('step_effect{{"Effect"}}', text)
        self.assertIn('step_cause ==>|"leads to"| step_effect', text)

    def test_reasoning_path_chain_uses_thick_arrow(self) -> None:
        text = graph_to_mermaid(
            OPMGraph(), reasoning_path=["A cause", "Middle", "Final outcome"]
        )
        self.assertEqual(text.count("==>"), 2)

    def test_empty_steps_in_reasoning_path_are_skipped(self) -> None:
        text = graph_to_mermaid(
            OPMGraph(), reasoning_path=["Real step", "", "   ", "Other step"]
        )
        self.assertIn('"Real step"', text)
        self.assertIn('"Other step"', text)
        self.assertEqual(text.count("==>"), 1)

    def test_implicit_outcome_node_explicitly_defined(self) -> None:
        text = graph_to_mermaid(_mi_graph(), reasoning_path=_MI_REASONING_PATH)
        self.assertIn('out_myocardial_infarction{{"Myocardial infarction"}}', text)

    def test_reasoning_step_reuses_existing_implicit_outcome_node(self) -> None:
        text = graph_to_mermaid(_mi_graph(), reasoning_path=_MI_REASONING_PATH)
        # "Myocardial infarction" exists once (defined as an outcome from the
        # link target) and the path reuses that node rather than creating a
        # duplicate ``step_myocardial_infarction`` node.
        self.assertEqual(
            text.count('"Myocardial infarction"'),
            1,
        )
        self.assertNotIn("step_myocardial_infarction", text)

    def test_chain_reaches_terminal_outcome_node(self) -> None:
        text = graph_to_mermaid(_mi_graph(), reasoning_path=_MI_REASONING_PATH)
        # Final spine edge should land on the terminal outcome.
        self.assertIn(
            'step_reduced_blood_flow ==>|"leads to"| out_myocardial_infarction',
            text,
        )

    def test_isolated_object_connected_via_involves_edge(self) -> None:
        text = graph_to_mermaid(_mi_graph(), reasoning_path=_MI_REASONING_PATH)
        # Atherosclerotic plaque — isolated in OPM links — should attach to
        # the "Atherosclerosis" step via prefix matching ("atheroscler...").
        self.assertIn(
            'step_atherosclerosis -.->|"involves"| obj_atherosclerotic_plaque',
            text,
        )

    def test_isolated_state_matched_by_word_prefix(self) -> None:
        text = graph_to_mermaid(_mi_graph(), reasoning_path=_MI_REASONING_PATH)
        # Injured myocardium -> matches "Myocardial infarction" via the
        # "myocardi" prefix.
        self.assertIn(
            'out_myocardial_infarction -.->|"involves"| state_injured_myocardium',
            text,
        )

    def test_isolated_node_with_no_match_falls_back_to_final_step(self) -> None:
        text = graph_to_mermaid(_mi_graph(), reasoning_path=_MI_REASONING_PATH)
        # "Heart muscle" shares no words/prefixes with any step, so the
        # fallback connects it to the final reasoning step.
        self.assertIn(
            'out_myocardial_infarction -.->|"involves"| obj_heart_muscle',
            text,
        )

    def test_no_isolated_nodes_in_full_mi_graph(self) -> None:
        text = graph_to_mermaid(_mi_graph(), reasoning_path=_MI_REASONING_PATH)
        defined = _defined_node_ids(text)
        in_edges = _node_ids_in_edges(text)
        self.assertEqual(defined - in_edges, set())

    def test_substring_match_picks_most_relevant_step(self) -> None:
        # When an OPM element name is a substring of one step, that step wins
        # regardless of fuzzier alternatives.
        graph = OPMGraph(objects=["Coronary artery"])
        text = graph_to_mermaid(
            graph,
            reasoning_path=["Atherosclerosis", "Coronary artery blockage", "Outcome"],
        )
        # "Coronary artery" is a substring of "Coronary artery blockage" so it
        # attaches there, not to the final step or to atherosclerosis.
        self.assertIn(
            'step_coronary_artery_blockage -.->|"involves"| obj_coronary_artery',
            text,
        )

    def test_reasoning_path_argument_is_keyword_only(self) -> None:
        with self.assertRaises(TypeError):
            graph_to_mermaid(OPMGraph(), ["A", "B"])  # type: ignore[misc]

    def test_no_reasoning_path_means_no_chain_or_involves_edges(self) -> None:
        text = graph_to_mermaid(_mi_graph())
        self.assertNotIn("==>", text)
        self.assertNotIn("-.->", text)


class ExportMermaidTests(unittest.TestCase):
    def test_writes_mermaid_text_to_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.mmd"

            returned = export_mermaid(_sample_graph(), path)

            self.assertEqual(returned, path)
            self.assertTrue(path.exists())
            text = path.read_text(encoding="utf-8")
            self.assertIn("flowchart TD", text)

    def test_content_matches_graph_to_mermaid(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.mmd"

            export_mermaid(_sample_graph(), path)

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                graph_to_mermaid(_sample_graph()),
            )

    def test_creates_missing_parent_directories(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "deep" / "nested" / "graph.mmd"

            export_mermaid(_sample_graph(), path)

            self.assertTrue(path.exists())

    def test_overwrites_existing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.mmd"
            path.write_text("old content", encoding="utf-8")

            export_mermaid(_sample_graph(), path)

            self.assertIn("flowchart TD", path.read_text(encoding="utf-8"))

    def test_unwritable_parent_raises_mermaid_export_error(self) -> None:
        with TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker"
            blocker.write_text("not a directory", encoding="utf-8")
            target = blocker / "graph.mmd"

            with self.assertRaises(MermaidExportError):
                export_mermaid(_sample_graph(), target)


if __name__ == "__main__":
    unittest.main()
