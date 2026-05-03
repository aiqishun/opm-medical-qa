"""Tests for the JSON/JSONL helpers in :mod:`data_io`."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from data_io import DataIOError, read_json, read_jsonl, write_jsonl


class ReadJsonTests(unittest.TestCase):
    def test_returns_decoded_object(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            path.write_text(json.dumps({"a": 1, "b": [2, 3]}), encoding="utf-8")

            self.assertEqual(read_json(path), {"a": 1, "b": [2, 3]})

    def test_missing_file_raises_data_io_error(self) -> None:
        with self.assertRaises(DataIOError) as cm:
            read_json(Path("/nonexistent/path/file.json"))
        self.assertIn("File not found", str(cm.exception))

    def test_invalid_json_raises_data_io_error(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            path.write_text("{not valid json", encoding="utf-8")

            with self.assertRaises(DataIOError) as cm:
                read_json(path)
            self.assertIn("Invalid JSON", str(cm.exception))


class ReadJsonlTests(unittest.TestCase):
    def test_yields_one_record_per_non_empty_line(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.jsonl"
            path.write_text(
                '{"x": 1}\n\n{"x": 2}\n   \n{"x": 3}\n',
                encoding="utf-8",
            )

            records = list(read_jsonl(path))

            self.assertEqual(records, [{"x": 1}, {"x": 2}, {"x": 3}])

    def test_missing_file_raises_data_io_error(self) -> None:
        with self.assertRaises(DataIOError):
            list(read_jsonl(Path("/nonexistent/file.jsonl")))

    def test_invalid_line_reports_line_number(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.jsonl"
            path.write_text('{"x": 1}\n{not json}\n', encoding="utf-8")

            with self.assertRaises(DataIOError) as cm:
                list(read_jsonl(path))
            self.assertIn("line 2", str(cm.exception))

    def test_non_object_line_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.jsonl"
            path.write_text("[1, 2, 3]\n", encoding="utf-8")

            with self.assertRaises(DataIOError) as cm:
                list(read_jsonl(path))
            self.assertIn("JSON object", str(cm.exception))


class WriteJsonlTests(unittest.TestCase):
    def test_creates_parent_directory_and_returns_count(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "out.jsonl"
            count = write_jsonl(path, [{"a": 1}, {"b": 2}])

            self.assertEqual(count, 2)
            self.assertTrue(path.exists())
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual([json.loads(line) for line in lines], [{"a": 1}, {"b": 2}])

    def test_preserves_unicode(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.jsonl"
            write_jsonl(path, [{"text": "café"}])

            self.assertIn("café", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
