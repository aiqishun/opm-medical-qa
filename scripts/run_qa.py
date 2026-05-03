#!/usr/bin/env python
"""Command-line demo for the OPM medical QA prototype.

This script wires together the knowledge base loader, the rule-based reasoner,
and the text formatter. All of the actual logic lives under ``src/``; the
script itself only handles argument parsing, I/O paths, and process exit codes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DEFAULT_KNOWLEDGE_BASE = PROJECT_ROOT / "data" / "processed" / "cardiology_knowledge.json"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_io import DataIOError  # noqa: E402
from formatting import format_qa_result  # noqa: E402
from reasoning import RuleBasedCardiologyReasoner, load_topics  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the rule-based OPM cardiology question-answering demo."
    )
    parser.add_argument(
        "--question",
        required=True,
        help="Medical question to answer.",
    )
    parser.add_argument(
        "--knowledge-base",
        default=DEFAULT_KNOWLEDGE_BASE,
        type=Path,
        help="Path to the cardiology knowledge base JSON file.",
    )
    return parser


def run(question: str, knowledge_base_path: Path) -> str:
    """Answer ``question`` using ``knowledge_base_path`` and return formatted text."""

    topics = load_topics(knowledge_base_path)
    reasoner = RuleBasedCardiologyReasoner(topics=topics)
    result = reasoner.answer(question)
    return format_qa_result(result)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""

    args = _build_parser().parse_args(argv)

    try:
        output = run(args.question, args.knowledge_base)
    except DataIOError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
