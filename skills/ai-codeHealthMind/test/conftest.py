"""Compatibility shim over :mod:`helpers`.

The suite is plain ``unittest`` -- there is no pytest in this project and
``python -m unittest discover -s test`` does **not** auto-import ``conftest``.
This module therefore only re-exports the shared helpers so that a caller who
expects a ``conftest`` module (or a future pytest runner) gets the identical
surface.  ``helpers.py`` remains the single source of truth.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from helpers import (  # noqa: E402,F401
    CHMTestCase,
    ENTRY_SCRIPT,
    PROJECT_ROOT,
    SRC_DIR,
    TOOLCHAIN_ROOT,
    changed_file,
    cleanup_temp_dirs,
    cli_env,
    commit_all,
    evidence,
    git_init,
    hunk,
    make_config,
    make_ctx,
    make_finding,
    make_temp_repo,
    repo_root,
    run_cli,
    run_python,
    sample_findings,
    stage_all,
    temp_dir,
    toolchain_available,
    write_bytes,
    write_files,
)

__all__ = [
    "CHMTestCase",
    "ENTRY_SCRIPT",
    "PROJECT_ROOT",
    "SRC_DIR",
    "TOOLCHAIN_ROOT",
    "changed_file",
    "cleanup_temp_dirs",
    "cli_env",
    "commit_all",
    "evidence",
    "git_init",
    "hunk",
    "make_config",
    "make_ctx",
    "make_finding",
    "make_temp_repo",
    "repo_root",
    "run_cli",
    "run_python",
    "sample_findings",
    "stage_all",
    "temp_dir",
    "toolchain_available",
    "write_bytes",
    "write_files",
]
