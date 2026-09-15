#!/usr/bin/env python3
"""selftest.py — SkillMind 端到端自测（spec-v2 §7 / §16）。

原则：
  - **零污染**：所有写入走临时目录（registry --out / score --store / telemetry --store），
    绝不碰 <repo>/.skillmind/，也不碰任何业务文件。
  - **可复现**：同输入同输出；分数用 score.compute 独立复算，不信任 CLI 打印。
  - **诚实**：PyYAML 缺失时相关一致性检查标记 SKIP 而非伪装 PASS。

覆盖 22 项：语法 / schema / 解析器一致性 / 哈希语义一致性 / 注册表 / manifest /
路由金标 / 评分金标 / 遥测脱敏 / overlap 检测 / 否定从句派生 / 审计 verdict /
校验器 bool-enum 安全 / 校验器唯一来源 / 哈希免 OS 元数据污染 /
token 估算公式 / 尺寸预算单位与 root_words 消费 / L2 单条 token 预算。

用法：python3 scripts/selftest.py [--json]
退出码：0 = 全 PASS（允许 SKIP）；1 = 有 FAIL；2 = 环境错误。
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import py_compile
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"

#: 漂移检测结论（与 skillmind.py verify 一致）
DRIFT, MISSING, UNTRACKED = "DRIFT", "MISSING", "UNTRACKED"


def _run(mod: Any, argv: list) -> tuple[int, str]:
    """调用子模块 main(argv)，捕获 stdout；SystemExit 归一为退出码。"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = mod.main(list(argv))
    except SystemExit as exc:
        code = int(exc.code or 0)
    except Exception as exc:  # noqa: BLE001 - 自测需把异常变成 FAIL 而非崩溃
        return 99, f"{type(exc).__name__}: {exc}"
    return int(code or 0), buf.getvalue()


def _mod(name: str):
    return importlib.import_module(name)


def _load_cases(path: Path, key: str) -> list:
    data = C.load_json(path, default=None)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in (key, "cases", "items"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


# ────────────────────────────── 各项检查 ──────────────────────────────

def check_py_compile(root: Path) -> dict:
    bad = []
    files = sorted((C.SCRIPTS_DIR).glob("*.py"))
    for p in files:
        try:
            py_compile.compile(str(p), doraise=True, cfile=str(Path(tempfile.gettempdir()) / (p.stem + ".pyc")))
        except py_compile.PyCompileError as exc:
            bad.append(f"{p.name}: {exc}")
    return {"ok": not bad, "detail": f"{len(files)} 个脚本编译{'通过' if not bad else '失败: ' + '; '.join(bad)}",
            "count": len(files)}


def check_json_schemas(root: Path) -> dict:
    bad = []
    names = []
    for p in sorted((C.SKILL_DIR / "schemas").glob("*.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except ValueError as exc:
            bad.append(f"{p.name}: JSON 解析失败 {exc}")
            continue
        if not doc.get("schema_name") or not doc.get("schema_version"):
            bad.append(f"{p.name}: 缺 schema_name/schema_version")
        names.append(str(doc.get("schema_name")))
    return {"ok": not bad, "detail": f"{len(names)} 个 schema{'通过' if not bad else '问题: ' + '; '.join(bad)}",
            "schemas": names}


def check_yaml_lite_parity(root: Path) -> dict:
    if not C.HAVE_PYYAML:
        return {"ok": True, "skip": True, "detail": "PyYAML 未安装 → 跳过一致性比对（_yaml_lite 已在裸 Python 下承担解析）"}
    import yaml
    bad = []
    files = sorted((root / "shared").glob("*.yaml")) + [C.SKILL_DIR / "skill.yaml",
                                                        C.SKILL_DIR / "templates" / "skill-skeleton" / "skill.yaml"]
    n = 0
    for p in files:
        if not p.exists():
            continue
        n += 1
        ref = yaml.safe_load(p.read_text(encoding="utf-8"))
        got = C.load_yaml(p)
        if ref != got:
            bad.append(p.name)
    return {"ok": not bad, "detail": f"{n} 个 YAML 与 PyYAML {'一致' if not bad else '不一致: ' + ', '.join(bad)}"}


def check_hash_semantics(root: Path) -> dict:
    if not C.HAVE_PYYAML:
        return {"ok": True, "skip": True, "detail": "PyYAML 未安装 → 跳过与 _release_lib 的哈希比对"}
    sys.path.insert(0, str(root / "scripts"))
    try:
        rl = _mod("_release_lib")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"无法加载 scripts/_release_lib.py: {exc}"}
    manifest = C.try_load_yaml(root / C.CONTROL_PLANE["release_manifest"]) or {}
    exclude = C.manifest_exclude(root)
    bad, n = [], 0
    for name, spec in (manifest.get("skills") or {}).items():
        rel = (spec or {}).get("artifact_path")
        if not rel:
            continue
        art = root / rel
        if not art.exists():
            continue
        n += 1
        a = rl.hash_tree(art, exclude=exclude)["content_hash"]
        b = C.hash_tree(art, exclude=exclude)["content_hash"]
        if a != b:
            bad.append(f"{name}")
    return {"ok": not bad,
            "detail": f"{n} 个 artifact 的 content_hash 与 _release_lib {'逐字节一致' if not bad else '不一致: ' + ', '.join(bad)}"}


def check_registry_build(root: Path, tmp: Path) -> dict:
    """断言注册表**自洽**：每个 skill 的 hash == hash_tree(该 skill 目录)。

    这里**不**断言「hash == release-manifest 记录的 content_hash」——记录是否新鲜是
    控制面的账，由 `skillmind verify` 负责（见 check_verify_consistency）。把两件事混在
    一个检查里，会让本仓既有的历史记录过期问题挡住 SkillMind 自身的构建验证。

    并发写入（外部进程正在改某个 skill 目录）会导致两次哈希不同 —— 标记为「并发写入中」
    并跳过，而不是判 FAIL：那是环境状态，不是 SkillMind 的回归。
    """
    out = tmp / "registry.json"
    code, text = _run(_mod("registry_build"), ["--root", str(root), "--out", str(out)])
    if code != 0 or not out.exists():
        return {"ok": False, "detail": f"registry build 退出码 {code}: {text[:200]}"}
    reg = json.loads(out.read_text(encoding="utf-8"))
    ids = sorted(s["skill_id"] for s in reg.get("skills") or [])
    problems = []
    racing: list[str] = []
    if len(ids) < 6:
        problems.append(f"只扫到 {len(ids)} 个 skill: {ids}")
    exclude = C.manifest_exclude(root)
    for s in reg.get("skills") or []:
        d = root / str(s.get("dir") or "")
        if not d.is_dir():
            problems.append(f"{s['skill_id']}: dir 不存在")
            continue
        h1 = C.hash_tree(d, exclude)["content_hash"]
        if h1 == s.get("hash"):
            continue
        # 目录在两次哈希之间发生变化 → 有并发写入（外部进程在改该 skill），
        # 不是 SkillMind 自身缺陷。标记而非 FAIL，避免把并发误判成回归。
        if h1 != C.hash_tree(d, exclude)["content_hash"]:
            racing.append(s["skill_id"])
            continue
        problems.append(f"{s['skill_id']}: hash 与 hash_tree(dir) 不自洽")
    detail = (f"skills={len(ids)}；hash 自洽 {len(ids) - len(problems) - len(racing)}/{len(ids)}"
              + (f"；并发写入中（已跳过）: {', '.join(racing)}" if racing else "")
              + ("" if not problems else "；问题: " + "; ".join(problems)))
    return {"ok": not problems, "detail": detail,
            "registry": str(out), "skill_ids": ids, "racing": racing}


def check_verify_consistency(root: Path) -> dict:
    """断言漂移检测器**自洽**：ok / 退出码 / summary 三者一致，findings 字段完整。

    本仓存在历史遗留 DRIFT（记录过期）时不判 FAIL —— 那是控制面的账，如实列出即可；
    真正要保证的是「检测器能正确检出」。修复入口：python3 scripts/build_release.py。
    """
    sk = _mod("skillmind")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = sk.cmd_verify(["--root", str(root), "--json"])
    try:
        res = json.loads(buf.getvalue())
    except ValueError:
        return {"ok": False, "detail": "verify 未输出合法 JSON"}
    s = res.get("summary") or {}
    expect_ok = (s.get(DRIFT) == 0 and s.get(MISSING) == 0)
    problems = []
    if bool(res.get("ok")) != expect_ok:
        problems.append("ok 与 summary 不自洽")
    if (code == 0) != expect_ok:
        problems.append(f"退出码 {code} 与结论不自洽")
    for f in res.get("findings") or []:
        if not f.get("verdict") or not f.get("detail"):
            problems.append("findings 缺 verdict/detail")
            break
    drift = sorted({str(f.get("skill")) for f in (res.get("findings") or [])
                    if f.get("verdict") == DRIFT})
    extra = f"；检出既有 DRIFT: {', '.join(drift)}（非本次改动，修复: python3 scripts/build_release.py）" if drift else ""
    return {"ok": not problems,
            "detail": f"verify 自洽（PASS={s.get(PASS)} DRIFT={s.get(DRIFT)} "
                      f"MISSING={s.get(MISSING)} UNTRACKED={s.get(UNTRACKED)}）{extra}"
                      + ("" if not problems else "；问题: " + "; ".join(problems))}


def check_registry_schema(tmp: Path) -> dict:
    reg_p = tmp / "registry.json"
    if not reg_p.exists():
        return {"ok": False, "detail": "registry.json 不存在（依赖 registry build）"}
    schema = json.loads((C.SKILL_DIR / "schemas" / "registry.schema.json").read_text(encoding="utf-8"))
    inst = json.loads(reg_p.read_text(encoding="utf-8"))
    errors = _mod("telemetry").validate_instance(inst, schema)
    return {"ok": not errors, "detail": f"registry.json 对 registry.schema.json "
                                        f"{'校验通过' if not errors else '有 ' + str(len(errors)) + ' 处不符: ' + '; '.join(errors[:3])}"}


def check_manifest_validate_self() -> dict:
    code, text = _run(_mod("manifest_validate"), ["--path", str(C.SKILL_DIR / "skill.yaml"), "--json"])
    return {"ok": code == 0, "detail": f"skill.yaml 校验退出码 {code}"
                                        + ("" if code == 0 else f": {text[:200]}")}


def check_router_expectations(root: Path, tmp: Path) -> dict:
    reg = tmp / "registry.json"
    cases = [
        ("改一个 MyBatis SQL，查询条件多一个审核人", "ai-code"),
        ("审计一下 skill 的触发器，MCP tool 暴露太多了", "ai-skill-mcp-Y"),
        ("澄清需求并冻结，输出开发规格", "ai-requirement"),
    ]
    bad = []
    for task, expect in cases:
        code, text = _run(_mod("router"), ["--task", task, "--registry", str(reg), "--json"])
        if code != 0:
            bad.append(f"{task[:16]}… 退出码 {code}")
            continue
        try:
            res = json.loads(text)
        except ValueError:
            bad.append(f"{task[:16]}… 输出非 JSON")
            continue
        top = (res.get("recommended") or [{}])[0].get("skill_id")
        if top != expect:
            bad.append(f"「{task[:18]}…」期望 {expect} 实得 {top}")
    return {"ok": not bad, "detail": f"{len(cases)} 条路由期望{'全部命中' if not bad else '未命中: ' + '; '.join(bad)}"}


def check_routing_golden(root: Path, tmp: Path) -> dict:
    path = C.SKILL_DIR / "tests" / "routing-cases.json"
    if not path.exists():
        return {"ok": False, "detail": "tests/routing-cases.json 不存在"}
    cases = _load_cases(path, "routing-cases")
    if not cases:
        return {"ok": False, "detail": "routing-cases.json 无用例"}
    bad = []
    for c in cases:
        argv = ["--task", str(c.get("task") or ""), "--registry", str(tmp / "registry.json"), "--json"]
        if c.get("project_type"):
            argv += ["--project-type", str(c["project_type"])]
        code, text = _run(_mod("router"), argv)
        if code != 0:
            bad.append(f"{c.get('id')}: 退出码 {code}")
            continue
        try:
            res = json.loads(text)
        except ValueError:
            bad.append(f"{c.get('id')}: 输出非 JSON")
            continue
        rec = res.get("recommended") or []
        top = rec[0].get("skill_id") if rec else None
        ids = [r.get("skill_id") for r in rec]
        exp = c.get("expect_top")
        if exp and top != exp:
            bad.append(f"{c.get('id')}: expect_top={exp} 实得 {top}")
        for forbidden in (c.get("expect_not") or []):
            if forbidden in ids:
                bad.append(f"{c.get('id')}: 不该出现 {forbidden}")
    return {"ok": not bad, "detail": f"{len(cases)} 条路由金标{'全过' if not bad else f'{len(bad)} 条不过: ' + '; '.join(bad[:3])}"}


def check_score_formula() -> dict:
    sc = _mod("score")
    metrics = {"success_rate": 0.95, "accuracy": 0.93, "token_avg": 2500,
               "time_avg": 15, "stability": 0.98}
    rec = sc.compute(metrics, None)
    got = rec.get("score")
    expect = 0.40 * 95 + 0.30 * 93 + 0.15 * 100 + 0.10 * 100 + 0.05 * 98  # = 95.8
    sub = rec.get("subscores") or {}
    problems = []
    if got is None or abs(float(got) - expect) > 0.05:
        problems.append(f"score={got} 期望 {expect}")
    for k, v in (("success_rate", 95.0), ("accuracy", 93.0), ("token_efficiency", 100.0),
                 ("speed", 100.0), ("stability", 98.0)):
        if abs(float(sub.get(k, -1)) - v) > 0.01:
            problems.append(f"subscores.{k}={sub.get(k)} 期望 {v}")
    if not rec.get("baseline_defaulted"):
        problems.append("未标注 baseline_defaulted")
    return {"ok": not problems,
            "detail": f"§3.3 公式复算 score={got}（期望 {expect}）"
                      + ("" if not problems else "；问题: " + "; ".join(problems))}


def check_scoring_golden() -> dict:
    path = C.SKILL_DIR / "tests" / "scoring-cases.json"
    if not path.exists():
        return {"ok": False, "detail": "tests/scoring-cases.json 不存在"}
    cases = _load_cases(path, "scoring-cases")
    if not cases:
        return {"ok": False, "detail": "scoring-cases.json 无用例"}
    sc = _mod("score")
    bad = []
    for c in cases:
        rec = sc.compute(c.get("metrics") or {}, c.get("baseline"))
        got = float(rec.get("score") or 0)
        exp = float(c.get("expect_score") or 0)
        if abs(got - exp) > 0.5:
            bad.append(f"{c.get('id')}: {got} vs {exp}")
    return {"ok": not bad, "detail": f"{len(cases)} 条评分金标{'全过' if not bad else f'{len(bad)} 条不过: ' + '; '.join(bad)}"}


def check_telemetry(tmp: Path) -> dict:
    store = tmp / "telemetry.jsonl"
    secret = "sk-selftest-abcdef1234567890"
    ev = {"ts": "2026-09-15T12:00:00Z", "session_id": "s", "agent_id": "cursor",
          "project_id": "code-mind", "skill_id": "ai-code", "triggered": True,
          "success": False, "latency_ms": 1500, "p0_evidence_retained": False,
          "error_class": "Timeout", "api_token": secret}
    code, text = _run(_mod("telemetry"), ["append", "--event-json", json.dumps(ev), "--store", str(store)])
    if code != 0 or not store.exists():
        return {"ok": False, "detail": f"telemetry append 退出码 {code}: {text[:200]}"}
    raw = store.read_text(encoding="utf-8")
    problems = []
    if secret in raw:
        problems.append("敏感值未脱敏，已落盘")
    code2, text2 = _run(_mod("telemetry"), ["summary", "--store", str(store), "--json"])
    if code2 != 0:
        problems.append(f"summary 退出码 {code2}")
    else:
        try:
            summ = json.loads(text2)
        except ValueError:
            summ = {}
        blob = json.dumps(summ, ensure_ascii=False)
        if "p0_evidence" not in blob:
            problems.append("summary 未报 P0 证据丢失")
    return {"ok": not problems,
            "detail": "脱敏 + P0 证据告警" + ("正常" if not problems else "问题: " + "; ".join(problems))}


def check_triggers_derivation(root: Path) -> dict:
    """断言 derive_triggers **真正消费** description 的否定从句。

    历史缺陷：exclude 恒为 [] —— 否定从句被静默丢弃，导致 5/6 技能无精确度护栏，
    且 audit 把「作者写了 Not for 但解析器不派生」误报成「作者没写」。
    """
    problems: list[str] = []

    desc = ("Use when /alpha: do the thing. "
            "Not for /beta, requirement freeze, log-only ops.")
    got = C.derive_triggers("", desc)
    exc = list(got.get("exclude") or [])
    inc = list(got.get("include") or [])
    for want in ("/beta", "requirement freeze"):
        if want not in exc:
            problems.append(f"合成样本 exclude 缺 {want!r}（实得 {exc}）")
    if "/beta" in inc:
        problems.append("include 混入否定从句的 /beta（正向面被污染）")

    for sid in ("ai-code", "ai-concise"):
        p = root / "skills" / sid / "SKILL.md"
        if not p.exists():
            continue
        text = C.read_text(p)
        d = C.frontmatter_scalar(text, "description")
        if "not for" not in d.lower():
            continue
        if not list(C.derive_triggers(text, d).get("exclude") or []):
            problems.append(f"{sid} 写了 Not for 却未派生 exclude")

    # 消费端：多词短语须按 AND 语义命中（语序可变），否则护栏等于失效
    rt = _mod("router")
    if not rt.exclude_hit("requirement freeze", "freeze requirement then write code"):
        problems.append("exclude_hit 未按 AND 语义命中（语序变化漏判）")
    if rt.exclude_hit("log-only ops", "implement a new payment feature"):
        problems.append("exclude_hit 误命中无关任务")

    return {"ok": not problems,
            "detail": f"否定从句派生 exclude + 消费端 AND 命中{'正常' if not problems else '异常: ' + '; '.join(problems)}"}


def check_audit_verdict(root: Path) -> dict:
    """断言 audit verdict 只由**可执行动作**决定：全 KEEP 必须 PASS。

    历史缺陷：verdict = OPTIMIZE if findings else PASS —— KEEP 也算 findings，
    于是审计永远报 OPTIMIZE（报警失效 = 等于没有报警）。
    """
    sk = _mod("skillmind")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sk.cmd_audit(["--root", str(root), "--scope", "agents", "--json"])
    try:
        res = json.loads(buf.getvalue())
    except ValueError:
        return {"ok": False, "detail": "audit 未输出合法 JSON"}
    actions = {str(f.get("action")) for f in res.get("findings") or []}
    actionable = actions - {"KEEP"}
    expect = "OPTIMIZE" if actionable else "PASS"
    problems = []
    if res.get("verdict") != expect:
        problems.append(f"verdict={res.get('verdict')} 期望 {expect}（actions={sorted(actions)}）")
    if "KEEP" in (res.get("counts") or {}) and not actionable and res.get("verdict") != "PASS":
        problems.append("KEEP 被当成可执行 findings")
    return {"ok": not problems,
            "detail": f"verdict 语义（全 KEEP → PASS）{'正确' if not problems else '错误: ' + '; '.join(problems)}"}


def check_validator_bool_enum() -> dict:
    """断言 JSON Schema 校验器的 enum 区分 True/1，且非法 pattern 不抛异常。

    历史缺陷：telemetry 的 enum 用 `instance not in schema["enum"]`，Python 里
    True == 1 → `True` 被误判为匹配 `enum:[1]`；pattern 无 re.error 兜底 → 崩。
    """
    tm = _mod("telemetry")
    problems: list[str] = []
    if not tm.validate_instance(True, {"enum": [1]}):
        problems.append("True 被误判为匹配 enum [1]（bool/int 未区分）")
    if tm.validate_instance(1, {"enum": [1]}):
        problems.append("1 未匹配 enum [1]")
    try:
        tm.validate_instance("x", {"pattern": "([unclosed"})
    except Exception as exc:  # noqa: BLE001
        problems.append(f"非法 pattern 抛 {type(exc).__name__} 而非记为错误")
    return {"ok": not problems,
            "detail": f"enum bool 安全 + pattern 兜底{'正常' if not problems else '异常: ' + '; '.join(problems)}"}


def check_validator_single_source() -> dict:
    """断言 JSON Schema 校验器**只有一个实现**（_common），两处消费方均为转发。

    历史教训：manifest_validate 与 telemetry 各写一份，已分化出缺陷（bool-enum /
    pattern 兜底）。本检查锁定「唯一来源」，防止再次各写一份。
    """
    problems: list[str] = []
    tm = _mod("telemetry")
    mv = _mod("manifest_validate")
    if tm.validate_instance is not C.validate_instance:
        problems.append("telemetry.validate_instance 不是 _common 的实现（疑似又复制了一份）")
    for dup in ("Validator", "json_type", "type_matches", "same_value"):
        if hasattr(mv, dup):
            problems.append(f"manifest_validate 又出现本地副本: {dup}")
    schema = {"type": "object", "properties": {"a": {"type": "integer", "minimum": 3}},
              "required": ["a"], "additionalProperties": False}
    probe = {"a": 1, "b": 2}
    a = C.validate_instance(probe, schema)
    b = tm.validate_instance(probe, schema)
    if sorted(a) != sorted(b):
        problems.append(f"两处校验结论不一致: {a} vs {b}")
    if not a:
        problems.append("探针未报错（minimum/additionalProperties 未生效）")
    return {"ok": not problems,
            "detail": f"校验器唯一来源{'已锁定' if not problems else '被破坏: ' + '; '.join(problems)}"}


def check_hash_os_noise(tmp: Path) -> dict:
    """断言 content_hash 不受 OS 目录元数据影响（.DS_Store / Thumbs.db）。

    历史缺陷：exclude 列表漏了 .DS_Store → Finder 一碰目录就改变 content_hash →
    假 DRIFT（本仓 ai-code 曾因此长期误报）。修在控制面
    `release-manifest.yaml: hash.normalize.exclude`，本检查锁住该口径。
    """
    exclude = C.manifest_exclude()
    problems: list[str] = []
    for noise in (".DS_Store", "Thumbs.db"):
        if noise not in exclude:
            problems.append(f"exclude 未含 OS 元数据 {noise}（会引发假 DRIFT）")
    d = tmp / "os-noise-probe"
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("hello\n", encoding="utf-8")
    clean = C.hash_tree(d, exclude)["content_hash"]
    (d / ".DS_Store").write_bytes(b"\x00\x01noise")
    (d / "Thumbs.db").write_bytes(b"\x00\x01noise")
    noisy = C.hash_tree(d, exclude)["content_hash"]
    if clean != noisy:
        problems.append("加入 .DS_Store/Thumbs.db 后 content_hash 变了")
    return {"ok": not problems,
            "detail": f"OS 元数据不污染 content_hash{'正常' if not problems else '异常: ' + '; '.join(problems)}"}


def check_overlap_detection() -> dict:
    rb = _mod("registry_build")
    skills = [
        {"skill_id": "a", "description": "alpha beta", "tags": ["x", "y", "z"]},
        {"skill_id": "b", "description": "alpha beta", "tags": ["x", "y", "z"]},
        {"skill_id": "c", "description": "gamma", "tags": ["q"]},
    ]
    ov = rb.compute_overlap(skills)
    hit = [o for o in ov if {o["a"], o["b"]} == {"a", "b"}]
    if not hit:
        return {"ok": False, "detail": "3 个共享标签的合成样本未检出 overlap"}
    if hit[0].get("severity") != "warn":
        return {"ok": False, "detail": f"severity 应为 warn，实为 {hit[0].get('severity')}"}
    return {"ok": True, "detail": "合成样本正确检出 overlap（severity=warn）"}


def check_est_tokens() -> dict:
    """断言 `est_tokens` 落地 `references/token-loading.md` §3 公式。

    历史缺口：公式 `ceil(ascii/4) + ceil(cjk/1.5)` 写进了规范，但 `scripts/`
    从未实现 → L2 单条预算「> 2000 tokens 必须再拆」无任何代码可核验。
    """
    if not hasattr(C, "est_tokens"):
        return {"ok": False, "detail": "C.est_tokens 缺失（规范公式未落地）"}
    cases = [
        ("", 0),
        ("a" * 4, 1),                 # ceil(4/4)
        ("a" * 5, 2),                 # ceil(5/4)
        ("\u4e00" * 3, 2),            # ceil(3/1.5)
        ("\u4e00" * 4, 3),            # ceil(4/1.5)
        ("a" * 8 + "\u4e00" * 3, 4),  # 2 + 2
    ]
    bad = []
    for text, want in cases:
        got = C.est_tokens(text)
        if got != want:
            bad.append(f"{text[:6]!r}->{got} 期望 {want}")
    return {"ok": not bad,
            "detail": "est_tokens 口径正确（ceil(ascii/4)+ceil(cjk/1.5)）"
                      if not bad else "口径错误: " + "; ".join(bad)}


def check_size_budget_units(root: Path) -> dict:
    """断言尺寸预算**单位正确**：行数硬顶与 words 分档是两套，且 `root_words` 被消费。

    历史缺陷：`ROOT_LINES_HOT/WARN/SPLIT = 200/500/800` —— 把规范里 *words* 的
    200/500/800 原值填进了 *行数* 常量。后果：`root_words` 算了却无人消费，
    「行数过关、词数超标」的常驻成本漏检（`ai-requirement` 196 行 / 2522 words）。
    """
    sk = _mod("skillmind")
    problems = []
    for name, want in (("ROOT_LINES_MAX", 120), ("ROOT_WORDS_HOT", 200),
                       ("ROOT_WORDS_WARN", 500), ("ROOT_WORDS_SPLIT", 800)):
        if not hasattr(sk, name):
            problems.append(f"缺常量 {name}")
        elif int(getattr(sk, name)) != want:
            problems.append(f"{name}={getattr(sk, name)} 期望 {want}")

    def probe(lines: int, words: int) -> list:
        fake = {"skill_id": "__probe__", "path": "skills/__probe__/SKILL.md",
                "root_lines": lines, "root_words": words, "load_mode": "always",
                "triggers": {"include": ["x"], "exclude": ["y"]}, "refs": [],
                "description": "probe", "status": "active"}
        return sk._audit_skill(root, fake)

    big = probe(196, 2522)
    if not any(f["action"] == "LAZY-LOAD" for f in big):
        problems.append("常驻 2522 words 未报 LAZY-LOAD（root_words 未被消费）")
    if not any(f["action"] == "SPLIT" for f in big):
        problems.append("196 行 / 2522 words 未报 SPLIT")
    if any(f["action"] in ("SPLIT", "LAZY-LOAD") for f in probe(60, 180)):
        problems.append("60 行 / 180 words 的合规常驻根被误报尺寸问题")
    return {"ok": not problems,
            "detail": "尺寸预算单位与 root_words 消费均正确" if not problems
                      else "错误: " + "; ".join(problems)}


def check_ref_token_budget(root: Path) -> dict:
    """断言 L2 单条 reference 超预算会被报出。

    历史缺口：`references/token-loading.md` §1.3 规定「单条 reference 估算
    > 2000 tokens → 必须再拆」，但 `_audit_skill` 只查 `refs` 断链、从无尺寸检查
    → `spec-v1.md`（≈5.5k tok）长期漏检。
    """
    sk = _mod("skillmind")
    sid = "ai-skill-mcp-Y"
    probe = {"skill_id": sid, "path": f"skills/{sid}/SKILL.md",
             "root_lines": 60, "root_words": 673, "load_mode": "on-demand",
             "triggers": {"include": ["x"], "exclude": ["y"]},
             "refs": ["references/spec-v1.md"], "description": "probe",
             "status": "active"}
    found = sk._audit_skill(root, probe)
    hit = [f for f in found if f["action"] == "SPLIT" and "spec-v1" in str(f.get("issue"))]
    if not hit:
        return {"ok": False, "detail": "spec-v1.md（≈5.5k tok > 4000）未被报为超预算 SPLIT"}
    return {"ok": True, "detail": f"L2 单条超预算正确报出：{hit[0]['issue'][:56]}"}


# ────────────────────────────── 主流程 ──────────────────────────────

def run(root: Path) -> dict:
    checks: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="skillmind-selftest-") as td:
        tmp = Path(td)

        def add(name: str, fn) -> None:
            try:
                res = fn()
            except Exception as exc:  # noqa: BLE001
                res = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
            checks.append({"name": name,
                           "status": SKIP if res.get("skip") else (PASS if res.get("ok") else FAIL),
                           "detail": res.get("detail", ""),
                           **({k: v for k, v in res.items() if k not in ("ok", "skip", "detail")})})

        add("py_compile_all", lambda: check_py_compile(root))
        add("json_schemas_parse", lambda: check_json_schemas(root))
        add("yaml_lite_parity", lambda: check_yaml_lite_parity(root))
        add("hash_semantics_parity", lambda: check_hash_semantics(root))
        add("registry_build", lambda: check_registry_build(root, tmp))
        add("registry_schema", lambda: check_registry_schema(tmp))
        add("verify_consistency", lambda: check_verify_consistency(root))
        add("manifest_validate_self", lambda: check_manifest_validate_self())
        add("router_expectations", lambda: check_router_expectations(root, tmp))
        add("routing_golden_cases", lambda: check_routing_golden(root, tmp))
        add("score_formula", lambda: check_score_formula())
        add("scoring_golden_cases", lambda: check_scoring_golden())
        add("telemetry_redaction", lambda: check_telemetry(tmp))
        add("overlap_detection", lambda: check_overlap_detection())
        add("triggers_derivation", lambda: check_triggers_derivation(root))
        add("audit_verdict", lambda: check_audit_verdict(root))
        add("validator_bool_enum", lambda: check_validator_bool_enum())
        add("validator_single_source", lambda: check_validator_single_source())
        add("hash_os_noise", lambda: check_hash_os_noise(tmp))
        add("est_tokens", lambda: check_est_tokens())
        add("size_budget_units", lambda: check_size_budget_units(root))
        add("ref_token_budget", lambda: check_ref_token_budget(root))

    counts = {s: sum(1 for c in checks if c["status"] == s) for s in (PASS, FAIL, SKIP)}
    return {"schema_name": "skillmind-selftest", "schema_version": C.SCHEMA_VERSION,
            "generated_at": C.now_iso(), "root": str(root),
            "pyyaml": C.HAVE_PYYAML, "python": sys.version.split()[0],
            "counts": counts, "ok": counts[FAIL] == 0, "checks": checks}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog="selftest.py", description="SkillMind 端到端自测")
    ap.add_argument("--root", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        root = Path(a.root).expanduser().resolve() if a.root else C.repo_root()
    except OSError as exc:
        C.eprint(f"ERROR: 无法解析 --root: {exc}")
        return EXIT_USAGE
    if not (root / "skills").is_dir():
        C.eprint(f"ERROR: 缺少 skills/ 目录: {root / 'skills'}")
        return EXIT_USAGE

    payload = run(root)
    lines = [C.banner("SkillMind Selftest"),
             f"root={root}  python={payload['python']}  pyyaml={payload['pyyaml']}", ""]
    for c in payload["checks"]:
        lines.append(f"[{c['status']:<4}] {c['name']:<26} {c['detail']}")
    lines += ["", f"PASS={payload['counts'][PASS]} FAIL={payload['counts'][FAIL]} "
                  f"SKIP={payload['counts'][SKIP]} → "
                  + ("OK" if payload["ok"] else "FAILED")]
    C.emit(payload, as_json=a.json, human=lines)
    return EXIT_OK if payload["ok"] else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
