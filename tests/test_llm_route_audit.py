"""Tests for the optional ``llm_route_audit.py`` CLI script."""

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

import llm_route_audit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "llm_route_audit.py"


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


def _audit(
    *,
    concept: str = "aortic regurgitation",
    acceptable: bool = False,
    recommended: str = "aortic regurgitation",
    out_of_scope: bool = False,
    error_type: str = "physical_sign_recognition_failure",
    confidence: str = "high",
) -> llm_route_audit.RouteAuditClassification:
    return llm_route_audit.RouteAuditClassification(
        primary_tested_concept=concept,
        is_current_topic_acceptable=acceptable,
        recommended_topic=recommended,
        is_out_of_scope_for_current_kb=out_of_scope,
        error_type=error_type,
        evidence_sentence="Early diastolic murmur and head bobbing are present.",
        short_reason="The stem tests aortic regurgitation, not the matched topic.",
        confidence=confidence,
    )


class PromptTests(unittest.TestCase):
    def test_record_for_prompt_sends_only_requested_fields(self) -> None:
        prompt_record = llm_route_audit.record_for_prompt(
            {
                "id": "case-1",
                "question": "Which finding is expected with decreased stroke volume?",
                "matched_topic": "coronary artery disease",
                "matched_terms": ["coronary artery disease"],
                "answer": "CAD narrows coronary arteries.",
                "explanation": "Do not send this field.",
                "graph_path": "outputs/graphs/q1.json",
            }
        )

        self.assertEqual(
            set(prompt_record),
            {"question", "current_matched_topic", "matched_terms", "answer"},
        )
        self.assertEqual(prompt_record["current_matched_topic"], "coronary artery disease")
        self.assertNotIn("explanation", prompt_record)
        self.assertNotIn("graph_path", prompt_record)

    def test_prompt_names_topic_routing_failure_modes(self) -> None:
        prompt = llm_route_audit.build_user_prompt(
            {
                "question": "Known angina does not improve after nitroglycerin.",
                "matched_topic": "angina",
                "matched_terms": ["angina"],
                "answer": "Angina is reduced oxygen supply to heart muscle.",
            }
        )

        self.assertIn("primary tested concept", prompt)
        self.assertIn("temporal_state_transition_failure", prompt)
        self.assertIn("past_medical_history_distraction", prompt)


class ResponseParsingTests(unittest.TestCase):
    def test_parse_model_response_validates_structured_output(self) -> None:
        response = {
            "output_text": json.dumps(
                {
                    "primary_tested_concept": "acute coronary syndrome",
                    "is_current_topic_acceptable": False,
                    "recommended_topic": "myocardial infarction",
                    "is_out_of_scope_for_current_kb": False,
                    "error_type": "temporal_state_transition_failure",
                    "evidence_sentence": "Pain persists after nitroglycerin.",
                    "short_reason": "Refractory angina symptoms should route to ACS/MI.",
                    "confidence": "high",
                }
            )
        }

        audit = llm_route_audit.parse_model_response(response)

        self.assertEqual(audit.primary_tested_concept, "acute coronary syndrome")
        self.assertEqual(audit.error_type, "temporal_state_transition_failure")
        self.assertFalse(audit.is_current_topic_acceptable)

    def test_parse_model_response_rejects_invalid_error_type(self) -> None:
        response = {
            "output_text": json.dumps(
                {
                    "primary_tested_concept": "homocystinuria",
                    "is_current_topic_acceptable": False,
                    "recommended_topic": "homocystinuria",
                    "is_out_of_scope_for_current_kb": True,
                    "error_type": "not_in_enum",
                    "evidence_sentence": "The sibling had myocardial infarction.",
                    "short_reason": "The cardiac event belongs to family history.",
                    "confidence": "high",
                }
            )
        }

        with self.assertRaises(llm_route_audit.MalformedRouteAuditResponse):
            llm_route_audit.parse_model_response(response)

    def test_parse_model_response_rejects_empty_required_string(self) -> None:
        response = {
            "output_text": json.dumps(
                {
                    "primary_tested_concept": "",
                    "is_current_topic_acceptable": True,
                    "recommended_topic": "angina",
                    "is_out_of_scope_for_current_kb": False,
                    "error_type": "correct_or_acceptable",
                    "evidence_sentence": "The question asks about angina.",
                    "short_reason": "The current route is acceptable.",
                    "confidence": "medium",
                }
            )
        }

        with self.assertRaises(llm_route_audit.MalformedRouteAuditResponse):
            llm_route_audit.parse_model_response(response)

    def test_parse_model_response_reads_nested_responses_text(self) -> None:
        response = {
            "output": [
                {
                    "content": [
                        {
                            "text": json.dumps(
                                {
                                    "primary_tested_concept": "stroke volume",
                                    "is_current_topic_acceptable": False,
                                    "recommended_topic": "cardiac physiology",
                                    "is_out_of_scope_for_current_kb": True,
                                    "error_type": "vignette_distraction",
                                    "evidence_sentence": "The final question asks about stroke volume.",
                                    "short_reason": "CAD is background context.",
                                    "confidence": "high",
                                }
                            )
                        }
                    ]
                }
            ]
        }

        audit = llm_route_audit.parse_model_response(response)

        self.assertEqual(audit.recommended_topic, "cardiac physiology")
        self.assertTrue(audit.is_out_of_scope_for_current_kb)


class RetryTests(unittest.TestCase):
    def test_audit_with_retry_retries_once(self) -> None:
        calls = 0

        def flaky_auditor(record: dict) -> llm_route_audit.RouteAuditClassification:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise llm_route_audit.RouteAuditAPIError("temporary")
            return _audit()

        audit = llm_route_audit.audit_with_retry(
            {"question": "Early diastolic murmur?"},
            flaky_auditor,
            sleep_seconds=0,
        )

        self.assertEqual(calls, 2)
        self.assertEqual(audit.recommended_topic, "aortic regurgitation")


class OpenAIClientTests(unittest.TestCase):
    def test_responses_client_uses_json_schema_structured_output(self) -> None:
        client = llm_route_audit.OpenAIResponsesRouteAuditor(
            api_key="test-key",
            model="gpt-5.4-nano",
        )
        response = {
            "output_text": json.dumps(
                {
                    "primary_tested_concept": "aortic regurgitation",
                    "is_current_topic_acceptable": False,
                    "recommended_topic": "aortic regurgitation",
                    "is_out_of_scope_for_current_kb": False,
                    "error_type": "physical_sign_recognition_failure",
                    "evidence_sentence": "There is an early diastolic murmur.",
                    "short_reason": "The signs point to aortic regurgitation.",
                    "confidence": "high",
                }
            )
        }

        with mock.patch.object(client, "_post_json", return_value=response) as post_json:
            audit = client({"question": "Early diastolic murmur?", "matched_topic": "PE"})

        payload = post_json.call_args.args[0]
        self.assertEqual(audit.error_type, "physical_sign_recognition_failure")
        self.assertEqual(payload["model"], "gpt-5.4-nano")
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertIn("error_type", payload["text"]["format"]["schema"]["required"])


class RunAuditTests(unittest.TestCase):
    def test_run_audit_writes_fields_and_summary_with_mocked_auditor(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            output_path = tmp_path / "out.jsonl"
            summary_path = tmp_path / "summary.md"
            _write_jsonl(
                input_path,
                [
                    {
                        "id": "sign",
                        "question": "Early diastolic murmur with head bobbing.",
                        "matched_topic": "pulmonary embolism",
                        "matched_terms": ["murmur", "valve"],
                        "answer": "Pulmonary embolism obstructs pulmonary blood flow.",
                    },
                    {
                        "id": "ok",
                        "question": "What causes myocardial infarction?",
                        "matched_topic": "myocardial infarction",
                        "matched_terms": ["myocardial infarction"],
                        "answer": "MI is caused by coronary artery blockage.",
                    },
                    {
                        "id": "scope",
                        "question": "Sibling MI plus cataracts and developmental delay.",
                        "matched_topic": "myocardial infarction",
                        "matched_terms": ["myocardial infarction"],
                        "answer": "MI is caused by coronary blockage.",
                    },
                ],
            )

            def auditor(record: dict) -> llm_route_audit.RouteAuditClassification:
                if record["id"] == "ok":
                    return _audit(
                        concept="myocardial infarction",
                        acceptable=True,
                        recommended="myocardial infarction",
                        error_type="correct_or_acceptable",
                    )
                if record["id"] == "scope":
                    return _audit(
                        concept="homocystinuria",
                        recommended="homocystinuria",
                        out_of_scope=True,
                        error_type="family_history_distraction",
                    )
                return _audit()

            summary = llm_route_audit.run_audit(
                input_path=input_path,
                output_path=output_path,
                summary_path=summary_path,
                model="mock-model",
                auditor=auditor,
            )

            self.assertEqual(summary.audited_records, 3)
            self.assertEqual(summary.acceptable_topics, 1)
            self.assertEqual(summary.unacceptable_topics, 2)
            self.assertEqual(summary.out_of_scope, 1)
            self.assertEqual(
                summary.error_type_counts["family_history_distraction"],
                1,
            )
            rows = _read_jsonl(output_path)
            self.assertEqual(rows[0]["recommended_topic"], "aortic regurgitation")
            self.assertEqual(rows[0]["route_audit_model"], "mock-model")
            self.assertTrue(rows[1]["is_current_topic_acceptable"])
            self.assertTrue(rows[2]["is_out_of_scope_for_current_kb"])
            md = summary_path.read_text(encoding="utf-8")
            self.assertIn("| Current topic acceptable | 1 |", md)
            self.assertIn("| physical_sign_recognition_failure | 1 |", md)

    def test_run_audit_limit_processes_prefix_only(self) -> None:
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

            summary = llm_route_audit.run_audit(
                input_path=input_path,
                output_path=tmp_path / "out.jsonl",
                summary_path=tmp_path / "summary.md",
                model="mock-model",
                limit=1,
                auditor=lambda record: _audit(acceptable=True, error_type="correct_or_acceptable"),
            )

            self.assertEqual(summary.total_input_records, 2)
            self.assertEqual(summary.attempted_records, 1)
            self.assertEqual(len(_read_jsonl(tmp_path / "out.jsonl")), 1)

    def test_run_audit_records_failure_after_retry(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(input_path, [{"id": "a", "question": "What causes angina?"}])

            summary = llm_route_audit.run_audit(
                input_path=input_path,
                output_path=tmp_path / "out.jsonl",
                summary_path=tmp_path / "summary.md",
                model="mock-model",
                auditor=lambda record: (_ for _ in ()).throw(
                    llm_route_audit.RouteAuditAPIError("boom")
                ),
            )

            self.assertEqual(summary.failed_records, 1)
            row = _read_jsonl(tmp_path / "out.jsonl")[0]
            self.assertEqual(row["confidence"], "low")
            self.assertIn("boom", row["route_audit_error"])

    def test_run_audit_skips_missing_question_without_calling_auditor(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(input_path, [{"id": "missing"}])
            auditor = mock.Mock()

            summary = llm_route_audit.run_audit(
                input_path=input_path,
                output_path=tmp_path / "out.jsonl",
                summary_path=tmp_path / "summary.md",
                model="mock-model",
                auditor=auditor,
            )

            self.assertEqual(summary.skipped_missing_question, 1)
            auditor.assert_not_called()
            row = _read_jsonl(tmp_path / "out.jsonl")[0]
            self.assertIn("Missing non-empty question", row["route_audit_error"])


class MainTests(unittest.TestCase):
    def test_main_dry_run_does_not_require_api_key_or_write_output(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            output_path = tmp_path / "out.jsonl"
            _write_jsonl(
                input_path,
                [
                    {
                        "question": "What finding suggests aortic regurgitation?",
                        "matched_topic": "pulmonary embolism",
                        "matched_terms": ["murmur"],
                        "answer": "PE obstructs pulmonary blood flow.",
                    }
                ],
            )

            buffer = io.StringIO()
            with mock.patch.dict(os.environ, {}, clear=True):
                with redirect_stdout(buffer):
                    exit_code = llm_route_audit.main(
                        [
                            "--input", str(input_path),
                            "--output", str(output_path),
                            "--summary", str(tmp_path / "summary.md"),
                            "--dry-run",
                        ]
                    )

            self.assertEqual(exit_code, 0)
            self.assertIn("Dry run only", buffer.getvalue())
            self.assertIn("User prompt for first selected record", buffer.getvalue())
            self.assertFalse(output_path.exists())

    def test_main_reports_missing_api_key(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_path = tmp_path / "in.jsonl"
            _write_jsonl(input_path, [{"question": "What causes angina?"}])
            err = io.StringIO()

            with mock.patch.dict(os.environ, {}, clear=True):
                with redirect_stderr(err), redirect_stdout(io.StringIO()):
                    exit_code = llm_route_audit.main(
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
