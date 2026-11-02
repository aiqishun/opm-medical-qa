"""Tests for the optional ``llm_filter_medqa.py`` CLI script."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import llm_filter_medqa


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "llm_filter_medqa.py"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


class PromptTests(unittest.TestCase):
    def test_prompt_distinguishes_main_topic_from_incidental_history(self) -> None:
        prompt = llm_filter_medqa.build_user_prompt(
            {
                "id": "case-1",
                "question": (
                    "A patient with history of myocardial infarction presents "
                    "with jaundice. What enzyme pattern is expected?"
                ),
                "options": {"A": "ALT elevation", "B": "ST elevation"},
                "answer": "Do not send generated answer text",
            }
        )

        self.assertIn("main tested concept", prompt)
        self.assertIn("past history or incidental context", prompt)
        self.assertIn("history of myocardial infarction", prompt)
        self.assertNotIn("Do not send generated answer text", prompt)


class ResponseParsingTests(unittest.TestCase):
    def test_parse_model_response_validates_structured_output(self) -> None:
        response = {
            "output_text": json.dumps(
                {
                    "llm_is_cardiology_relevant": True,
                    "llm_primary_topic": "aortic stenosis",
                    "llm_confidence": "high",
                    "llm_is_incidental_history_only": False,
                    "llm_reason": "The stem asks about a valve lesion.",
                }
            )
        }

        classification = llm_filter_medqa.parse_model_response(response)

        self.assertTrue(classification.llm_is_cardiology_relevant)
        self.assertEqual(classification.llm_primary_topic, "aortic stenosis")
        self.assertEqual(classification.llm_confidence, "high")

    def test_parse_model_response_rejects_malformed_json(self) -> None:
        with self.assertRaises(llm_filter_medqa.MalformedModelResponse):
            llm_filter_medqa.parse_model_response({"output_text": "{not json"})

    def test_parse_model_response_rejects_invalid_confidence(self) -> None:
        response = {
            "output_text": json.dumps(
                {
                    "llm_is_cardiology_relevant": False,
                    "llm_primary_topic": None,
                    "llm_confidence": "certain",
                    "llm_is_incidental_history_only": True,
                    "llm_reason": "Cardiac history is incidental.",
                }
            )
        }

        with self.assertRaises(llm_filter_medqa.MalformedModelResponse):
            llm_filter_medqa.parse_model_response(response)

    def test_parse_model_response_reads_nested_responses_text(self) -> None:
        response = {
            "output": [
                {
                    "content": [
                        {
                            "text": json.dumps(
                                {
                                    "llm_is_cardiology_relevant": False,
                                    "llm_primary_topic": None,
                                    "llm_confidence": "medium",
                                    "llm_is_incidental_history_only": True,
                                    "llm_reason": "The cardiac term is only history.",
                                }
                            )
                        }
                    ]
                }
            ]
        }

        classification = llm_filter_medqa.parse_model_response(response)

        self.assertFalse(classification.llm_is_cardiology_relevant)
        self.assertTrue(classification.llm_is_incidental_history_only)


class RetryTests(unittest.TestCase):
    def test_classify_with_retry_retries_once(self) -> None:
        calls = 0

        def flaky_classifier(record: dict) -> llm_filter_medqa.LLMClassification:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise llm_filter_medqa.LLMAPIError("temporary")
            return llm_filter_medqa.LLMClassification(
                llm_is_cardiology_relevant=True,
                llm_primary_topic="heart failure",
                llm_confidence="high",
                llm_is_incidental_history_only=False,
                llm_reason="The stem tests heart failure.",
            )

        classification = llm_filter_medqa.classify_with_retry(
            {"question": "Heart failure mechanism?"},
            flaky_classifier,
            sleep_seconds=0,
        )

        self.assertEqual(calls, 2)
        self.assertEqual(classification.llm_primary_topic, "heart failure")


class OpenAIClientTests(unittest.TestCase):
    def test_responses_client_uses_json_schema_structured_output(self) -> None:
        client = llm_filter_medqa.OpenAIResponsesClassifier(
            api_key="test-key",
            model="gpt-4o-mini",
        )
        response = {
            "output_text": json.dumps(
                {
                    "llm_is_cardiology_relevant": True,
                    "llm_primary_topic": "angina",
                    "llm_confidence": "high",
                    "llm_is_incidental_history_only": False,
                    "llm_reason": "The stem tests angina.",
                }
            )
        }

        with mock.patch.object(client, "_post_json", return_value=response) as post_json:
            classification = client({"question": "What causes exertional chest pain?"})

        payload = post_json.call_args.args[0]
        self.assertEqual(classification.llm_primary_topic, "angina")
        self.assertEqual(payload["model"], "gpt-4o-mini")
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertIn(
            "llm_is_incidental_history_only",
            payload["text"]["format"]["schema"]["required"],
        )


class RunFilterTests(unittest.TestCase):
    def test_run_filter_writes_llm_fields_with_mocked_classifier(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            output_path = tmp_path / "out.jsonl"
            relevant_output_path = tmp_path / "relevant.jsonl"
            summary_path = tmp_path / "summary.md"
            _write_jsonl(
                input_path,
                [
                    {
                        "id": "cardiac",
                        "question": "Which murmur finding suggests aortic stenosis?",
                    },
                    {
                        "id": "history-only",
                        "question": (
                            "A patient with prior MI has an itchy rash. "
                            "What is the diagnosis?"
                        ),
                    },
                    {
                        "id": "incidental-cardiac",
                        "question": (
                            "A patient with heart failure history has pneumonia. "
                            "Which organism is most likely?"
                        ),
                    },
                ],
            )

            def classifier(record: dict) -> llm_filter_medqa.LLMClassification:
                if record["id"] == "cardiac":
                    return llm_filter_medqa.LLMClassification(
                        llm_is_cardiology_relevant=True,
                        llm_primary_topic="aortic stenosis",
                        llm_confidence="high",
                        llm_is_incidental_history_only=False,
                        llm_reason="The main tested concept is a valve lesion.",
                    )
                if record["id"] == "incidental-cardiac":
                    return llm_filter_medqa.LLMClassification(
                        llm_is_cardiology_relevant=True,
                        llm_primary_topic="heart failure",
                        llm_confidence="medium",
                        llm_is_incidental_history_only=True,
                        llm_reason="Heart failure is only background history.",
                    )
                return llm_filter_medqa.LLMClassification(
                    llm_is_cardiology_relevant=False,
                    llm_primary_topic=None,
                    llm_confidence="high",
                    llm_is_incidental_history_only=True,
                    llm_reason="The MI mention is only past history.",
                )

            summary = llm_filter_medqa.run_filter(
                input_path=input_path,
                output_path=output_path,
                summary_path=summary_path,
                model="mock-model",
                relevant_output_path=relevant_output_path,
                classifier=classifier,
            )

            self.assertEqual(summary.classified_records, 3)
            self.assertEqual(summary.cardiology_relevant, 2)
            self.assertEqual(summary.incidental_history_only, 2)
            self.assertEqual(summary.relevant_only_written, 1)
            rows = _read_jsonl(output_path)
            self.assertEqual(rows[0]["llm_primary_topic"], "aortic stenosis")
            self.assertEqual(rows[0]["llm_model"], "mock-model")
            self.assertFalse(rows[1]["llm_is_cardiology_relevant"])
            self.assertTrue(rows[1]["llm_is_incidental_history_only"])
            relevant_rows = _read_jsonl(relevant_output_path)
            self.assertEqual(len(relevant_rows), 1)
            self.assertEqual(relevant_rows[0]["id"], "cardiac")
            summary_md = summary_path.read_text(encoding="utf-8")
            self.assertIn("audit and triage", summary_md)
            self.assertIn("| Relevant-only records written | 1 |", summary_md)
            self.assertIn(str(relevant_output_path), summary_md)

    def test_relevant_only_records_requires_relevant_and_not_incidental(self) -> None:
        records = [
            {
                "id": "keep",
                "llm_is_cardiology_relevant": True,
                "llm_is_incidental_history_only": False,
            },
            {
                "id": "exclude-history",
                "llm_is_cardiology_relevant": True,
                "llm_is_incidental_history_only": True,
            },
            {
                "id": "exclude-noncardiac",
                "llm_is_cardiology_relevant": False,
                "llm_is_incidental_history_only": False,
            },
        ]

        relevant = llm_filter_medqa.relevant_only_records(records)

        self.assertEqual([record["id"] for record in relevant], ["keep"])

    def test_run_filter_limit_processes_prefix_only(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(
                input_path,
                [
                    {"id": "a", "question": "What causes angina?"},
                    {"id": "b", "question": "What causes endocarditis?"},
                ],
            )

            summary = llm_filter_medqa.run_filter(
                input_path=input_path,
                output_path=tmp_path / "out.jsonl",
                summary_path=tmp_path / "summary.md",
                model="mock-model",
                limit=1,
                classifier=lambda record: llm_filter_medqa.LLMClassification(
                    llm_is_cardiology_relevant=True,
                    llm_primary_topic="angina",
                    llm_confidence="high",
                    llm_is_incidental_history_only=False,
                    llm_reason="The stem tests angina.",
                ),
            )

            self.assertEqual(summary.total_input_records, 2)
            self.assertEqual(summary.attempted_records, 1)
            self.assertEqual(len(_read_jsonl(tmp_path / "out.jsonl")), 1)

    def test_run_filter_records_failure_after_retry(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(input_path, [{"id": "a", "question": "What causes angina?"}])

            summary = llm_filter_medqa.run_filter(
                input_path=input_path,
                output_path=tmp_path / "out.jsonl",
                summary_path=tmp_path / "summary.md",
                model="mock-model",
                classifier=lambda record: (_ for _ in ()).throw(
                    llm_filter_medqa.LLMAPIError("boom")
                ),
            )

            self.assertEqual(summary.failed_records, 1)
            row = _read_jsonl(tmp_path / "out.jsonl")[0]
            self.assertEqual(row["llm_confidence"], "low")
            self.assertIn("boom", row["llm_error"])

    def test_run_filter_skips_missing_question_without_calling_classifier(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(input_path, [{"id": "missing"}])
            classifier = mock.Mock()

            summary = llm_filter_medqa.run_filter(
                input_path=input_path,
                output_path=tmp_path / "out.jsonl",
                summary_path=tmp_path / "summary.md",
                model="mock-model",
                classifier=classifier,
            )

            self.assertEqual(summary.skipped_missing_question, 1)
            classifier.assert_not_called()
            row = _read_jsonl(tmp_path / "out.jsonl")[0]
            self.assertIn("Missing non-empty question", row["llm_error"])


class MainTests(unittest.TestCase):
    def test_main_dry_run_does_not_require_api_key_or_write_output(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            output_path = tmp_path / "out.jsonl"
            relevant_output_path = tmp_path / "relevant.jsonl"
            _write_jsonl(input_path, [{"id": "a", "question": "What causes angina?"}])

            buffer = io.StringIO()
            with mock.patch.dict(os.environ, {}, clear=True):
                with redirect_stdout(buffer):
                    exit_code = llm_filter_medqa.main(
                        [
                            "--input", str(input_path),
                            "--output", str(output_path),
                            "--summary", str(tmp_path / "summary.md"),
                            "--relevant-output", str(relevant_output_path),
                            "--dry-run",
                        ]
                    )

            self.assertEqual(exit_code, 0)
            self.assertIn("Dry run only", buffer.getvalue())
            self.assertIn("User prompt for first selected record", buffer.getvalue())
            self.assertFalse(output_path.exists())
            self.assertFalse(relevant_output_path.exists())

    def test_main_reports_missing_api_key(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(input_path, [{"question": "What causes angina?"}])
            err = io.StringIO()

            with mock.patch.dict(os.environ, {}, clear=True):
                with redirect_stderr(err), redirect_stdout(io.StringIO()):
                    exit_code = llm_filter_medqa.main(
                        [
                            "--input", str(input_path),
                            "--output", str(tmp_path / "out.jsonl"),
                            "--summary", str(tmp_path / "summary.md"),
                        ]
                    )

            self.assertEqual(exit_code, 1)
            self.assertIn("OPENAI_API_KEY is required", err.getvalue())


class ScriptInvocationTests(unittest.TestCase):
    def test_script_dry_run_invocation(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(input_path, [{"question": "What causes angina?"}])

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input", str(input_path),
                    "--output", str(tmp_path / "out.jsonl"),
                    "--summary", str(tmp_path / "summary.md"),
                    "--dry-run",
                    "--limit", "1",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={key: value for key, value in os.environ.items() if key != "OPENAI_API_KEY"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Dry run complete; no API calls were made.", result.stdout)


if __name__ == "__main__":
    unittest.main()
