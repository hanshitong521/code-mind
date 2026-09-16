"""Configuration loading and validation for ``.codehealth.yml``.

Defaults follow spec §27 exactly.  The loader is forgiving about *absent*
keys (they take defaults) and strict about *malformed* ones (it raises), so a
typo in a gate threshold can never silently weaken the gate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .errors import ConfigError
from .util import DEFAULT_EXCLUDES

try:  # pragma: no cover - depends on host
    import yaml as _pyyaml  # type: ignore
except Exception:  # pragma: no cover
    _pyyaml = None

from . import yamlmini

CONFIG_FILENAMES = (".codehealth.yml", ".codehealth.yaml", "codehealth.yml")


def load_yaml(text: str) -> Any:
    """Parse YAML with PyYAML when present, else the built-in subset parser."""
    if _pyyaml is not None:
        return _pyyaml.safe_load(text)
    return yamlmini.loads(text)


def yaml_backend() -> str:
    return "pyyaml" if _pyyaml is not None else "yamlmini"


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------


@dataclass
class ToolConfig:
    enabled: bool = True
    #: extra argv appended to the tool invocation
    args: list[str] = field(default_factory=list)
    timeout_s: float = 300.0
    #: rule set / ruleset reference (PMD, Semgrep, ...)
    ruleset: Optional[str] = None
    #: explicit executable / home override
    home: Optional[str] = None
    bin: Optional[str] = None


@dataclass
class ToolsConfig:
    pmd: ToolConfig = field(default_factory=ToolConfig)
    cpd: ToolConfig = field(default_factory=ToolConfig)
    spotbugs: ToolConfig = field(default_factory=ToolConfig)
    semgrep: ToolConfig = field(default_factory=ToolConfig)
    knip: ToolConfig = field(default_factory=ToolConfig)
    openrewrite: ToolConfig = field(default_factory=lambda: ToolConfig(enabled=False))
    compile: ToolConfig = field(default_factory=ToolConfig)
    test: ToolConfig = field(default_factory=lambda: ToolConfig(enabled=False))
    native: ToolConfig = field(default_factory=ToolConfig)

    def get(self, name: str) -> ToolConfig:
        if not hasattr(self, name):
            raise ConfigError(f"unknown tool '{name}'")
        return getattr(self, name)

    def items(self):
        for name in (
            "native",
            "compile",
            "pmd",
            "cpd",
            "spotbugs",
            "semgrep",
            "knip",
            "openrewrite",
            "test",
        ):
            yield name, getattr(self, name)


@dataclass
class ReviewConfig:
    context_isolation: bool = True
    multi_model_on_high: bool = True
    reviewers_low: int = 1
    reviewers_medium: int = 1
    reviewers_high: int = 2
    reviewers_critical: int = 2
    validator_on_high: bool = True
    validator_on_critical: bool = True
    #: semantic reviewer backend: "off" | "rule" | "llm"
    backend: str = "rule"
    #: command template for the LLM backend, e.g. "llm-run --model {model} --prompt-file {prompt}"
    llm_command: Optional[str] = None
    model_a: str = "model-a"
    model_b: str = "model-b"
    max_tokens_per_call: int = 6000


@dataclass
class GatesConfig:
    block_on_critical: bool = True
    block_on_high: bool = True
    max_new_medium: int = 5
    warn_on_new_medium: bool = True
    block_on_tool_gap_for_critical: bool = True
    block_on_compile_fail: bool = True
    block_on_test_fail: bool = True
    min_score: float = 0.0


@dataclass
class TokenConfig:
    diff_first: bool = True
    max_context_files: int = 12
    cache: bool = True
    max_file_bytes_for_llm: int = 120_000
    summarize_generated: bool = True
    exclude_generated_from_llm: bool = True


@dataclass
class DeadCodeConfig:
    allow_auto_delete: bool = False
    require_reference_count_zero: bool = True
    dynamic_entry_check: bool = True


@dataclass
class BaselineConfig:
    enabled: bool = True
    path: str = ".codehealth-baseline.json"
    block_on_new_high: bool = True
    block_on_new_critical: bool = True


@dataclass
class AcceptedRisk:
    finding_id: str
    reason: str = ""
    owner: str = ""
    expires: Optional[str] = None
    #: optional rule-level wildcard, e.g. "CHM-JAVA-DUP-*"
    rule_id: Optional[str] = None

    def is_expired(self, today: str) -> bool:
        if not self.expires:
            return False
        return today > str(self.expires)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "reason": self.reason,
            "owner": self.owner,
            "expires": self.expires,
            "rule_id": self.rule_id,
        }


@dataclass
class Config:
    version: int = 1
    mode: str = "diff"
    languages: list[str] = field(
        default_factory=lambda: ["java", "javascript", "typescript", "vue"]
    )
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    gates: GatesConfig = field(default_factory=GatesConfig)
    token: TokenConfig = field(default_factory=TokenConfig)
    dead_code: DeadCodeConfig = field(default_factory=DeadCodeConfig)
    baseline: BaselineConfig = field(default_factory=BaselineConfig)
    accepted_risks: list[AcceptedRisk] = field(default_factory=list)

    #: glob-ish suffixes to exclude from analysis
    excludes: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    #: paths treated as generated (excluded from LLM context by default)
    generated_patterns: list[str] = field(
        default_factory=lambda: [
            "**/generated/**",
            "**/*.generated.*",
            "**/*_pb2.py",
            "**/target/generated-sources/**",
            "**/dist/**",
            "**/*.min.js",
        ]
    )
    #: minimum token count for CPD duplication
    duplication_min_tokens: int = 100
    #: complexity thresholds
    complexity_thresholds: dict[str, int] = field(
        default_factory=lambda: {
            "method_lines": 80,
            "method_cyclomatic": 15,
            "class_lines": 800,
            "nesting_depth": 4,
        }
    )
    #: source path used for ``--repo`` scans
    source_roots: list[str] = field(default_factory=lambda: ["src", "app", "lib"])
    #: where run artefacts are written
    run_dir: str = ".codehealth/runs"
    #: path of the loaded config file, if any
    source_path: Optional[str] = None

    # ---------------------------------------------------------------- lookups

    def accepted_risk_for(self, finding_id: str, rule_id: str, today: str) -> Optional[AcceptedRisk]:
        for ar in self.accepted_risks:
            if ar.is_expired(today):
                continue
            if ar.finding_id == finding_id:
                return ar
            if ar.rule_id and _glob_match(ar.rule_id, rule_id):
                return ar
        return None

    def is_excluded(self, rel_path: str) -> bool:
        parts = set(Path(rel_path).parts)
        return bool(parts & set(self.excludes))

    def is_generated(self, rel_path: str) -> bool:
        return any(_glob_match(pat, rel_path) for pat in self.generated_patterns)

    def to_dict(self) -> dict[str, Any]:
        def dc(obj: Any) -> Any:
            if hasattr(obj, "__dataclass_fields__"):
                return {k: dc(getattr(obj, k)) for k in obj.__dataclass_fields__}
            if isinstance(obj, list):
                return [dc(v) for v in obj]
            if isinstance(obj, dict):
                return {k: dc(v) for k, v in obj.items()}
            return obj

        return dc(self)


# --------------------------------------------------------------------------
# glob (fnmatch with ** support)
# --------------------------------------------------------------------------


_GLOB_CACHE: dict[str, "re.Pattern[str]"] = {}


def _glob_to_regex(pattern: str) -> "re.Pattern[str]":
    cached = _GLOB_CACHE.get(pattern)
    if cached is not None:
        return cached
    import re as _re

    p = pattern.replace("\\", "/")
    out: list[str] = []
    i = 0
    n = len(p)
    while i < n:
        ch = p[i]
        if ch == "*":
            if i + 1 < n and p[i + 1] == "*":
                j = i + 2
                if j < n and p[j] == "/":
                    j += 1
                    out.append("(?:.*/)?")
                else:
                    out.append(".*")
                i = j
                continue
            out.append("[^/]*")
            i += 1
            continue
        if ch == "?":
            out.append("[^/]")
            i += 1
            continue
        out.append(_re.escape(ch))
        i += 1
    compiled = _re.compile("^" + "".join(out) + "$")
    _GLOB_CACHE[pattern] = compiled
    return compiled


def _glob_match(pattern: str, text: str) -> bool:
    text = text.replace("\\", "/").lstrip("./")
    if _glob_to_regex(pattern).match(text):
        return True
    # also allow matching a bare filename against a path pattern such as
    # "**/*.min.js" -> "vendor.min.js"
    if "/" not in text:
        tail = pattern.rsplit("/", 1)[-1]
        # ``**/generated/**`` ends with ``**`` — matching bare filenames via
        # ``^.*$`` would mark every file (e.g. vendor.js) as generated.
        if not tail or tail == "**" or "." not in tail:
            return False
        return bool(_glob_to_regex(tail).match(text))
    return False


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------


def find_config(start: Path) -> Optional[Path]:
    cur = Path(start).resolve()
    for candidate in (cur, *cur.parents):
        for name in CONFIG_FILENAMES:
            p = candidate / name
            if p.is_file():
                return p
    return None


_ENV_TOOL_HOMES = {
    "pmd": ("CHM_PMD_HOME", "PMD_HOME"),
    "cpd": ("CHM_PMD_HOME", "PMD_HOME"),
    "spotbugs": ("CHM_SPOTBUGS_HOME", "SPOTBUGS_HOME"),
    "knip": ("CHM_KNIP_BIN", "KNIP_BIN"),
    "semgrep": ("CHM_SEMGREP_BIN", "SEMGREP_BIN"),
    "openrewrite": ("CHM_OPENREWRITE_BIN", "OPENREWRITE_BIN"),
}


def _apply_env_overrides(cfg: Config) -> None:
    for tool_name, env_names in _ENV_TOOL_HOMES.items():
        tc = cfg.tools.get(tool_name)
        for env_name in env_names:
            val = os.environ.get(env_name)
            if val:
                if env_name.endswith("_BIN"):
                    tc.bin = val
                else:
                    tc.home = val
                break


def _coerce_tool(name: str, raw: Any) -> ToolConfig:
    if raw is None:
        return ToolConfig()
    if isinstance(raw, bool):
        return ToolConfig(enabled=raw)
    if not isinstance(raw, dict):
        raise ConfigError(f"tools.{name} must be a mapping or bool, got {type(raw).__name__}")
    tc = ToolConfig()
    for key, value in raw.items():
        if not hasattr(tc, key):
            raise ConfigError(f"tools.{name}: unknown key '{key}'")
        setattr(tc, key, value)
    if tc.timeout_s is not None:
        tc.timeout_s = float(tc.timeout_s)
    if not isinstance(tc.args, list):
        raise ConfigError(f"tools.{name}.args must be a list")
    return tc


def _coerce_section(cls: type, raw: Any, section: str) -> Any:
    if raw is None:
        return cls()
    if not isinstance(raw, dict):
        raise ConfigError(f"'{section}' must be a mapping")
    obj = cls()
    for key, value in raw.items():
        if not hasattr(obj, key):
            raise ConfigError(f"'{section}': unknown key '{key}'")
        current = getattr(obj, key)
        if isinstance(current, bool) and not isinstance(value, bool):
            raise ConfigError(f"'{section}.{key}' must be a boolean")
        if isinstance(current, int) and not isinstance(current, bool) and not isinstance(value, int):
            if isinstance(value, float):
                value = int(value)
            else:
                raise ConfigError(f"'{section}.{key}' must be an integer")
        setattr(obj, key, value)
    return obj


def _coerce_accepted_risks(raw: Any) -> list[AcceptedRisk]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError("'accepted_risks' must be a list")
    out: list[AcceptedRisk] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ConfigError(f"accepted_risks[{i}] must be a mapping")
        fid = item.get("finding_id")
        rule = item.get("rule_id")
        if not fid and not rule:
            raise ConfigError(f"accepted_risks[{i}] needs 'finding_id' or 'rule_id'")
        out.append(
            AcceptedRisk(
                finding_id=fid or "",
                reason=item.get("reason", ""),
                owner=item.get("owner", ""),
                expires=item.get("expires"),
                rule_id=rule,
            )
        )
    return out


def parse_config(data: Any, *, source_path: Optional[str] = None) -> Config:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError("config root must be a mapping")

    known = {
        "version",
        "mode",
        "languages",
        "tools",
        "review",
        "gates",
        "token",
        "dead_code",
        "baseline",
        "accepted_risks",
        "excludes",
        "generated_patterns",
        "duplication_min_tokens",
        "complexity_thresholds",
        "source_roots",
        "run_dir",
    }
    unknown = set(data) - known
    if unknown:
        raise ConfigError(f"unknown config keys: {sorted(unknown)}")

    cfg = Config()
    cfg.source_path = source_path

    if "version" in data:
        cfg.version = int(data["version"])
        if cfg.version != 1:
            raise ConfigError(f"unsupported config version {cfg.version} (expected 1)")
    if "mode" in data:
        mode = str(data["mode"])
        if mode not in ("diff", "staged", "commit", "range", "file", "repo"):
            raise ConfigError(f"invalid mode '{mode}'")
        cfg.mode = mode
    if "languages" in data:
        langs = data["languages"]
        if not isinstance(langs, list):
            raise ConfigError("'languages' must be a list")
        cfg.languages = [str(x) for x in langs]

    if "tools" in data:
        tools_raw = data["tools"] or {}
        if not isinstance(tools_raw, dict):
            raise ConfigError("'tools' must be a mapping")
        for name, raw in tools_raw.items():
            if name not in {n for n, _ in cfg.tools.items()}:
                raise ConfigError(f"tools: unknown tool '{name}'")
            setattr(cfg.tools, name, _coerce_tool(name, raw))

    cfg.review = _coerce_section(ReviewConfig, data.get("review"), "review")
    cfg.gates = _coerce_section(GatesConfig, data.get("gates"), "gates")
    cfg.token = _coerce_section(TokenConfig, data.get("token"), "token")
    cfg.dead_code = _coerce_section(DeadCodeConfig, data.get("dead_code"), "dead_code")
    cfg.baseline = _coerce_section(BaselineConfig, data.get("baseline"), "baseline")
    cfg.accepted_risks = _coerce_accepted_risks(data.get("accepted_risks"))

    if "excludes" in data:
        cfg.excludes = [str(x) for x in (data["excludes"] or [])]
    if "generated_patterns" in data:
        cfg.generated_patterns = [str(x) for x in (data["generated_patterns"] or [])]
    if "duplication_min_tokens" in data:
        cfg.duplication_min_tokens = int(data["duplication_min_tokens"])
    if "complexity_thresholds" in data:
        thresholds = data["complexity_thresholds"] or {}
        if not isinstance(thresholds, dict):
            raise ConfigError("'complexity_thresholds' must be a mapping")
        for k, v in thresholds.items():
            if k not in cfg.complexity_thresholds:
                raise ConfigError(f"complexity_thresholds: unknown key '{k}'")
            cfg.complexity_thresholds[k] = int(v)
    if "source_roots" in data:
        cfg.source_roots = [str(x) for x in (data["source_roots"] or [])]
    if "run_dir" in data:
        cfg.run_dir = str(data["run_dir"])

    if cfg.review.backend not in ("off", "rule", "llm"):
        raise ConfigError(f"review.backend must be off|rule|llm, got '{cfg.review.backend}'")

    _apply_env_overrides(cfg)
    return cfg


def load_config(path: Optional[Path | str] = None, *, repo_root: Optional[Path] = None) -> Config:
    """Load config from ``path`` or discover it from ``repo_root``."""
    target: Optional[Path] = Path(path) if path else None
    if target is None and repo_root is not None:
        target = find_config(Path(repo_root))
    if target is None:
        cfg = Config()
        _apply_env_overrides(cfg)
        return cfg
    if not Path(target).is_file():
        raise ConfigError(f"config file not found: {target}")
    text = Path(target).read_text(encoding="utf-8")
    try:
        data = load_yaml(text)
    except Exception as exc:
        raise ConfigError(f"failed to parse {target}: {exc}") from exc
    return parse_config(data, source_path=str(target))


DEFAULT_CONFIG_TEMPLATE = """\
# CodeHealthMind configuration -- see docs/architecture.md
version: 1

mode: diff

languages:
  - java
  - javascript
  - typescript
  - vue

tools:
  pmd:
    enabled: true
  cpd:
    enabled: true
  spotbugs:
    enabled: true
  semgrep:
    enabled: true
  knip:
    enabled: true
  openrewrite:
    enabled: false

review:
  context_isolation: true
  multi_model_on_high: true
  backend: rule

gates:
  block_on_critical: true
  block_on_high: true
  max_new_medium: 5

token:
  diff_first: true
  max_context_files: 12
  cache: true

dead_code:
  allow_auto_delete: false

baseline:
  enabled: true
"""
