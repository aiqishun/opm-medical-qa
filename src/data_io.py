"""JSON and JSONL I/O helpers with friendly error messages.

These helpers wrap the standard library so the rest of the prototype can load
knowledge bases and small datasets without rewriting the same boilerplate or
producing opaque tracebacks for missing files or malformed JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator


class DataIOError(Exception):
    """Raised when input data cannot be read or parsed."""


def read_json(path: Path) -> Any:
    """Read a JSON document from ``path``.

    Raises:
        DataIOError: if the file does not exist or contains invalid JSON.
    """

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as error:
        raise DataIOError(f"File not found: {path}") from error
    except json.JSONDecodeError as error:
        raise DataIOError(
            f"Invalid JSON in {path} at line {error.lineno}, column {error.colno}: "
            f"{error.msg}"
        ) from error


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield records from a JSONL file, one object per non-empty line.

    Raises:
        DataIOError: if the file is missing or any line contains invalid JSON.
    """

    try:
        file = path.open("r", encoding="utf-8")
    except FileNotFoundError as error:
        raise DataIOError(f"File not found: {path}") from error

    with file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise DataIOError(
                    f"Invalid JSON on line {line_number} of {path}: {error.msg}"
                ) from error

            if not isinstance(record, dict):
                raise DataIOError(
                    f"Expected a JSON object on line {line_number} of {path}, "
                    f"got {type(record).__name__}."
                )

            yield record


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    """Write ``records`` to ``path`` as JSONL and return the number written.

    Creates the parent directory if it does not exist.
    """

    path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    return count
