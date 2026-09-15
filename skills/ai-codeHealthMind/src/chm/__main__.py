"""``python -m chm`` -> the codehealth CLI."""

from __future__ import annotations

import sys

from .cli.main import main

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
