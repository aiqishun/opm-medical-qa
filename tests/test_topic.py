"""Tests for the cardiology topic loader."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from data_io import DataIOError
from reasoning.topic import CardiologyTopic, load_topics


_VALID_TOPIC: dict = {
    "name": "demo topic",
    "question_patterns": ["What causes demo?"],
    "keywords": ["demo"],
    "answer": "Demo answer.",
    "explanation": "Demo explanation.",
    "reasoning_path": ["A", "B"],
    "opm_objects": ["Object"],
    "opm_processes": ["Process"],
    "opm_states": ["State"],
    "opm_links": [{"source": "A", "relationship": "leads to", "target": "B"}],
}


class CardiologyTopicTests(unittest.TestCase):
    def test_from_dict_builds_topic(self) -> None:
        topic = CardiologyTopic.from_dict(_VALID_TOPIC)

        self.assertEqual(topic.name, "demo topic")
        self.assertEqual(topic.question_patterns, ["What causes demo?"])
        self.assertEqual(topic.opm_links[0]["source"], "A")

    def test_keywords_default_to_empty_list(self) -> None:
        data = {key: value for key, value in _VALID_TOPIC.items() if key != "keywords"}
        topic = CardiologyTopic.from_dict(data)

        self.assertEqual(topic.keywords, [])

    def test_missing_required_field_raises(self) -> None:
        data = {key: value for key, value in _VALID_TOPIC.items() if key != "answer"}

        with self.assertRaises(DataIOError) as cm:
            CardiologyTopic.from_dict(data)
        self.assertIn("answer", str(cm.exception))


class LoadTopicsTests(unittest.TestCase):
    def test_loads_topics_from_well_formed_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "kb.json"
            path.write_text(json.dumps({"topics": [_VALID_TOPIC]}), encoding="utf-8")

            topics = load_topics(path)

            self.assertEqual(len(topics), 1)
            self.assertIsInstance(topics[0], CardiologyTopic)

    def test_rejects_root_that_is_not_an_object(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "kb.json"
            path.write_text(json.dumps([_VALID_TOPIC]), encoding="utf-8")

            with self.assertRaises(DataIOError):
                load_topics(path)

    def test_rejects_missing_topics_list(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "kb.json"
            path.write_text(json.dumps({"items": []}), encoding="utf-8")

            with self.assertRaises(DataIOError) as cm:
                load_topics(path)
            self.assertIn("topics", str(cm.exception))

    def test_loads_bundled_knowledge_base(self) -> None:
        kb = Path(__file__).resolve().parents[1] / "data" / "processed" / "cardiology_knowledge.json"
        topics = load_topics(kb)

        self.assertGreater(len(topics), 0)
        self.assertTrue(any(topic.name == "myocardial infarction" for topic in topics))


if __name__ == "__main__":
    unittest.main()
