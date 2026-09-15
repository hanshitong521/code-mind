#!/usr/bin/env python3
"""Zero-install entry point for CodeHealthMind.

Run from anywhere::

    python codehealth.py review --diff
    python codehealth.py probe

No PYTHONPATH juggling and no third-party dependencies (ADR-001).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from chm.cli.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
