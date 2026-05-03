"""Test package for the OPM medical QA prototype.

Adds ``src/`` and ``scripts/`` to ``sys.path`` so individual test modules can
import the production code regardless of how the suite is invoked.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

for _subdir in ("src", "scripts"):
    _path = str(_PROJECT_ROOT / _subdir)
    if _path not in sys.path:
        sys.path.insert(0, _path)
