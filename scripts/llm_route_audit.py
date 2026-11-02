#!/usr/bin/env python
"""Optional LLM-assisted audit of OPM topic routing decisions.

This script is a local audit/triage aid for batch QA results. It does not
answer medical questions. It asks an OpenAI model to identify the primary
tested concept in each record and judge whether the current OPM matched topic
is an acceptable routing target.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib import error as urllib_error
from urllib import request as urllib_request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DEFAULT_INPUT = PROJECT_ROOT / "experiments" / "results" / "llm_relevant_batch_qa_results.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "experiments" / "results" / "llm_route_audit_100.jsonl"
DEFAULT_SUMMARY = (
    PROJECT_ROOT / "experiments" / "results" / "llm_route_audit_summary_100.md"
)
DEFAULT_MODEL = "gpt-5.4-nano"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
MAX_TEXT_CHARS = 500

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_io import DataIOError, read_jsonl, write_jsonl  # noqa: E402


ERROR_TYPES: tuple[str, ...] = (
    "past_medical_history_distraction",
    "family_history_distraction",
    "vignette_distraction",
    "manifestation_vs_cause",
    "generic_downstream_outcome",
    "physical_sign_recognition_failure",
    "anatomy_laterality_failure",
    "temporal_state_transition_failure",
    "medication_management_focus",
    "correct_or_acceptable",
    "other",
)

SYSTEM_PROMPT = """\
You are a careful medical-dataset routing auditor. Your task is only to audit
topic routing, not to answer the medical question or provide medical advice.

Identify the question's primary tested concept and judge whether the current
OPM matched_topic is acceptable. Pay close attention to distractors from past
medical history, family history, background vignettes, manifestations versus
causes, downstream generic outcomes, physical signs, temporal state changes,
medication-management focus, and anatomy/laterality clues.
"""

USER_PROMPT_TEMPLATE = """\
Audit the OPM topic routing for this batch QA result.
Identify the primary tested concept, especially when background entities are distractors.

Return a structured JSON object with:
- primary_tested_concept: the main concept actually being tested
- is_current_topic_acceptable: true if the current matched topic is a reasonable routing target
- recommended_topic: the best topic label to route to; use the current topic if acceptable
- is_out_of_scope_for_current_kb: true if the best topic is outside the current OPM cardiology KB
- error_type: one of the allowed enum values
- evidence_sentence: one short sentence from or closely paraphrasing the stem that supports the route
- short_reason: one short explanation of the audit judgment
- confidence: one of low, medium, high

Allowed error_type values:
{error_types}

Record:
{record_json}
"""

ROUTE_AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "primary_tested_concept": {"type": "string"},
        "is_current_topic_acceptable": {"type": "boolean"},
        "recommended_topic": {"type": "string"},
        "is_out_of_scope_for_current_kb": {"type": "boolean"},
        "error_type": {"type": "string", "enum": list(ERROR_TYPES)},
        "evidence_sentence": {"type": "string"},
        "short_reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": [
        "primary_tested_concept",
        "is_current_topic_acceptable",
        "recommended_topic",
        "is_out_of_scope_for_current_kb",
        "error_type",
        "evidence_sentence",
        "short_reason",
        "confidence",
    ],
}


class RouteAuditError(Exception):
    """Base error for route-audit failures."""


class RouteAuditConfigurationError(RouteAuditError):
    """Raised when required local configuration is missing."""


class RouteAuditAPIError(RouteAuditError):
    """Raised when the model API request fails."""


class MalformedRouteAuditResponse(RouteAuditError):
    """Raised when the model response cannot be parsed or validated."""


@dataclass(frozen=True)
class RouteAuditClassification:
    """Validated route-audit fields written back to each JSONL row."""

    primary_tested_concept: str
    is_current_topic_acceptable: bool
    recommended_topic: str
    is_out_of_scope_for_current_kb: bool
    error_type: str
    evidence_sentence: str
    short_reason: str
    confidence: str

    def as_record_fields(self, model: str) -> dict[str, Any]:
        return {
            "primary_tested_concept": self.primary_tested_concept,
            "is_current_topic_acceptable": self.is_current_topic_acceptable,
            "recommended_topic": self.recommended_topic,
            "is_out_of_scope_for_current_kb": self.is_out_of_scope_for_current_kb,
            "error_type": self.error_type,
            "evidence_sentence": self.evidence_sentence,
            "short_reason": self.short_reason,
            "confidence": self.confidence,
            "route_audit_model": model,
        }


@dataclass(frozen=True)
class RouteAuditSummary:
    """Counts returned by :func:`run_audit` for end-of-run reporting."""

    total_input_records: int
    attempted_records: int
    audited_records: int
    acceptable_topics: int
    unacceptable_topics: int
    out_of_scope: int
    failed_records: int
    skipped_missing_question: int
    input_path: Path
    output_path: Path
    summary_path: Path
    model: str
    limit: int | None = None
    dry_run: bool = False
    error_type_counts: dict[str, int] = field(default_factory=dict)
    results: list[dict[str, Any]] = field(default_factory=list)


Auditor = Callable[[Mapping[str, Any]], RouteAuditClassification]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Optionally use an OpenAI model to audit OPM matched_topic routing "
            "decisions in a batch QA results JSONL file."
        )
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        type=Path,
        help="Input batch QA results JSONL file.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        type=Path,
        help="Output JSONL file with route-audit metadata.",
    )
    parser.add_argument(
        "--summary",
        default=DEFAULT_SUMMARY,
        type=Path,
        help="Markdown summary path.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model name. Defaults to {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--limit",
        default=None,
        type=int,
        help="Optional maximum number of input records to process.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt and preview records without calling the API.",
    )
    return parser


def _question_text(record: Mapping[str, Any]) -> str | None:
    question = record.get("question")
    if not isinstance(question, str):
        return None
    question = question.strip()
    return question or None


def record_for_prompt(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return exactly the batch-result fields sent to the model."""

    matched_terms = record.get("matched_terms")
    if not isinstance(matched_terms, list):
        matched_terms = []
    return {
        "question": _question_text(record),
        "current_matched_topic": record.get("matched_topic"),
        "matched_terms": matched_terms,
        "answer": record.get("answer"),
    }


def build_user_prompt(record: Mapping[str, Any]) -> str:
    """Build the user prompt for one batch QA result row."""

    record_json = json.dumps(record_for_prompt(record), ensure_ascii=False, indent=2)
    return USER_PROMPT_TEMPLATE.format(
        error_types=", ".join(ERROR_TYPES),
        record_json=record_json,
    )


def _require_non_empty_string(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MalformedRouteAuditResponse(f"{key} must be a non-empty string")
    return value.strip()[:MAX_TEXT_CHARS]


def validate_route_audit(raw: Mapping[str, Any]) -> RouteAuditClassification:
    """Validate a decoded model JSON object."""

    missing = [key for key in ROUTE_AUDIT_SCHEMA["required"] if key not in raw]
    if missing:
        raise MalformedRouteAuditResponse(
            f"missing required field(s): {', '.join(missing)}"
        )

    if not isinstance(raw["is_current_topic_acceptable"], bool):
        raise MalformedRouteAuditResponse("is_current_topic_acceptable must be boolean")
    if not isinstance(raw["is_out_of_scope_for_current_kb"], bool):
        raise MalformedRouteAuditResponse("is_out_of_scope_for_current_kb must be boolean")

    error_type = raw["error_type"]
    if error_type not in ERROR_TYPES:
        raise MalformedRouteAuditResponse(
            f"error_type must be one of: {', '.join(ERROR_TYPES)}"
        )

    confidence = raw["confidence"]
    if confidence not in {"low", "medium", "high"}:
        raise MalformedRouteAuditResponse("confidence must be low, medium, or high")

    return RouteAuditClassification(
        primary_tested_concept=_require_non_empty_string(raw, "primary_tested_concept"),
        is_current_topic_acceptable=raw["is_current_topic_acceptable"],
        recommended_topic=_require_non_empty_string(raw, "recommended_topic"),
        is_out_of_scope_for_current_kb=raw["is_out_of_scope_for_current_kb"],
        error_type=error_type,
        evidence_sentence=_require_non_empty_string(raw, "evidence_sentence"),
        short_reason=_require_non_empty_string(raw, "short_reason"),
        confidence=confidence,
    )


def parse_model_response(response: Mapping[str, Any]) -> RouteAuditClassification:
    """Parse a Responses API response into a validated route audit."""

    text = response.get("output_text")
    if not isinstance(text, str):
        text = _extract_response_text(response)
    if not isinstance(text, str) or not text.strip():
        raise MalformedRouteAuditResponse("response did not contain output text")

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise MalformedRouteAuditResponse(
            f"response was not valid JSON: {error.msg}"
        ) from error

    if not isinstance(raw, dict):
        raise MalformedRouteAuditResponse("response JSON must be an object")
    return validate_route_audit(raw)


def _extract_response_text(response: Mapping[str, Any]) -> str | None:
    output = response.get("output")
    if not isinstance(output, list):
        return None

    chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "".join(chunks) if chunks else None


class OpenAIResponsesRouteAuditor:
    """Small standard-library client for OpenAI Responses structured output."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: int = 60,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def __call__(self, record: Mapping[str, Any]) -> RouteAuditClassification:
        payload = {
            "model": self.model,
            "temperature": 0,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": build_user_prompt(record)}],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "opm_route_audit",
                    "strict": True,
                    "schema": ROUTE_AUDIT_SCHEMA,
                }
            },
        }
        response = self._post_json(payload)
        return parse_model_response(response)

    def _post_json(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib_request.Request(
            OPENAI_RESPONSES_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=self.timeout_seconds) as response:
                decoded = response.read().decode("utf-8")
        except urllib_error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RouteAuditAPIError(
                f"OpenAI API request failed with HTTP {error.code}: {detail[:500]}"
            ) from error
        except urllib_error.URLError as error:
            raise RouteAuditAPIError(f"OpenAI API request failed: {error.reason}") from error
        except TimeoutError as error:
            raise RouteAuditAPIError("OpenAI API request timed out") from error

        try:
            parsed = json.loads(decoded)
        except json.JSONDecodeError as error:
            raise MalformedRouteAuditResponse(
                f"OpenAI API returned invalid JSON: {error.msg}"
            ) from error
        if not isinstance(parsed, dict):
            raise MalformedRouteAuditResponse("OpenAI API response must be a JSON object")
        return parsed


def audit_with_retry(
    record: Mapping[str, Any],
    auditor: Auditor,
    *,
    retries: int = 1,
    sleep_seconds: float = 0.25,
) -> RouteAuditClassification:
    """Audit one record, retrying transient or malformed responses once."""

    last_error: Exception | None = None
    attempts = retries + 1
    for attempt in range(attempts):
        try:
            return auditor(record)
        except Exception as error:  # noqa: BLE001 - caller records the failure.
            last_error = error
            if attempt < attempts - 1 and sleep_seconds > 0:
                time.sleep(sleep_seconds)
    assert last_error is not None
    if isinstance(last_error, RouteAuditError):
        raise last_error
    raise RouteAuditAPIError(str(last_error)) from last_error


def _failed_fields(model: str, reason: str) -> dict[str, Any]:
    return {
        "primary_tested_concept": "",
        "is_current_topic_acceptable": False,
        "recommended_topic": "",
        "is_out_of_scope_for_current_kb": False,
        "error_type": "other",
        "evidence_sentence": "",
        "short_reason": reason[:MAX_TEXT_CHARS],
        "confidence": "low",
        "route_audit_model": model,
        "route_audit_error": reason[:MAX_TEXT_CHARS],
    }


def run_audit(
    *,
    input_path: Path,
    output_path: Path,
    summary_path: Path,
    model: str,
    limit: int | None = None,
    dry_run: bool = False,
    auditor: Auditor | None = None,
) -> RouteAuditSummary:
    """Run the optional route audit and write JSONL plus Markdown summary."""

    if limit is not None and limit < 1:
        raise DataIOError("--limit must be a positive integer when provided.")

    records = list(read_jsonl(input_path))
    selected_records = records[:limit] if limit is not None else records

    if dry_run:
        _print_dry_run(selected_records, model)
        return RouteAuditSummary(
            total_input_records=len(records),
            attempted_records=len(selected_records),
            audited_records=0,
            acceptable_topics=0,
            unacceptable_topics=0,
            out_of_scope=0,
            failed_records=0,
            skipped_missing_question=sum(
                1 for record in selected_records if _question_text(record) is None
            ),
            input_path=input_path,
            output_path=output_path,
            summary_path=summary_path,
            model=model,
            limit=limit,
            dry_run=True,
        )

    if auditor is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RouteAuditConfigurationError(
                "OPENAI_API_KEY is required unless --dry-run is used."
            )
        auditor = OpenAIResponsesRouteAuditor(api_key=api_key, model=model)

    rows: list[dict[str, Any]] = []
    audited = 0
    acceptable = 0
    out_of_scope = 0
    failed = 0
    skipped = 0
    error_type_counts: Counter[str] = Counter()

    for record in selected_records:
        row = dict(record)
        if _question_text(record) is None:
            skipped += 1
            failed += 1
            row.update(_failed_fields(model, "Missing non-empty question field."))
            rows.append(row)
            continue

        try:
            audit = audit_with_retry(record, auditor)
        except RouteAuditError as error:
            failed += 1
            row.update(_failed_fields(model, f"Route audit failed: {error}"))
        else:
            audited += 1
            if audit.is_current_topic_acceptable:
                acceptable += 1
            if audit.is_out_of_scope_for_current_kb:
                out_of_scope += 1
            error_type_counts[audit.error_type] += 1
            row.update(audit.as_record_fields(model))
        rows.append(row)

    write_jsonl(output_path, rows)

    summary = RouteAuditSummary(
        total_input_records=len(records),
        attempted_records=len(selected_records),
        audited_records=audited,
        acceptable_topics=acceptable,
        unacceptable_topics=audited - acceptable,
        out_of_scope=out_of_scope,
        failed_records=failed,
        skipped_missing_question=skipped,
        input_path=input_path,
        output_path=output_path,
        summary_path=summary_path,
        model=model,
        limit=limit,
        dry_run=False,
        error_type_counts=dict(sorted(error_type_counts.items())),
        results=rows,
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(build_summary_markdown(summary), encoding="utf-8")
    return summary


def _print_dry_run(records: Sequence[Mapping[str, Any]], model: str) -> None:
    print("Dry run only; no API call will be made and no output files will be written.")
    print(f"Model: {model}")
    if not records:
        print("No records selected.")
        return

    print("\nSystem prompt:")
    print(SYSTEM_PROMPT)
    print("\nUser prompt for first selected record:")
    print(build_user_prompt(records[0]))

    preview_count = min(3, len(records))
    print(f"\nPreviewing {preview_count} selected record(s):")
    for index, record in enumerate(records[:preview_count], start=1):
        preview = {"index": index, **record_for_prompt(record)}
        print(json.dumps(preview, ensure_ascii=False))


def build_summary_markdown(summary: RouteAuditSummary) -> str:
    """Build a compact Markdown summary for the route-audit run."""

    limit_text = str(summary.limit) if summary.limit is not None else "none"
    lines = [
        "# LLM Route Audit Summary",
        "",
        "| Field | Value |",
        "| --- | ---: |",
        f"| Input records | {summary.total_input_records} |",
        f"| Attempted records | {summary.attempted_records} |",
        f"| Audited records | {summary.audited_records} |",
        f"| Current topic acceptable | {summary.acceptable_topics} |",
        f"| Current topic unacceptable | {summary.unacceptable_topics} |",
        f"| Out of scope for current KB | {summary.out_of_scope} |",
        f"| Failed records | {summary.failed_records} |",
        f"| Skipped missing question | {summary.skipped_missing_question} |",
        "",
        "## Run Metadata",
        "",
        f"- Input: `{summary.input_path}`",
        f"- Output JSONL: `{summary.output_path}`",
        f"- Model: `{summary.model}`",
        f"- Limit: `{limit_text}`",
        "",
        "## Error Types",
        "",
    ]
    if summary.error_type_counts:
        lines.extend(["| Error type | Count |", "| --- | ---: |"])
        for error_type, count in summary.error_type_counts.items():
            lines.append(f"| {error_type} | {count} |")
    else:
        lines.append("No route-audit classifications were recorded.")

    lines.extend(
        [
            "",
            "## Scope",
            "",
            (
                "This optional LLM layer is for local audit and triage of OPM "
                "topic routing decisions. It does not generate medical answers, "
                "does not validate clinical correctness, and should not be treated "
                "as an accuracy metric."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _print_summary(summary: RouteAuditSummary) -> None:
    print(f"Read {summary.total_input_records} records from: {summary.input_path}")
    print(f"Attempted records: {summary.attempted_records}")
    if summary.dry_run:
        print("Dry run complete; no API calls were made.")
        return
    print(f"Audited: {summary.audited_records}")
    print(f"Current topic acceptable: {summary.acceptable_topics}")
    print(f"Current topic unacceptable: {summary.unacceptable_topics}")
    print(f"Out of scope for current KB: {summary.out_of_scope}")
    print(f"Failed: {summary.failed_records}")
    print(f"Skipped (missing question): {summary.skipped_missing_question}")
    print(f"Wrote results to: {summary.output_path}")
    print(f"Wrote summary report to: {summary.summary_path}")


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""

    args = _build_parser().parse_args(argv)
    try:
        summary = run_audit(
            input_path=args.input,
            output_path=args.output,
            summary_path=args.summary,
            model=args.model,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    except (DataIOError, RouteAuditConfigurationError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
