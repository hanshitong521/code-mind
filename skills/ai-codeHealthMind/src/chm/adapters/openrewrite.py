"""OpenRewrite adapter -- a *repair executor*, not an evidence source.

This adapter deliberately produces **no findings**.  It exists so the repair
stage has a real, auditable way to apply a recipe, and so that the gate can
prove whether that capability is actually present on the host.

Safety contract (spec §33/§34): :meth:`OpenRewriteAdapter.apply` refuses to run
unless the caller has *explicitly* opted in via ``ctx.options["allow_rewrite"]``
**and** there is test evidence for the change.  Refusal is returned as a typed
``ToolError``, never as a silent success.

On this host Maven itself is broken -- ``mvn -v`` fails with
``找不到或无法加载主类 org.codehaus.plexus.classworlds.launcher.Launcher`` --
so :meth:`available` truthfully reports ``False`` and quotes the real stderr.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from ..contracts import ProviderResult, ScanContext
from ..errors import ToolError, ToolFailureKind, ToolStatus
from ..schema import Category
from ..util import run_cmd, which
from .base import CliProvider, first_lines, parse_version
from .pmd import coerce_ctx, config_path_failure, explicit_path_error

OPENREWRITE_BIN_ENV = "CHM_OPENREWRITE_BIN"
MAVEN_BIN_ENV = "CHM_MVN_BIN"

#: the Maven plugin coordinate that implements dry-run / run / discover
MAVEN_PLUGIN = "org.openrewrite.maven:rewrite-maven-plugin"


class OpenRewriteAdapter(CliProvider):
    """Recipe execution for the repair stage; never a finding producer."""

    name = "openrewrite"
    executable = "mvn"
    categories: tuple[Category, ...] = ()

    #: absence only disables auto-repair, it never blocks a finding's evidence
    evidence_gap = False

    def __init__(self, ctx: Optional[ScanContext] = None) -> None:
        #: see PmdAdapter.__init__ -- lets available()/version() see config
        self._ctx = coerce_ctx(ctx)
        self._version: Optional[str] = None
        self._version_probed = False

    # -- capability ------------------------------------------------------

    def _eff(self, ctx: Optional[ScanContext]) -> Optional[ScanContext]:
        return ctx if ctx is not None else self._ctx

    def _config(self, ctx: Optional[ScanContext] = None) -> Any:
        effective = self._eff(ctx)
        cfg = getattr(effective, "config", None) if effective is not None else None
        tools = getattr(cfg, "tools", None)
        return getattr(tools, "openrewrite", None)

    def _cli(self, ctx: Optional[ScanContext] = None) -> Optional[str]:
        cfg = self._config(ctx)
        bin_value = getattr(cfg, "bin", None) if cfg is not None else None
        if bin_value and Path(bin_value).is_file():
            return bin_value
        env = os.environ.get(OPENREWRITE_BIN_ENV)
        if env and Path(env).is_file():
            return env
        home = getattr(cfg, "home", None) if cfg is not None else None
        if home:
            return which("mod", [Path(home)])
        return None

    def _maven(self) -> Optional[str]:
        env = os.environ.get(MAVEN_BIN_ENV)
        if env and Path(env).is_file():
            return env
        return which("mvn")

    def _maven_probe(self) -> tuple[bool, Optional[str]]:
        """Run ``mvn -v`` for real and report exactly what happened."""
        mvn = self._maven()
        if mvn is None:
            return False, "no Maven executable found on PATH (set CHM_MVN_BIN to override)"
        result = run_cmd([mvn, "-v"], timeout_s=60.0)
        if result.launch_error:
            return False, f"mvn could not be launched: {result.launch_error}"
        if result.timed_out:
            return False, "mvn -v timed out"
        text = (result.stdout + result.stderr).strip()
        if result.exit_code != 0:
            return False, (
                f"mvn -v exited {result.exit_code}: {first_lines(text) or 'no output'}"
            )
        self._version = parse_version(text)
        return True, None

    def _local_repo(self, ctx: Optional[ScanContext] = None) -> Path:
        cfg = self._config(ctx)
        for arg in getattr(cfg, "args", None) or []:
            token = str(arg)
            if token.startswith("-Dmaven.repo.local="):
                return Path(token.split("=", 1)[1])
        return Path.home() / ".m2" / "repository"

    def _plugin_cached(self, ctx: Optional[ScanContext] = None) -> bool:
        """Is the rewrite plugin already in the local Maven repo (i.e. offline-usable)?

        Running Maven is not the same as being able to run OpenRewrite: without
        the plugin cached locally, the goal has to be downloaded first.  A probe
        must not silently assume network access exists.
        """
        group, artifact = MAVEN_PLUGIN.split(":")
        base = self._local_repo(ctx) / Path(*group.split(".")) / artifact
        if not base.is_dir():
            return False
        for version_dir in base.iterdir():
            if version_dir.is_dir() and any(version_dir.glob("*.jar")):
                return True
        return False

    def version(self) -> Optional[str]:
        if self._version_probed:
            return self._version
        self._version_probed = True
        ok, _ = self._maven_probe()
        if not ok:
            cli = self._cli(None)
            if cli is None:
                return None
            result = run_cmd([cli, "--version"], timeout_s=60.0)
            if not result.ok:
                return None
            self._version = parse_version(result.stdout + result.stderr)
        return self._version

    def available(self) -> tuple[bool, Optional[str]]:
        configured_error = explicit_path_error(self._config(None), "openrewrite")
        if configured_error:
            return False, configured_error
        cli = self._cli(None)
        if cli is not None:
            result = run_cmd([cli, "--version"], timeout_s=60.0)
            if result.exit_code == 0 and not result.launch_error:
                self._version = parse_version(result.stdout + result.stderr)
                self._version_probed = True
                return True, None
            return False, (
                f"OpenRewrite CLI at {cli} did not answer --version: "
                f"{first_lines(result.stderr or result.stdout) or 'no output'}"
            )

        maven_ok, maven_reason = self._maven_probe()
        if not maven_ok:
            return False, maven_reason
        if not self._plugin_cached(None):
            return False, (
                "Maven runs but the OpenRewrite plugin is not in the local repository "
                f"({self._local_repo(None)}); '{MAVEN_PLUGIN}' would have to be downloaded "
                "before any recipe could run"
            )
        self._version_probed = True
        return True, None

    # -- scope -----------------------------------------------------------

    def supports(self, ctx: ScanContext) -> bool:
        """OpenRewrite is applicable to any Maven/Gradle project."""
        root = Path(ctx.repo_root)
        return (root / "pom.xml").is_file() or (root / "build.gradle").is_file()

    # -- scan (no findings, by design) ------------------------------------

    def scan(self, ctx: ScanContext) -> ProviderResult:
        """Dry-run probe only.

        OpenRewrite is a *repair* tool: it never contributes findings.  When the
        toolchain is genuinely absent we still say so rather than returning a
        cheerful empty result.
        """
        self._ctx = coerce_ctx(ctx)
        config_failure = config_path_failure(self.name, self._config(ctx), "openrewrite")
        if config_failure is not None:
            return config_failure
        ok, reason = self.available()
        if not ok:
            return self._unavailable(
                ToolFailureKind.MISSING.value,
                reason or "OpenRewrite is not available on this host",
                gap=False,
            )
        return ProviderResult(
            provider=self.name,
            status=ToolStatus.OK,
            findings=[],
            duration_ms=0,
            command=None,
            version=self._version,
            artefact=None,
        )

    # -- recipes ----------------------------------------------------------

    def list_recipes(self, ctx: Optional[ScanContext] = None) -> list[str]:
        """Recipes the host can actually offer; ``[]`` when it cannot offer any.

        Call :meth:`available` to learn *why* an empty list came back.  The
        availability check runs first on purpose: invoking the Maven goal when
        the plugin is not cached would block on a network download for the whole
        timeout budget and then fail anyway.
        """
        ok, _ = self.available()
        if not ok:
            return []
        recipes, _ = self._discover_recipes(ctx)
        return recipes

    def _discover_recipes(
        self, ctx: Optional[ScanContext] = None
    ) -> tuple[list[str], Optional[ToolError]]:
        argv, error = self._recipe_discovery_argv(ctx)
        if argv is None:
            return [], error
        cfg = self._config(ctx)
        timeout_s = float(getattr(cfg, "timeout_s", 300.0) or 300.0)
        result = run_cmd(
            argv, cwd=Path(ctx.repo_root) if ctx is not None else None, timeout_s=timeout_s
        )
        if result.timed_out or result.launch_error or result.exit_code != 0:
            # ``-q`` can swallow the reason entirely; never report a blank detail.
            excerpt = first_lines(result.stderr or result.stdout)
            if not excerpt:
                excerpt = (
                    "Maven exited non-zero without a message (plugin not resolvable "
                    "offline?)"
                )
            return [], ToolError(
                provider=self.name,
                kind=ToolFailureKind.NONZERO_EXIT,
                detail=f"recipe discovery failed: {excerpt}",
                command=result.command_line,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                evidence_gap=False,
            )
        recipes = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip() and "." in line and " " not in line.strip()
        ]
        return sorted(set(recipes)), None

    def _recipe_discovery_argv(
        self, ctx: Optional[ScanContext]
    ) -> tuple[Optional[list[str]], Optional[ToolError]]:
        cli = self._cli(ctx)
        if cli is not None:
            return [cli, "discover"], None
        mvn = self._maven()
        if mvn is None:
            return None, ToolError(
                provider=self.name,
                kind=ToolFailureKind.MISSING,
                detail="no Maven executable found on PATH (set CHM_MVN_BIN to override)",
                evidence_gap=False,
            )
        return [mvn, "-q", f"{MAVEN_PLUGIN}:discover"], None

    # -- execution ---------------------------------------------------------

    def dry_run(self, recipe: str, ctx: ScanContext) -> ProviderResult:
        """Preview a recipe without touching the working tree."""
        return self._run(recipe, ctx, dry=True)

    def apply(self, recipe: str, ctx: ScanContext) -> ProviderResult:
        """Execute a recipe -- only with explicit opt-in *and* test evidence."""
        gate_error = self._apply_gate(ctx)
        if gate_error is not None:
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=gate_error,
            )
        return self._run(recipe, ctx, dry=False)

    @staticmethod
    def _apply_gate(ctx: ScanContext) -> Optional[ToolError]:
        if ctx.options.get("allow_rewrite") is not True:
            return ToolError(
                provider="openrewrite",
                kind=ToolFailureKind.CONFIG,
                detail=(
                    "refusing to modify the working tree: ctx.options['allow_rewrite'] "
                    "is not True"
                ),
                evidence_gap=False,
            )
        has_test_evidence = bool(str(getattr(ctx, "test_evidence", "") or "").strip()) or (
            ctx.options.get("test_ok") is True
        )
        if not has_test_evidence:
            return ToolError(
                provider="openrewrite",
                kind=ToolFailureKind.CONFIG,
                detail=(
                    "refusing to modify the working tree without test evidence "
                    "(set ctx.test_evidence or ctx.options['test_ok']=True)"
                ),
                evidence_gap=False,
            )
        return None

    def _run(self, recipe: str, ctx: ScanContext, *, dry: bool) -> ProviderResult:
        if not recipe:
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=ToolError(
                    provider=self.name,
                    kind=ToolFailureKind.CONFIG,
                    detail="no recipe specified",
                    evidence_gap=False,
                ),
            )

        argv, build_error = self._build_argv(recipe, ctx, dry=dry)
        if argv is None:
            return ProviderResult(
                provider=self.name, status=ToolStatus.UNAVAILABLE, error=build_error
            )

        cfg = self._config(ctx)
        timeout_s = float(getattr(cfg, "timeout_s", 600.0) or 600.0)
        result = run_cmd(argv, cwd=Path(ctx.repo_root), timeout_s=timeout_s)
        command = result.command_line

        if result.timed_out:
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=ToolError(
                    provider=self.name,
                    kind=ToolFailureKind.TIMEOUT,
                    detail=f"OpenRewrite {'dry-run' if dry else 'run'} exceeded its time budget",
                    command=command,
                    exit_code=result.exit_code,
                    duration_ms=result.duration_ms,
                    stderr_excerpt=first_lines(result.stderr),
                    evidence_gap=False,
                ),
                duration_ms=result.duration_ms,
                command=command,
            )
        if result.launch_error:
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=ToolError(
                    provider=self.name,
                    kind=ToolFailureKind.MISSING,
                    detail=f"OpenRewrite could not be launched: {result.launch_error}",
                    command=command,
                    duration_ms=result.duration_ms,
                    evidence_gap=False,
                ),
                duration_ms=result.duration_ms,
                command=command,
            )
        if result.exit_code != 0:
            return ProviderResult(
                provider=self.name,
                status=ToolStatus.UNAVAILABLE,
                error=ToolError(
                    provider=self.name,
                    kind=ToolFailureKind.NONZERO_EXIT,
                    detail=(
                        f"OpenRewrite {'dry-run' if dry else 'run'} of '{recipe}' "
                        f"exited {result.exit_code}: "
                        f"{first_lines(result.stderr or result.stdout)}"
                    ),
                    command=command,
                    exit_code=result.exit_code,
                    duration_ms=result.duration_ms,
                    stderr_excerpt=first_lines(result.stderr),
                    evidence_gap=False,
                ),
                duration_ms=result.duration_ms,
                command=command,
            )

        artefact = self._write_artefact(
            ctx,
            f"openrewrite-{'dryrun' if dry else 'apply'}.log",
            result.stdout + ("\n--- stderr ---\n" + result.stderr if result.stderr else ""),
        )
        return ProviderResult(
            provider=self.name,
            status=ToolStatus.OK,
            findings=[],
            duration_ms=result.duration_ms,
            command=command,
            version=self._version,
            artefact=artefact,
        )

    def _build_argv(
        self, recipe: str, ctx: ScanContext, *, dry: bool
    ) -> tuple[Optional[list[str]], Optional[ToolError]]:
        cfg = self._config(ctx)
        extra = [str(a) for a in (getattr(cfg, "args", None) or [])]

        cli = self._cli(ctx)
        if cli is not None:
            argv = [cli, "run", recipe] + (["--dry-run"] if dry else []) + extra
            return argv, None

        mvn = self._maven()
        if mvn is None:
            return None, ToolError(
                provider=self.name,
                kind=ToolFailureKind.MISSING,
                detail="no Maven executable found on PATH (set CHM_MVN_BIN to override)",
                evidence_gap=False,
            )
        goal = "dryRun" if dry else "run"
        argv = [
            mvn,
            "-q",
            f"{MAVEN_PLUGIN}:{goal}",
            f"-Drewrite.activeRecipes={recipe}",
        ] + extra
        return argv, None
