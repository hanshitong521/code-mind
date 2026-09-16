"""Small, dependency-free helpers shared by the whole engine.

Everything here is stdlib-only on purpose: the gate must run in a bare CI
container with nothing installed but Python (ADR-001).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Sequence

# --------------------------------------------------------------------------
# hashing / ids
# --------------------------------------------------------------------------


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path | str) -> str:
    """Content hash of a file; missing file hashes to a stable sentinel."""
    p = Path(path)
    try:
        return sha256_bytes(p.read_bytes())
    except OSError:
        return "sha256:missing"


def stable_json(obj: Any) -> str:
    """Deterministic JSON -- key order and separators fixed.

    Required so that two runs over the same input produce byte-identical
    reports (spec §41 Determinism).
    """
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def short_hash(*parts: str, length: int = 12) -> str:
    return sha256_text("\x00".join(parts))[:length]


def now_ms() -> int:
    return int(time.time() * 1000)


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


@dataclass
class Timer:
    """Context manager recording wall-clock duration in milliseconds."""

    started_at: float = 0.0
    duration_ms: int = 0

    def __enter__(self) -> "Timer":
        self.started_at = time.perf_counter()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.duration_ms = int((time.perf_counter() - self.started_at) * 1000)


# --------------------------------------------------------------------------
# process execution
# --------------------------------------------------------------------------


@dataclass
class CmdResult:
    """Outcome of a real subprocess invocation."""

    argv: Sequence[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    launch_error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.launch_error is None and not self.timed_out and self.exit_code == 0

    @property
    def command_line(self) -> str:
        return " ".join(_quote(a) for a in self.argv)


def _quote(arg: str) -> str:
    if arg == "" or re.search(r"[\s\"'&|<>^]", arg):
        return '"' + arg.replace('"', '\\"') + '"'
    return arg


def run_cmd(
    argv: Sequence[str],
    *,
    cwd: Optional[Path | str] = None,
    timeout_s: float = 120.0,
    env: Optional[dict[str, str]] = None,
    input_text: Optional[str] = None,
    max_output_bytes: int = 32 * 1024 * 1024,
) -> CmdResult:
    """Run a real command, always returning -- never raising.

    On Windows the whole process tree is killed on timeout, otherwise a JVM
    child would keep the pipe open and hang the caller.
    """
    argv = [str(a) for a in argv]
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    merged_env.setdefault("PYTHONIOENCODING", "utf-8")

    started = time.perf_counter()
    creationflags = 0
    if sys.platform == "win32":  # pragma: no cover - platform specific
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd) if cwd else None,
            env=merged_env,
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )
    except (OSError, ValueError) as exc:
        return CmdResult(
            argv=argv,
            exit_code=-1,
            stdout="",
            stderr="",
            duration_ms=int((time.perf_counter() - started) * 1000),
            launch_error=f"{type(exc).__name__}: {exc}",
        )

    timed_out = False
    try:
        out_b, err_b = proc.communicate(
            input=input_text.encode("utf-8") if input_text is not None else None,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        try:
            out_b, err_b = proc.communicate(timeout=10)
        except Exception:  # pragma: no cover - defensive
            out_b, err_b = b"", b""

    duration = int((time.perf_counter() - started) * 1000)
    return CmdResult(
        argv=argv,
        exit_code=proc.returncode if proc.returncode is not None else -1,
        stdout=_decode(out_b[:max_output_bytes]),
        stderr=_decode(err_b[:max_output_bytes]),
        duration_ms=duration,
        timed_out=timed_out,
    )


def _kill_tree(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":  # pragma: no cover
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=15,
            )
            return
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def which(name: str, extra_paths: Iterable[Path | str] = ()) -> Optional[str]:
    """Locate an executable, honouring extra search roots."""
    found = shutil.which(name)
    if found:
        return found
    exts = [""]
    if sys.platform == "win32":  # pragma: no cover
        exts = [".exe", ".cmd", ".bat", ".ps1", ""]
    for root in extra_paths:
        root = Path(root)
        for ext in exts:
            cand = root / f"{name}{ext}"
            if cand.is_file():
                return str(cand)
    return None


# --------------------------------------------------------------------------
# paths / files
# --------------------------------------------------------------------------

DEFAULT_EXCLUDES = (
    ".git",
    ".hg",
    ".svn",
    ".codehealth",
    "node_modules",
    "target",
    "build",
    "dist",
    "out",
    ".venv",
    "venv",
    "__pycache__",
    ".mvn",
    ".gradle",
    ".idea",
    ".vscode",
    "coverage",
    ".next",
)


def is_binary_bytes(sample: bytes) -> bool:
    if b"\x00" in sample:
        return True
    if not sample:
        return False
    text_chars = sum(1 for b in sample if 9 <= b <= 13 or 32 <= b <= 126 or b >= 128)
    return (text_chars / len(sample)) < 0.70


def is_binary_file(path: Path, sample_size: int = 4096) -> bool:
    try:
        with path.open("rb") as fh:
            return is_binary_bytes(fh.read(sample_size))
    except OSError:
        return True


def iter_files(
    root: Path,
    *,
    suffixes: Optional[Iterable[str]] = None,
    excludes: Iterable[str] = DEFAULT_EXCLUDES,
    max_bytes: Optional[int] = None,
    follow_symlinks: bool = False,
) -> Iterator[Path]:
    """Deterministic, sorted walk that skips vendor/build dirs."""
    root = Path(root)
    exclude_set = set(excludes)
    suffix_set = {s.lower() for s in suffixes} if suffixes else None
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        dirnames[:] = sorted(d for d in dirnames if d not in exclude_set)
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if suffix_set is not None and p.suffix.lower() not in suffix_set:
                continue
            if max_bytes is not None:
                try:
                    if p.stat().st_size > max_bytes:
                        continue
                except OSError:
                    continue
            results.append(p)
    yield from results


def read_text(path: Path | str, *, max_bytes: int = 8 * 1024 * 1024) -> str:
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError:
        return ""
    return _decode(data[:max_bytes])


def read_lines(path: Path | str) -> list[str]:
    """Read preserving original line ending semantics (split on \\n only)."""
    return read_text(path).replace("\r\n", "\n").replace("\r", "\n").split("\n")


def relpath(path: Path | str, root: Path | str) -> str:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except (ValueError, OSError):
        return Path(path).as_posix()


def ensure_dir(path: Path | str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: Path | str, obj: Any) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path | str, default: Any = None) -> Any:
    p = Path(path)
    if not p.is_file():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


# --------------------------------------------------------------------------
# text
# --------------------------------------------------------------------------

_WS = re.compile(r"[ \t]+")


def normalize_ws(text: str) -> str:
    return _WS.sub(" ", text).strip()


def strip_comments_and_strings(code: str, line_comment: str = "//") -> str:
    """Crude but deterministic comment/string stripper.

    Used only to reduce false positives in *pattern* analyzers; it is not a
    parser and never claims to be one.
    """
    out: list[str] = []
    i = 0
    n = len(code)
    in_str: Optional[str] = None
    in_line_comment = False
    in_block_comment = False
    while i < n:
        ch = code[i]
        nxt = code[i + 1] if i + 1 < n else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            else:
                out.append(" ")
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                out.append("  ")
                i += 2
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if in_str:
            if ch == "\\":
                out.append("  ")
                i += 2
                continue
            if ch == in_str:
                in_str = None
            out.append(" " if ch != "\n" else "\n")
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            out.append(" ")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def percent(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(100.0 * numerator / denominator, 2)
