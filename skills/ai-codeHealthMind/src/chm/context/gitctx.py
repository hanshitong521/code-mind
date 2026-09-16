"""Git-backed change-set resolution -- spec §7.

Everything in this module is **read-only**.  Only ``rev-parse``, ``status``,
``diff``, ``diff-tree``, ``show``, ``ls-files`` and ``cat-file`` style
plumbing is ever invoked; no command here may mutate the repository.

Two properties are load bearing for the rest of the gate:

* **determinism** -- the returned list is sorted by path and no timestamp ever
  enters a hash;
* **honesty** -- when a mode cannot be honoured the failure is raised as a
  :class:`~chm.errors.GitError` (or reported as an explicit ``degraded`` marker
  in the run metadata), never swallowed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..config import Config
from ..contracts import ChangeKind, ChangedFile, Hunk, ReviewMode, ScanContext, language_of
from ..errors import ContextError, GitError
from ..util import (
    CmdResult,
    ensure_dir,
    file_hash,
    is_binary_file,
    iter_files,
    relpath,
    run_cmd,
    short_hash,
)

__all__ = [
    "GitInfo",
    "probe_repo",
    "resolve_context",
    "resolve_changed_files",
    "parse_unified_diff",
    "file_at_rev",
    "changed_line_text",
]


#: Known source suffixes, used when walking a non-git tree.
SOURCE_SUFFIXES = (
    ".java",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".vue",
    ".json",
    ".yml",
    ".yaml",
    ".xml",
    ".sql",
    ".md",
    ".properties",
    ".gradle",
)

#: ``git -c ...`` prefix; colour and path quoting must never leak into parsing.
_GIT_OPTS = ["-c", "color.ui=false", "-c", "core.quotepath=false"]

_STATUS_KIND = {
    "A": ChangeKind.ADDED,
    "D": ChangeKind.DELETED,
    "M": ChangeKind.MODIFIED,
    "R": ChangeKind.RENAMED,
    "C": ChangeKind.COPIED,
    "T": ChangeKind.MODIFIED,
    "U": ChangeKind.MODIFIED,
    "X": ChangeKind.UNKNOWN,
}

_DIFF_GIT_RE = re.compile(r"^diff --git a/(?P<a>.*) b/(?P<b>.*)$")
_HUNK_RE = re.compile(
    r"^@@ -(?P<os>\d+)(?:,(?P<oc>\d+))? \+(?P<ns>\d+)(?:,(?P<nc>\d+))? @@(?P<hdr>.*)$"
)


# --------------------------------------------------------------------------
# repository probe
# --------------------------------------------------------------------------


@dataclass
class GitInfo:
    """Cheap, always-available facts about the repository we are auditing."""

    repo_root: Path
    head_sha: str
    branch: Optional[str]
    dirty: bool
    is_git: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_root": str(self.repo_root),
            "head_sha": self.head_sha,
            "branch": self.branch,
            "dirty": self.dirty,
            "is_git": self.is_git,
        }


def _run_git(root: Path, args: list[str], *, timeout_s: float = 120.0) -> CmdResult:
    return run_cmd(["git", *_GIT_OPTS, *args], cwd=root, timeout_s=timeout_s)


def _git_or_raise(root: Path, args: list[str], what: str, *, timeout_s: float = 120.0) -> CmdResult:
    res = _run_git(root, args, timeout_s=timeout_s)
    if res.launch_error:
        raise GitError(
            f"could not launch git for {what}: {res.launch_error}",
            command=res.command_line,
            repo_root=str(root),
        )
    if res.timed_out:
        raise GitError(
            f"git {what} timed out after {timeout_s:.0f}s",
            command=res.command_line,
            repo_root=str(root),
        )
    if not res.ok:
        raise GitError(
            f"git {what} failed with exit code {res.exit_code}",
            command=res.command_line,
            exit_code=res.exit_code,
            stderr=res.stderr.strip()[:4000],
            repo_root=str(root),
        )
    return res


def probe_repo(repo_root: Path) -> GitInfo:
    """Describe ``repo_root`` without ever mutating it.

    Uses exactly two git invocations in the normal case: ``rev-parse
    --show-toplevel`` and ``status --porcelain=v2 --branch``.  Spawning git is
    the single most expensive thing this module does, so it is kept minimal.
    """
    root = Path(repo_root).resolve()
    top = _run_git(root, ["rev-parse", "--show-toplevel"], timeout_s=30.0)
    if top.launch_error or not top.ok or not top.stdout.strip():
        return GitInfo(repo_root=root, head_sha="", branch=None, dirty=False, is_git=False)

    toplevel = top.stdout.strip().splitlines()[-1].strip()
    try:
        resolved = Path(toplevel).resolve()
    except OSError:
        resolved = root

    head_sha = ""
    branch: Optional[str] = None
    dirty = False

    st = _run_git(resolved, ["status", "--porcelain=v2", "--branch"], timeout_s=120.0)
    if st.ok:
        for raw in st.stdout.split("\n"):
            line = _strip_cr(raw)
            if line.startswith("# branch.oid "):
                value = line[len("# branch.oid "):].strip()
                head_sha = "" if value == "(initial)" else value
            elif line.startswith("# branch.head "):
                value = line[len("# branch.head "):].strip()
                branch = None if value in ("(detached)", "HEAD") else value
            elif line and not line.startswith("#"):
                dirty = True
    else:  # very old git: fall back to the classic porcelain output
        st2 = _run_git(resolved, ["status", "--porcelain"], timeout_s=120.0)
        dirty = bool(st2.ok and st2.stdout.strip())
        head = _run_git(resolved, ["rev-parse", "--verify", "HEAD"], timeout_s=30.0)
        head_sha = head.stdout.strip().splitlines()[0].strip() if head.ok and head.stdout.strip() else ""
        br = _run_git(resolved, ["rev-parse", "--abbrev-ref", "HEAD"], timeout_s=30.0)
        branch = br.stdout.strip() if br.ok and br.stdout.strip() else None
        if branch == "HEAD":
            branch = None

    return GitInfo(repo_root=resolved, head_sha=head_sha, branch=branch, dirty=dirty, is_git=True)


# --------------------------------------------------------------------------
# unified diff parsing
# --------------------------------------------------------------------------


def _strip_cr(line: str) -> str:
    return line[:-1] if line.endswith("\r") else line


def _strip_ab(raw: Optional[str]) -> Optional[str]:
    """``a/foo`` / ``b/foo`` -> ``foo``; ``/dev/null`` -> ``None``."""
    if raw is None:
        return None
    value = raw.strip()
    if not value or value == "/dev/null":
        return None
    if value.startswith("a/") or value.startswith("b/"):
        value = value[2:]
    return value.replace("\\", "/") or None


def parse_unified_diff(diff_text: str, *, repo_root: Path, config: Config) -> list[ChangedFile]:
    """Turn ``git diff`` output into :class:`ChangedFile` objects.

    Handles ``new file mode`` / ``deleted file mode`` / ``rename from|to`` /
    ``copy from|to`` / ``similarity index`` / ``Binary files ... differ`` /
    ``\\ No newline at end of file``, CRLF and LF alike.
    """
    root = Path(repo_root)
    files: list[ChangedFile] = []
    cur: Optional[dict[str, Any]] = None
    hunks: list[Hunk] = []
    hunk: Optional[Hunk] = None
    in_hunk = False
    old_used = 0
    new_used = 0

    def flush() -> None:
        nonlocal cur, hunks, hunk, in_hunk, old_used, new_used
        if cur is not None:
            cf = _build_changed_file(cur, hunks, root, config)
            if cf is not None:
                files.append(cf)
        cur = None
        hunks = []
        hunk = None
        in_hunk = False
        old_used = 0
        new_used = 0

    for raw_line in diff_text.split("\n"):
        line = _strip_cr(raw_line)

        if in_hunk and hunk is not None:
            if line.startswith("\\"):
                hunk.lines.append(line)
                continue
            if old_used < hunk.old_count or new_used < hunk.new_count:
                hunk.lines.append(line)
                marker = line[:1]
                if marker == "+":
                    new_used += 1
                elif marker == "-":
                    old_used += 1
                else:
                    old_used += 1
                    new_used += 1
                continue
            in_hunk = False  # fall through to header handling

        if line.startswith("diff --git "):
            flush()
            rest = line[len("diff --git "):]
            m = _DIFF_GIT_RE.match(line)
            cur = {
                "a_path": m.group("a") if m else None,
                "b_path": m.group("b") if m else None,
                "old_hdr": None,
                "new_hdr": None,
                "rename_from": None,
                "rename_to": None,
                "copy_from": None,
                "copy_to": None,
                "new_file": False,
                "deleted_file": False,
                "binary": False,
            }
            if m is None and rest:
                cur["a_path"] = rest
                cur["b_path"] = rest
            continue

        if cur is None:
            continue

        if line.startswith("new file mode"):
            cur["new_file"] = True
        elif line.startswith("deleted file mode"):
            cur["deleted_file"] = True
        elif line.startswith("rename from "):
            cur["rename_from"] = line[len("rename from "):].strip()
        elif line.startswith("rename to "):
            cur["rename_to"] = line[len("rename to "):].strip()
        elif line.startswith("copy from "):
            cur["copy_from"] = line[len("copy from "):].strip()
        elif line.startswith("copy to "):
            cur["copy_to"] = line[len("copy to "):].strip()
        elif line.startswith("Binary files ") or line.startswith("GIT binary patch"):
            cur["binary"] = True
        elif line.startswith("--- "):
            cur["old_hdr"] = line[4:]
        elif line.startswith("+++ "):
            cur["new_hdr"] = line[4:]
        elif line.startswith("@@"):
            m = _HUNK_RE.match(line)
            if m is None:
                raise ContextError(
                    "malformed unified-diff hunk header",
                    header=line[:200],
                    file=cur.get("b_path") or cur.get("a_path"),
                )
            hunk = Hunk(
                old_start=int(m.group("os")),
                old_count=int(m.group("oc")) if m.group("oc") is not None else 1,
                new_start=int(m.group("ns")),
                new_count=int(m.group("nc")) if m.group("nc") is not None else 1,
                header=m.group("hdr").strip(),
                lines=[],
            )
            hunks.append(hunk)
            in_hunk = True
            old_used = 0
            new_used = 0
        # everything else (index/similarity/dissimilarity/mode lines) is noise

    flush()
    files.sort(key=lambda f: f.path)
    return files


def _build_changed_file(
    cur: dict[str, Any], hunks: list[Hunk], root: Path, config: Config
) -> Optional[ChangedFile]:
    old_path = cur["rename_from"] or cur["copy_from"] or _strip_ab(cur["old_hdr"]) or cur["a_path"]
    new_path = cur["rename_to"] or cur["copy_to"] or _strip_ab(cur["new_hdr"]) or cur["b_path"]
    if cur["new_file"]:
        old_path = None
    if cur["deleted_file"]:
        new_path = None

    path = new_path or old_path
    if not path:
        return None
    path = path.replace("\\", "/")
    if config.is_excluded(path):
        return None

    if cur["new_file"]:
        kind = ChangeKind.ADDED
    elif cur["deleted_file"]:
        kind = ChangeKind.DELETED
    elif cur["rename_from"] and cur["rename_to"]:
        kind = ChangeKind.RENAMED
    elif cur["copy_from"] and cur["copy_to"]:
        kind = ChangeKind.COPIED
    elif old_path and new_path and old_path != new_path:
        kind = ChangeKind.RENAMED
    else:
        kind = ChangeKind.MODIFIED

    added = sum(1 for h in hunks for ln in h.lines if ln[:1] == "+")
    removed = sum(1 for h in hunks for ln in h.lines if ln[:1] == "-")

    full = root / path
    exists = full.is_file()
    size = 0
    if exists:
        try:
            size = full.stat().st_size
        except OSError:
            size = 0
    binary = bool(cur["binary"]) or (exists and is_binary_file(full))

    return ChangedFile(
        path=path,
        change_kind=kind,
        old_path=old_path if old_path and old_path != path else None,
        language=language_of(path),
        added_lines=added,
        removed_lines=removed,
        is_binary=binary,
        is_generated=config.is_generated(path),
        size_bytes=size,
        content_hash=file_hash(full),
        hunks=hunks,
    )


def changed_line_text(cf: ChangedFile) -> list[tuple[int, str]]:
    """``[(new_line_number, text)]`` for every added line of a changed file."""
    out: list[tuple[int, str]] = []
    for h in cf.hunks:
        lineno = h.new_start
        for line in h.lines:
            marker = line[:1]
            if marker == "+":
                out.append((lineno, line[1:]))
                lineno += 1
            elif marker == "-":
                continue
            elif marker == "\\":
                continue
            else:
                lineno += 1
    return out


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _parse_name_status(text: str) -> list[tuple[ChangeKind, str, Optional[str]]]:
    """``git diff --name-status`` output -> ``[(kind, path, old_path)]``."""
    out: list[tuple[ChangeKind, str, Optional[str]]] = []
    for raw in text.split("\n"):
        line = _strip_cr(raw)
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        code = parts[0].strip()
        letter = code[:1].upper()
        if letter in ("R", "C") and len(parts) >= 3:
            kind = ChangeKind.RENAMED if letter == "R" else ChangeKind.COPIED
            out.append((kind, parts[2].replace("\\", "/"), parts[1].replace("\\", "/")))
        else:
            out.append((_STATUS_KIND.get(letter, ChangeKind.UNKNOWN), parts[1].replace("\\", "/"), None))
    return out


def _make_entry(
    root: Path, config: Config, path: str, kind: ChangeKind, old_path: Optional[str] = None
) -> Optional[ChangedFile]:
    if config.is_excluded(path):
        return None
    full = root / path
    exists = full.is_file()
    size = 0
    added_lines = 0
    removed_lines = 0
    is_binary = exists and is_binary_file(full)
    if exists:
        try:
            size = full.stat().st_size
        except OSError:
            size = 0
        if not is_binary and kind is ChangeKind.ADDED:
            try:
                text = full.read_text(encoding="utf-8", errors="replace")
                added_lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
            except OSError:
                added_lines = 0
    return ChangedFile(
        path=path,
        change_kind=kind,
        old_path=old_path,
        language=language_of(path),
        added_lines=added_lines,
        removed_lines=removed_lines,
        is_binary=is_binary,
        is_generated=config.is_generated(path),
        size_bytes=size,
        content_hash=file_hash(full),
        hunks=[],
    )


def _merge_name_status(
    files: list[ChangedFile],
    name_status: str,
    root: Path,
    config: Config,
    meta: dict[str, Any],
) -> list[ChangedFile]:
    """Add entries the patch cannot express (mode-only, binary, submodule)."""
    seen = {f.path for f in files}
    for kind, path, old_path in _parse_name_status(name_status):
        if path in seen:
            continue
        entry = _make_entry(root, config, path, kind, old_path)
        if entry is None:
            continue
        seen.add(path)
        files.append(entry)
        meta["warnings"].append(f"change present in --name-status but not in patch: {path}")
    files.sort(key=lambda f: f.path)
    return files


def _cache_diff(cache_dir: Optional[Path], key: str, text: str, meta: dict[str, Any]) -> None:
    """Persist the raw diff for forensics.  Never read back (avoids staleness)."""
    if cache_dir is None:
        return
    try:
        target = Path(cache_dir) / "context" / f"{key}.patch"
        ensure_dir(target.parent)
        target.write_text(text, encoding="utf-8")
        meta["diff_artifact"] = str(target)
    except OSError as exc:
        meta["warnings"].append(f"could not write diff artefact: {exc}")


def _scan_tree(root: Path, config: Config) -> list[ChangedFile]:
    """Every source file under ``source_roots`` (or the root) as MODIFIED."""
    roots = [root / r for r in config.source_roots if (root / r).is_dir()]
    if not roots:
        roots = [root]
    found: dict[str, Path] = {}
    for base in roots:
        for path in iter_files(base, suffixes=SOURCE_SUFFIXES, excludes=config.excludes):
            rel = relpath(path, root)
            if rel.startswith("..") or config.is_excluded(rel):
                continue
            found[rel] = path
    out: list[ChangedFile] = []
    for rel in sorted(found):
        entry = _make_entry(root, config, rel, ChangeKind.MODIFIED)
        if entry is not None:
            out.append(entry)
    return out


def _list_repo_files(
    info: GitInfo, config: Config, cached: Optional[list[str]] = None
) -> list[str]:
    if cached is not None:
        return list(cached)
    if info.is_git:
        res = _git_or_raise(info.repo_root, ["ls-files", "-z"], "ls-files")
        paths = [p for p in res.stdout.split("\0") if p]
    else:
        paths = [cf.path for cf in _scan_tree(info.repo_root, config)]
    return sorted({p.replace("\\", "/") for p in paths if not config.is_excluded(p)})


def _resolve_file_arg(root: Path, file_arg: str) -> str:
    """Map a user supplied ``--file`` value onto a repo-relative posix path.

    An absolute path is taken as-is; anything else is first tried relative to
    the repository root (the documented meaning) and then relative to the
    current working directory.
    """
    raw = str(file_arg).replace("\\", "/").strip()
    if not raw:
        raise ContextError("empty file argument", repo_root=str(root))
    raw_path = Path(raw)
    candidates: list[Path] = [raw_path] if raw_path.is_absolute() else [root / raw_path, Path.cwd() / raw_path]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        try:
            rel = resolved.relative_to(root.resolve()).as_posix()
        except (ValueError, OSError):
            continue
        if not rel.startswith("..") and rel != ".":
            return rel
    raise ContextError(
        "file argument is outside the repository",
        file_arg=file_arg,
        repo_root=str(root),
    )


# --------------------------------------------------------------------------
# mode resolution
# --------------------------------------------------------------------------


def resolve_changed_files(
    info: GitInfo,
    *,
    mode: ReviewMode | str,
    base_ref: Optional[str] = None,
    head_ref: Optional[str] = None,
    commit: Optional[str] = None,
    file_arg: Optional[str] = None,
    config: Optional[Config] = None,
    cache_dir: Optional[Path] = None,
) -> tuple[list[ChangedFile], dict[str, Any]]:
    """Resolve the change set for one review mode.

    Returns ``(changed_files, meta)``; ``meta`` always carries the exact git
    commands that were run so a report can prove what was inspected.
    """
    cfg = config if config is not None else Config()
    mode_value = mode.value if isinstance(mode, ReviewMode) else str(mode)

    meta: dict[str, Any] = {
        "mode": mode_value,
        "is_git": info.is_git,
        "repo_root": str(info.repo_root),
        "head_sha": info.head_sha,
        "branch": info.branch,
        "dirty": info.dirty,
        "degraded": None,
        "commands": [],
        "warnings": [],
    }

    if not info.is_git:
        if mode_value == "repo":
            files = _scan_tree(info.repo_root, cfg)
            meta["repo_files_cache"] = [cf.path for cf in files]
            meta["warnings"].append("not a git repository: fell back to filesystem walk")
            return files, meta
        if mode_value == "file":
            if not file_arg:
                raise ContextError("mode 'file' requires a file argument")
            rel = _resolve_file_arg(info.repo_root, file_arg)
            entry = _make_entry(info.repo_root, cfg, rel, ChangeKind.ADDED)
            meta["warnings"].append("not a git repository: whole file treated as new")
            return ([entry] if entry else []), meta
        raise ContextError(
            f"mode '{mode_value}' requires a git repository",
            repo_root=str(info.repo_root),
        )

    root = info.repo_root

    if mode_value == "diff":
        if info.head_sha:  # already known from probe_repo -- no extra git call
            res = _git_or_raise(root, ["diff", "-M", "--no-color", "HEAD"], "diff HEAD")
            meta["commands"].append(res.command_line)
            files = parse_unified_diff(res.stdout, repo_root=root, config=cfg)
            # ``git diff HEAD`` omits untracked paths; the working-tree diff must
            # still surface new files the author has not staged yet.
            status = _run_git(root, ["status", "--porcelain", "-uall"], timeout_s=60.0)
            if status.ok:
                meta["commands"].append(status.command_line)
                seen = {cf.path for cf in files}
                for raw in status.stdout.split("\n"):
                    line = _strip_cr(raw)
                    if len(line) < 4:
                        continue
                    code, path = line[:2], line[3:]
                    path = path.replace("\\", "/")
                    if " -> " in path:
                        path = path.split(" -> ", 1)[1]
                    if code.strip() != "??" or path in seen:
                        continue
                    entry = _make_entry(root, cfg, path, ChangeKind.ADDED)
                    if entry is not None:
                        files.append(entry)
                        seen.add(path)
                files.sort(key=lambda f: f.path)
            _cache_diff(cache_dir, short_hash("diff", info.head_sha), res.stdout, meta)
            return files, meta

        # unborn HEAD: there is nothing to diff against.  Degrade explicitly.
        meta["degraded"] = "unborn-head"
        meta["warnings"].append(
            "HEAD has no commits; listing untracked + staged files with empty hunks"
        )
        res = _git_or_raise(root, ["status", "--porcelain", "-uall"], "status --porcelain")
        meta["commands"].append(res.command_line)
        files = []
        for raw in res.stdout.split("\n"):
            line = _strip_cr(raw)
            if len(line) < 4:
                continue
            code, path = line[:2], line[3:]
            path = path.replace("\\", "/")
            if " -> " in path:  # rename, "R  old -> new"
                path = path.split(" -> ", 1)[1]
            if code.strip() == "??":
                kind = ChangeKind.ADDED
            else:
                kind = _STATUS_KIND.get(code.strip()[:1].upper(), ChangeKind.MODIFIED)
            entry = _make_entry(root, cfg, path, kind)
            if entry is not None:
                files.append(entry)
        files.sort(key=lambda f: f.path)
        return files, meta

    if mode_value == "staged":
        res = _git_or_raise(root, ["diff", "--cached", "-M", "--no-color"], "diff --cached")
        meta["commands"].append(res.command_line)
        files = parse_unified_diff(res.stdout, repo_root=root, config=cfg)
        ns = _run_git(root, ["diff", "--cached", "--name-status", "-M"], timeout_s=60.0)
        if ns.ok:
            meta["commands"].append(ns.command_line)
            files = _merge_name_status(files, ns.stdout, root, cfg, meta)
        _cache_diff(cache_dir, short_hash("staged", info.head_sha), res.stdout, meta)
        return files, meta

    if mode_value == "commit":
        if not commit:
            raise ContextError("mode 'commit' requires a commit sha")
        res = _git_or_raise(
            root, ["show", "--format=", "--patch", "-M", "--no-color", commit], "show --patch"
        )
        meta["commands"].append(res.command_line)
        files = parse_unified_diff(res.stdout, repo_root=root, config=cfg)
        ns = _git_or_raise(
            root,
            ["diff-tree", "--no-commit-id", "--name-status", "-r", "--root", "-M", commit],
            "diff-tree --name-status",
        )
        meta["commands"].append(ns.command_line)
        files = _merge_name_status(files, ns.stdout, root, cfg, meta)
        if not files:
            meta["warnings"].append(f"commit {commit} produced an empty change set (merge commit?)")
        _cache_diff(cache_dir, short_hash("commit", commit), res.stdout, meta)
        return files, meta

    if mode_value == "range":
        if not base_ref or not head_ref:
            raise ContextError("mode 'range' requires both base_ref and head_ref")
        rng = f"{base_ref}..{head_ref}"
        res = _git_or_raise(root, ["diff", "-M", "--no-color", rng], f"diff {rng}")
        meta["commands"].append(res.command_line)
        files = parse_unified_diff(res.stdout, repo_root=root, config=cfg)
        ns = _git_or_raise(root, ["diff", "--name-status", "-M", rng], "diff --name-status")
        meta["commands"].append(ns.command_line)
        files = _merge_name_status(files, ns.stdout, root, cfg, meta)
        _cache_diff(cache_dir, short_hash("range", base_ref, head_ref), res.stdout, meta)
        return files, meta

    if mode_value == "file":
        if not file_arg:
            raise ContextError("mode 'file' requires a file argument")
        rel = _resolve_file_arg(root, file_arg)
        tracked = _run_git(root, ["ls-files", "--error-unmatch", "--", rel], timeout_s=30.0)
        if not tracked.ok:
            entry = _make_entry(root, cfg, rel, ChangeKind.ADDED)
            meta["warnings"].append(f"{rel} is not tracked by git; treated as a new file")
            return ([entry] if entry else []), meta
        res = _git_or_raise(root, ["diff", "-M", "--no-color", "HEAD", "--", rel], f"diff HEAD -- {rel}")
        meta["commands"].append(res.command_line)
        files = parse_unified_diff(res.stdout, repo_root=root, config=cfg)
        if not files:
            entry = _make_entry(root, cfg, rel, ChangeKind.MODIFIED)
            meta["warnings"].append(f"{rel} is unchanged against HEAD; reviewed in full")
            return ([entry] if entry else []), meta
        return files, meta

    if mode_value == "repo":
        res = _git_or_raise(root, ["ls-files", "-z"], "ls-files")
        meta["commands"].append(res.command_line)
        files = []
        listed: list[str] = []
        for path in res.stdout.split("\0"):
            if not path:
                continue
            normalised = path.replace("\\", "/")
            listed.append(normalised)
            entry = _make_entry(root, cfg, normalised, ChangeKind.MODIFIED)
            if entry is not None:
                files.append(entry)
        files.sort(key=lambda f: f.path)
        seen = {f.path for f in files}
        status = _run_git(root, ["status", "--porcelain", "-uall"], timeout_s=60.0)
        if status.ok:
            meta["commands"].append(status.command_line)
            for raw in status.stdout.split("\n"):
                line = _strip_cr(raw)
                if len(line) < 4:
                    continue
                code, path = line[:2], line[3:]
                path = path.replace("\\", "/")
                if " -> " in path:
                    path = path.split(" -> ", 1)[1]
                if code.strip() != "??" or path in seen:
                    continue
                entry = _make_entry(root, cfg, path, ChangeKind.ADDED)
                if entry is not None:
                    files.append(entry)
                    listed.append(path)
                    seen.add(path)
            files.sort(key=lambda f: f.path)
        meta["repo_files_cache"] = sorted(p for p in listed if not cfg.is_excluded(p))
        return files, meta

    raise ContextError(f"unsupported review mode '{mode_value}'")


def resolve_context(
    repo_root: Path,
    *,
    mode: ReviewMode,
    config: Config,
    base_ref: Optional[str] = None,
    head_ref: Optional[str] = None,
    commit: Optional[str] = None,
    file_arg: Optional[str] = None,
    cache_dir: Optional[Path] = None,
) -> ScanContext:
    """Build the :class:`ScanContext` every provider/reviewer receives."""
    if not isinstance(mode, ReviewMode):
        try:
            mode = ReviewMode(str(mode))
        except ValueError as exc:
            raise ContextError(f"unsupported review mode '{mode}'") from exc

    info = probe_repo(Path(repo_root))
    changed, meta = resolve_changed_files(
        info,
        mode=mode,
        base_ref=base_ref,
        head_ref=head_ref,
        commit=commit,
        file_arg=file_arg,
        config=config,
        cache_dir=cache_dir,
    )

    ctx = ScanContext(
        repo_root=info.repo_root if info.is_git else Path(repo_root).resolve(),
        mode=mode,
        changed_files=changed,
        base_ref=base_ref,
        head_ref=head_ref,
        commit=commit,
        file_arg=file_arg,
        repo_files=_list_repo_files(info, config, meta.pop("repo_files_cache", None)),
        config=config,
        cache_dir=Path(cache_dir) if cache_dir else None,
        options={"git": meta},
    )
    meta["changed_file_count"] = len(changed)
    meta["repo_file_count"] = len(ctx.repo_files)
    return ctx


def file_at_rev(repo_root: Path, rev: str, path: str) -> str:
    """Content of ``path`` at ``rev``; raises :class:`GitError` when absent."""
    root = Path(repo_root)
    res = _run_git(root, ["show", f"{rev}:{path}"], timeout_s=60.0)
    if res.launch_error:
        raise GitError(
            f"could not launch git show: {res.launch_error}",
            command=res.command_line,
            rev=rev,
            path=path,
        )
    if not res.ok:
        raise GitError(
            f"git show {rev}:{path} failed with exit code {res.exit_code}",
            command=res.command_line,
            exit_code=res.exit_code,
            stderr=res.stderr.strip()[:2000],
            rev=rev,
            path=path,
        )
    return res.stdout
