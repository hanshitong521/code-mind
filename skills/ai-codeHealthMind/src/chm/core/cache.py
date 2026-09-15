"""Run cache keyed on the five spec §14.3 elements.

A cache that ignores tool versions, the rule set or the config will happily
serve results produced under different rules -- which is worse than no cache.
So the stored key is the sha256 of *all five*:

``tool-version`` / ``repo-head`` / ``file-hash`` / ``rule-version`` /
``config-hash``.

Changing any one of them invalidates exactly the entries that depended on it.
A namespace is one JSON file, so invalidating a namespace is one unlink, and a
partial edit (one file changed -> one file-hash changed) only misses the keys
that mentioned that file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..util import ensure_dir, read_json, sha256_text, write_json

#: The five elements of spec §14.3, in the canonical order.
KEY_ELEMENTS: tuple[str, ...] = (
    "tool-version",
    "repo-head",
    "file-hash",
    "rule-version",
    "config-hash",
)


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0
    ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "writes": self.writes,
            "ratio": self.ratio,
        }


def cache_key(*parts: str) -> str:
    """Deterministic sha256 over the given parts."""
    return sha256_text("\x00".join("" if p is None else str(p) for p in parts))


def _safe_namespace(namespace: str) -> str:
    cleaned = "".join(
        ch if (ch.isalnum() or ch in "-_.") else "_" for ch in str(namespace)
    )
    return cleaned or "default"


def repo_cache_dir(repo_root: Path | str, config: Any, *, head_sha: str) -> Path:
    """``<repo>/<run_dir>/cache``.

    ``head_sha`` is accepted because every caller has it and because it is the
    element that most often invalidates the cache; the *isolation* it buys is
    applied through ``key_parts['repo-head']`` rather than through the path, so
    that the directory layout stays stable across commits (spec §14.3).
    """
    run_dir = getattr(config, "run_dir", ".codehealth/runs")
    return Path(repo_root) / str(run_dir) / "cache"


class RunCache:
    """One JSON file per namespace, one sha256 key per entry."""

    def __init__(self, cache_dir: Path | str, *, key_parts: Optional[dict[str, str]] = None):
        self.cache_dir = ensure_dir(cache_dir)
        self.key_parts: dict[str, str] = {
            str(k): "" if v is None else str(v)
            for k, v in (key_parts or {}).items()
        }
        self._hits = 0
        self._misses = 0
        self._writes = 0

    # ------------------------------------------------------------- internals

    def _salt(self) -> str:
        return cache_key(*[f"{name}={self.key_parts.get(name, '')}" for name in KEY_ELEMENTS])

    def _entry_key(self, key: str) -> str:
        return cache_key(self._salt(), str(key))

    def _path(self, namespace: str) -> Path:
        return self.cache_dir / f"{_safe_namespace(namespace)}.json"

    # --------------------------------------------------------------- public

    def get(self, namespace: str, key: str) -> Optional[Any]:
        path = self._path(namespace)
        data = read_json(path, default=None)
        if not isinstance(data, dict) or data.get("key") != self._entry_key(key):
            self._misses += 1
            return None
        self._hits += 1
        return data.get("value")

    def put(self, namespace: str, key: str, value: Any) -> None:
        path = self._path(namespace)
        write_json(path, {"key": self._entry_key(key), "value": value})
        self._writes += 1

    def invalidate(self, namespace: Optional[str] = None) -> None:
        if namespace is not None:
            target = self._path(namespace)
            if target.is_file():
                target.unlink()
            return
        for candidate in sorted(self.cache_dir.glob("*.json")):
            if candidate.is_file():
                candidate.unlink()

    def stats(self) -> CacheStats:
        denominator = self._hits + self._misses
        ratio = round(self._hits / denominator, 4) if denominator else 0.0
        return CacheStats(
            hits=self._hits, misses=self._misses, writes=self._writes, ratio=ratio
        )
