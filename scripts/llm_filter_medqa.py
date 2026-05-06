#!/usr/bin/env python
"""Optional LLM-assisted cardiology relevance filter for MedQA-style JSONL.

This script is an audit/triage aid for locally available MedQA-derived files.
It does not answer medical questions. It asks an OpenAI model whether the main
tested concept of each question is cardiology-related, with special attention
to cases where cardiac terms appear only as past medical history.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib import error as urllib_error
from urllib import request as urllib_request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DEFAULT_INPUT = (
    PROJECT_ROOT / "data" / "processed" / "medqa_cardiology_real_high_confidence.jsonl"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data" / "processed" / "medqa_cardiology_llm_filtered.jsonl"
)
DEFAULT_RELEVANT_OUTPUT = (
    PROJECT_ROOT / "data" / "processed" / "medqa_cardiology_llm_relevant.jsonl"
)
DEFAULT_SUMMARY = PROJECT_ROOT / "experiments" / "results" / "llm_filter_summary.md"
DEFAULT_MODEL = "gpt-4o-mini"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
MAX_REASON_CHARS = 320

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_io import DataIOError, read_jsonl, write_jsonl  # noqa: E402


SYSTEM_PROMPT = """\
You are a careful medical-dataset triage assistant. Your task is only to
classify question-topic relevance, not to answer the question or provide
medical advice.

Classify whether the question's main tested concept is cardiology-related.
Treat cardiology terms in past medical history, medication lists, vital signs,
or incidental context as incidental unless the question is testing a cardiac
diagnosis, mechanism, investigation, treatment, physiology, complication, or
prevention concept.
"""

USER_PROMPT_TEMPLATE = """\
Classify the following MedQA-style record.

Return a structured JSON object with:
- llm_is_cardiology_relevant: true only when the main tested concept is cardiology-related
- llm_primary_topic: short topic string, or null if non-cardiology/unclear
- llm_confidence: one of low, medium, high
- llm_is_incidental_history_only: true when cardiac terms appear only in past history or incidental context
- llm_reason: one short sentence explaining the judgment

Record:
{record_json}
"""

CLASSIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "llm_is_cardiology_relevant": {"type": "boolean"},
        "llm_primary_topic": {"type": ["string", "null"]},
        "llm_confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "llm_is_incidental_history_only": {"type": "boolean"},
        "llm_reason": {"type": "string"},
    },
    "required": [
        "llm_is_cardiology_relevant",
        "llm_primary_topic",
        "llm_confidence",
        "llm_is_incidental_history_only",
        "llm_reason",
    ],
}


class LLMFilterError(Exception):
    """Base error for LLM filtering failures."""


class LLMConfigurationError(LLMFilterError):
    """Raised when required local configuration is missing."""


class LLMAPIError(LLMFilterError):
    """Raised when the model API request fails."""


class MalformedModelResponse(LLMFilterError):
    """Raised when the model response cannot be parsed or validated."""


@dataclass(frozen=True)
class LLMClassification:
    """Validated classification fields written back to each JSONL row."""

    llm_is_cardiology_relevant: bool
    llm_primary_topic: str | None
    llm_confidence: str
    llm_is_incidental_history_only: bool
    llm_reason: str

    def as_record_fields(self, model: str) -> dict[str, Any]:
        return {
            "llm_is_cardiology_relevant": self.llm_is_cardiology_relevant,
            "llm_primary_topic": self.llm_primary_topic,
            "llm_confidence": self.llm_confidence,
            "llm_is_incidental_history_only": self.llm_is_incidental_history_only,
            "llm_reason": self.llm_reason,
            "llm_model": model,
        }


@dataclass(frozen=True)
class LLMFilterSummary:
    """Counts returned by :func:`run_filter` for end-of-run reporting."""

    total_input_records: int
    attempted_records: int
    classified_records: int
    cardiology_relevant: int
    incidental_history_only: int
    failed_records: int
    skipped_missing_question: int
    input_path: Path
    output_path: Path
    summary_path: Path
    model: str
    relevant_output_path: Path | None = None
    relevant_only_written: int = 0
    limit: int | None = None
    dry_run: bool = False
    results: list[dict[str, Any]] = field(default_factory=list)


Classifier = Callable[[Mapping[str, Any]], LLMClassification]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Optionally apply an OpenAI model as a second-stage cardiology "
            "relevance classifier over a local MedQA-derived JSONL file."
        )
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        type=Path,
        help=(
            "Input JSONL file. Defaults to "
            "data/processed/medqa_cardiology_real_high_confidence.jsonl."
        ),
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        type=Path,
        help=(
            "Output JSONL file with LLM classification metadata. Defaults to "
            "data/processed/medqa_cardiology_llm_filtered.jsonl."
        ),
    )
    parser.add_argument(
        "--summary",
        default=DEFAULT_SUMMARY,
        type=Path,
        help=(
            "Markdown summary path. Defaults to "
            "experiments/results/llm_filter_summary.md."
        ),
    )
    parser.add_argument(
        "--relevant-output",
        default=None,
        type=Path,
        metavar="PATH",
        help=(
            "Optional JSONL file that receives only rows where "
            "llm_is_cardiology_relevant is true and "
            "llm_is_incidental_history_only is false. Example: "
            f"{DEFAULT_RELEVANT_OUTPUT.relative_to(PROJECT_ROOT)}."
        ),
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
    """Return the minimal record fields sent to the model."""

    prompt_record: dict[str, Any] = {"question": _question_text(record)}
    for key in ("options", "matched_terms", "filter_confidence", "id"):
        if key in record:
            prompt_record[key] = record[key]
    return prompt_record


def build_user_prompt(record: Mapping[str, Any]) -> str:
    """Build the user prompt for one JSONL record."""

    record_json = json.dumps(record_for_prompt(record), ensure_ascii=False, indent=2)
    return USER_PROMPT_TEMPLATE.format(record_json=record_json)


def validate_classification(raw: Mapping[str, Any]) -> LLMClassification:
    """Validate a decoded model JSON object."""

    missing = [key for key in CLASSIFICATION_SCHEMA["required"] if key not in raw]
    if missing:
        raise MalformedModelResponse(f"missing required field(s): {', '.join(missing)}")

    if not isinstance(raw["llm_is_cardiology_relevant"], bool):
        raise MalformedModelResponse("llm_is_cardiology_relevant must be boolean")
    if not isinstance(raw["llm_is_incidental_history_only"], bool):
        raise MalformedModelResponse("llm_is_incidental_history_only must be boolean")

    primary_topic = raw["llm_primary_topic"]
    if primary_topic is not None and not isinstance(primary_topic, str):
        raise MalformedModelResponse("llm_primary_topic must be string or null")
    if isinstance(primary_topic, str):
        primary_topic = primary_topic.strip() or None

    confidence = raw["llm_confidence"]
    if confidence not in {"low", "medium", "high"}:
        raise MalformedModelResponse("llm_confidence must be low, medium, or high")

    reason = raw["llm_reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise MalformedModelResponse("llm_reason must be a non-empty string")

    return LLMClassification(
        llm_is_cardiology_relevant=raw["llm_is_cardiology_relevant"],
        llm_primary_topic=primary_topic,
        llm_confidence=confidence,
        llm_is_incidental_history_only=raw["llm_is_incidental_history_only"],
        llm_reason=reason.strip()[:MAX_REASON_CHARS],
    )


def parse_model_response(response: Mapping[str, Any]) -> LLMClassification:
    """Parse a Responses API response into a validated classification."""

    text = response.get("output_text")
    if not isinstance(text, str):
        text = _extract_response_text(response)
    if not isinstance(text, str) or not text.strip():
        raise MalformedModelResponse("response did not contain output text")

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise MalformedModelResponse(f"response was not valid JSON: {error.msg}") from error

    if not isinstance(raw, dict):
        raise MalformedModelResponse("response JSON must be an object")
    return validate_classification(raw)


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


class OpenAIResponsesClassifier:
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

    def __call__(self, record: Mapping[str, Any]) -> LLMClassification:
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
                    "name": "cardiology_filter_classification",
                    "strict": True,
                    "schema": CLASSIFICATION_SCHEMA,
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
            raise LLMAPIError(
                f"OpenAI API request failed with HTTP {error.code}: {detail[:500]}"
            ) from error
        except urllib_error.URLError as error:
            raise LLMAPIError(f"OpenAI API request failed: {error.reason}") from error
        except TimeoutError as error:
            raise LLMAPIError("OpenAI API request timed out") from error

        try:
            parsed = json.loads(decoded)
        except json.JSONDecodeError as error:
            raise MalformedModelResponse(
                f"OpenAI API returned invalid JSON: {error.msg}"
            ) from error
        if not isinstance(parsed, dict):
            raise MalformedModelResponse("OpenAI API response must be a JSON object")
        return parsed


def classify_with_retry(
    record: Mapping[str, Any],
    classifier: Classifier,
    *,
    retries: int = 1,
    sleep_seconds: float = 0.25,
) -> LLMClassification:
    """Classify one record, retrying transient or malformed responses once."""

    last_error: Exception | None = None
    attempts = retries + 1
    for attempt in range(attempts):
        try:
            return classifier(record)
        except Exception as error:  # noqa: BLE001 - caller records the failure.
            last_error = error
            if attempt < attempts - 1 and sleep_seconds > 0:
                time.sleep(sleep_seconds)
    assert last_error is not None
    if isinstance(last_error, LLMFilterError):
        raise last_error
    raise LLMAPIError(str(last_error)) from last_error


def _failed_fields(model: str, reason: str) -> dict[str, Any]:
    return {
        "llm_is_cardiology_relevant": False,
        "llm_primary_topic": None,
        "llm_confidence": "low",
        "llm_is_incidental_history_only": False,
        "llm_reason": reason[:MAX_REASON_CHARS],
        "llm_model": model,
        "llm_error": reason[:MAX_REASON_CHARS],
    }


def run_filter(
    *,
    input_path: Path,
    output_path: Path,
    summary_path: Path,
    model: str,
    relevant_output_path: Path | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    classifier: Classifier | None = None,
) -> LLMFilterSummary:
    """Run the optional LLM filter and write JSONL plus Markdown summary."""

    if limit is not None and limit < 1:
        raise DataIOError("--limit must be a positive integer when provided.")

    records = list(read_jsonl(input_path))
    selected_records = records[:limit] if limit is not None else records

    if dry_run:
        _print_dry_run(selected_records, model)
        return LLMFilterSummary(
            total_input_records=len(records),
            attempted_records=len(selected_records),
            classified_records=0,
            cardiology_relevant=0,
            incidental_history_only=0,
            failed_records=0,
            skipped_missing_question=sum(
                1 for record in selected_records if _question_text(record) is None
            ),
            input_path=input_path,
            output_path=output_path,
            summary_path=summary_path,
            model=model,
            relevant_output_path=relevant_output_path,
            limit=limit,
            dry_run=True,
            results=[],
        )

    if classifier is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LLMConfigurationError(
                "OPENAI_API_KEY is required unless --dry-run is used."
            )
        classifier = OpenAIResponsesClassifier(api_key=api_key, model=model)

    rows: list[dict[str, Any]] = []
    classified = 0
    relevant = 0
    incidental = 0
    failed = 0
    skipped = 0

    for record in selected_records:
        row = dict(record)
        if _question_text(record) is None:
            skipped += 1
            failed += 1
            row.update(_failed_fields(model, "Missing non-empty question field."))
            rows.append(row)
            continue

        try:
            classification = classify_with_retry(record, classifier)
        except LLMFilterError as error:
            failed += 1
            row.update(_failed_fields(model, f"LLM classification failed: {error}"))
        else:
            classified += 1
            if classification.llm_is_cardiology_relevant:
                relevant += 1
            if classification.llm_is_incidental_history_only:
                incidental += 1
            row.update(classification.as_record_fields(model))
        rows.append(row)

    write_jsonl(output_path, rows)
    relevant_rows = relevant_only_records(rows)
    relevant_only_written = 0
    if relevant_output_path is not None:
        relevant_only_written = write_jsonl(relevant_output_path, relevant_rows)

    summary = LLMFilterSummary(
        total_input_records=len(records),
        attempted_records=len(selected_records),
        classified_records=classified,
        cardiology_relevant=relevant,
        incidental_history_only=incidental,
        failed_records=failed,
        skipped_missing_question=skipped,
        input_path=input_path,
        output_path=output_path,
        summary_path=summary_path,
        model=model,
        relevant_output_path=relevant_output_path,
        relevant_only_written=relevant_only_written,
        limit=limit,
        dry_run=False,
        results=rows,
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(build_summary_markdown(summary), encoding="utf-8")
    return summary


def relevant_only_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return rows classified as cardiology-relevant and not incidental history."""

    return [
        dict(record)
        for record in records
        if record.get("llm_is_cardiology_relevant") is True
        and record.get("llm_is_incidental_history_only") is False
    ]


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
        print(json.dumps({"index": index, **record_for_prompt(record)}, ensure_ascii=False))


def build_summary_markdown(summary: LLMFilterSummary) -> str:
    """Build a compact Markdown summary for the LLM filtering run."""

    limit_text = str(summary.limit) if summary.limit is not None else "none"
    relevant_output_text = (
        f"`{summary.relevant_output_path}`"
        if summary.relevant_output_path is not None
        else "not requested"
    )
    lines = [
        "# LLM Cardiology Filter Summary",
        "",
        "| Field | Value |",
        "| --- | ---: |",
        f"| Input records | {summary.total_input_records} |",
        f"| Attempted records | {summary.attempted_records} |",
        f"| Classified records | {summary.classified_records} |",
        f"| Cardiology relevant | {summary.cardiology_relevant} |",
        f"| Incidental history only | {summary.incidental_history_only} |",
        f"| Failed records | {summary.failed_records} |",
        f"| Skipped missing question | {summary.skipped_missing_question} |",
        f"| Relevant-only records written | {summary.relevant_only_written} |",
        "",
        "## Run Metadata",
        "",
        f"- Input: `{summary.input_path}`",
        f"- Output JSONL: `{summary.output_path}`",
        f"- Relevant-only output JSONL: {relevant_output_text}",
        f"- Model: `{summary.model}`",
        f"- Limit: `{limit_text}`",
        "",
        "## Scope",
        "",
        (
            "This optional LLM layer is for local audit and triage of "
            "MedQA-derived candidate rows. It does not generate medical answers, "
            "does not validate clinical correctness, and should not be treated as "
            "an accuracy metric."
        ),
    ]
    return "\n".join(lines) + "\n"


def _print_summary(summary: LLMFilterSummary) -> None:
    print(f"Read {summary.total_input_records} records from: {summary.input_path}")
    print(f"Attempted records: {summary.attempted_records}")
    if summary.dry_run:
        print("Dry run complete; no API calls were made.")
        return
    print(f"Classified: {summary.classified_records}")
    print(f"Cardiology relevant: {summary.cardiology_relevant}")
    print(f"Incidental history only: {summary.incidental_history_only}")
    print(f"Failed: {summary.failed_records}")
    print(f"Skipped (missing question): {summary.skipped_missing_question}")
    print(f"Wrote results to: {summary.output_path}")
    if summary.relevant_output_path is not None:
        print(f"Relevant-only records written: {summary.relevant_only_written}")
        print(f"Wrote relevant-only results to: {summary.relevant_output_path}")
    print(f"Wrote summary report to: {summary.summary_path}")


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""

    args = _build_parser().parse_args(argv)
    try:
        summary = run_filter(
            input_path=args.input,
            output_path=args.output,
            summary_path=args.summary,
            model=args.model,
            relevant_output_path=args.relevant_output,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    except (DataIOError, LLMConfigurationError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
