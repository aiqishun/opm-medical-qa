#!/usr/bin/env python
"""Command-line demo for the OPM medical QA prototype."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


# Make the local src/ directory importable when this script is run directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DEFAULT_KNOWLEDGE_BASE = PROJECT_ROOT / "data" / "processed" / "cardiology_knowledge.json"
sys.path.insert(0, str(SRC_DIR))

from reasoning.mock_reasoner import (  # noqa: E402
    CardiologyExample,
    RuleBasedCardiologyReasoner,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Run the mock OPM cardiology question-answering demo."
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
    return parser.parse_args()


def load_knowledge_base(path: Path) -> List[CardiologyExample]:
    """Load cardiology QA examples from a JSON file."""

    with path.open("r", encoding="utf-8") as file:
        data: Dict[str, Any] = json.load(file)

    examples = data.get("examples", [])
    return [CardiologyExample.from_dict(example) for example in examples]


def main() -> None:
    """Run the demo and print a human-readable result."""

    args = parse_args()

    examples = load_knowledge_base(args.knowledge_base)
    reasoner = RuleBasedCardiologyReasoner(examples=examples)
    result = reasoner.answer(args.question)

    print("answer:")
    print(result.answer)
    print()

    print("explanation:")
    print(result.explanation)
    print()

    print("reasoning path:")
    if result.reasoning_path:
        print(" -> ".join(result.reasoning_path))
    else:
        print("(no reasoning path found)")


if __name__ == "__main__":
    main()
