"""Export OPM-style graphs as machine-readable JSON.

Exported graphs are research artifacts produced by this prototype's rule-based
reasoner. They are not curated clinical knowledge graphs and must not be used
for clinical decision-making.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from graph.opm_graph import OPMGraph


class GraphExportError(Exception):
    """Raised when an OPM graph cannot be written to disk."""


def export_graph(graph: OPMGraph, path: Path, *, indent: int = 2) -> Path:
    """Write ``graph`` to ``path`` as JSON and return the path.

    Creates parent directories as needed. Writes via a temporary file in the
    same directory and atomically renames into place so a failed write cannot
    leave a half-written file at ``path``.

    Raises:
        GraphExportError: if the destination cannot be written.
    """

    path = Path(path)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise GraphExportError(
            f"Could not create directory {path.parent}: {error}"
        ) from error

    payload = json.dumps(graph.to_dict(), ensure_ascii=False, indent=indent)

    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=path.parent
        )
    except OSError as error:
        raise GraphExportError(
            f"Could not create a temporary file in {path.parent}: {error}"
        ) from error

    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
        os.replace(tmp_path, path)
    except OSError as error:
        tmp_path.unlink(missing_ok=True)
        raise GraphExportError(f"Could not write graph to {path}: {error}") from error

    return path
