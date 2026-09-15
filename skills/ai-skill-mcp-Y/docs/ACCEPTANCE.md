# ACCEPTANCE — SkillMind Ultimate V2.0 验收表

> 判据来源：`references/spec-v2.md` §13（技术/质量指标）、§14（接口契约）、§16（DoD）；`references/spec-v1.md` §18 / §25 / §28。
> 全部命令以**仓根**为工作目录执行。退出码约定：`0` 通过 / `1` 校验失败或 DRIFT / `2` 用法或环境错误。

```bash
cd <repo_root>                                   # code-mind
PY=python3                                       # 裸 Python 3.9+，无第三方依赖
```

**使用方式**：逐条勾选；任一项 FAIL 即停在该 Phase（见 `docs/ROADMAP.md`），并按 §6 回滚。

---

## 1. 技术指标（spec §13）

| # | 判据 | 验证命令 | 通过标准 |
|---|---|---|---|
| 1.1 | Skill 加载时间 < 100 ms | `$PY -c "import subprocess,time,statistics;ts=[];[ (lambda t: (subprocess.run(['$PY','skills/ai-skill-mcp-Y/scripts/skillmind.py','registry','query','--json'],capture_output=True), ts.append((time.perf_counter()-t)*1000)))(time.perf_counter()) for _ in range(5)];print('median_ms=%.1f'%statistics.median(ts))"` | 中位数 < 100 |
| 1.2 | Token 减少 30%–60% | 按 `benchmarks/runner.md` 跑完整 A/B，读 `.skillmind/reports/benchmark-*.md` | 降幅落在 30%–60% |
| 1.3 | Router 准确率 > 90% | 见下方「§1.3 Router 准确率检查」 | `accuracy > 0.90` |
| 1.4 | 多 Agent 隔离 100% | `$PY skills/ai-skill-mcp-Y/scripts/selftest.py --json` | `isolation` 用例全绿；无跨 agent/project/session 串数据 |
| 1.5 | 三级加载预算成立 | `$PY -c "import sys;sys.path.insert(0,'skills/ai-skill-mcp-Y/scripts');import _common as C;d=C.load_yaml('.skillmind/registry.json');print(sorted({s['load_mode'] for s in d['skills']}))"` | `load_mode ∈ {always,on-demand,deep}`；`always` 项总 tokens ≤ 100 |
| 1.6 | 无效上下文减少 ≥50% | `$PY skills/ai-skill-mcp-Y/scripts/skillmind.py telemetry summary --json` | `context_tokens_loaded` 相对基线降幅 ≥ 50% |

### §1.3 Router 准确率检查

标注表：`BM-01..BM-18` 的期望首选技能。用 `benchmarks/tasks.yaml` 的 18 条任务逐条跑路由并比对。

```bash
$PY - <<'PYEOF'
import json, subprocess, sys
sys.path.insert(0, 'skills/ai-skill-mcp-Y/scripts')
import _common as C

EXPECT = {
    'BM-01': 'ai-code', 'BM-02': 'ai-code', 'BM-03': 'ai-code', 'BM-04': 'ai-code',
    'BM-05': 'ai-code', 'BM-06': 'ai-code', 'BM-07': 'ai-code', 'BM-08': 'ai-code',
    'BM-09': 'ai-design', 'BM-10': 'ai-design', 'BM-11': 'ai-code', 'BM-12': 'ai-code',
    'BM-13': 'ai-code', 'BM-14': 'ai-code', 'BM-15': 'ai-requirement',
    'BM-16': 'ai-design', 'BM-17': 'ai-skill-mcp-Y', 'BM-18': 'ai-skill-mcp-Y',
}

tasks = C.load_yaml('skills/ai-skill-mcp-Y/benchmarks/tasks.yaml')['tasks']
hit = 0
for t in tasks:
    out = subprocess.run(
        [sys.executable, 'skills/ai-skill-mcp-Y/scripts/router.py',
         '--registry', '.skillmind/registry.json', '--task', t['task'],
         '--complexity', t['level'], '--risk', t['risk'], '--json'],
        capture_output=True, text=True).stdout
    rec = (json.loads(out or '{}').get('recommended') or [{}])[0].get('skill_id')
    ok = rec == EXPECT[t['id']]
    hit += ok
    print(f"{t['id']:6} got={rec!s:20} expect={EXPECT[t['id']]:20} {'OK' if ok else 'MISS'}")
print('accuracy=%.3f' % (hit / len(tasks)))
PYEOF
```

通过标准：末行 `accuracy > 0.90`。MISS 条目须逐条给出路由 `reasons` 与硬过滤日志，禁止直接改标注表迎合结果。

---

## 2. 质量指标（spec §13）

| # | 判据 | 验证命令 | 通过标准 |
|---|---|---|---|
| 2.1 | 评分可复现（同输入同输出） | 连跑两次 `$PY skills/ai-skill-mcp-Y/scripts/score.py report --json` | 两次输出逐字节一致 |
| 2.2 | 原始指标与分数同屏 | `$PY skills/ai-skill-mcp-Y/scripts/score.py report --json` | 同时含 `metrics`、`baseline`、`subscores`、`weights`、`score`、`grade` |
| 2.3 | 默认基线被标注 | 不传 `--baseline-json` 执行 `score record` | 输出含 `baseline_defaulted: true` |
| 2.4 | 自动测试四类齐备 | `$PY skills/ai-skill-mcp-Y/scripts/selftest.py --json` | 功能/回归/对抗/Benchmark 四类均有用例且全绿 |
| 2.5 | 自动升级受红线约束 | `$PY skills/ai-skill-mcp-Y/scripts/selftest.py --json` + 人工核对 §3.4 | 进化仅产出建议/候选 patch；无自动删除 Skill、无自动改权限、无自动改生产 Tool |
| 2.6 | 高风险变更须人工审批 | 人工核对进化报告 `.skillmind/reports/` | `risk ∈ {high,critical}` 的候选必须标 `requires_human_approval: true` |

---

## 3. 接口契约（spec §14）

| # | 判据 | 验证命令 | 通过标准 |
|---|---|---|---|
| 3.1 | 统一 CLI 全部子命令可用 | `$PY skills/ai-skill-mcp-Y/scripts/skillmind.py --help` | 含 `registry build/query`、`route`、`score record/report`、`telemetry append/summary`、`manifest validate`、`verify`、`selftest` |
| 3.2 | 子脚本可独立运行 | `$PY skills/ai-skill-mcp-Y/scripts/registry_build.py --json`；`$PY skills/ai-skill-mcp-Y/scripts/router.py --registry .skillmind/registry.json --task "改一个 MyBatis SQL" --json`；`$PY skills/ai-skill-mcp-Y/scripts/score.py report --json`；`$PY skills/ai-skill-mcp-Y/scripts/telemetry.py summary --json`；`$PY skills/ai-skill-mcp-Y/scripts/manifest_validate.py --path skills/ai-skill-mcp-Y/SKILL.md --json` | 各命令退出码 0，且同名参数与调度器一致 |
| 3.3 | `registry.json` 结构合规 | `$PY -c "import sys;sys.path.insert(0,'skills/ai-skill-mcp-Y/scripts');import _common as C;d=C.load_yaml('.skillmind/registry.json');print(d['schema_name'],d['schema_version'],sorted(d));print(d['stats'])"` | `schema_name=skillmind-registry`、`schema_version=1`、含 `skills/rules/mcps/overlap/stats` |
| 3.4 | `route-result.json` 结构合规 | `$PY skills/ai-skill-mcp-Y/scripts/skillmind.py route --task "品牌审核驳回后状态没变" --complexity L2 --risk medium --json` | `schema_name=skillmind-route-result`；含 `method/confidence/recommended/chain/excluded/warnings`；每条推荐带 `reasons` |
| 3.5 | 遥测事件字段完整 | `$PY skills/ai-skill-mcp-Y/scripts/skillmind.py telemetry summary --json` | 事件含 §14.5 全部字段，尤其 `correlation_id`、`p0_evidence_retained`、`error_class` |
| 3.6 | 状态目录正确 | `ls -la .skillmind/` | 出现 `registry.json` / `scores.json` / `telemetry.jsonl`（或空目录待生成），位置为仓根 `.skillmind/` |
| 3.7 | 退出码语义正确 | 故意传错参数跑一次 `skillmind.py route --task` | 返回 `2`；正常校验失败返回 `1`；通过返回 `0` |

---

## 4. Definition of Done（spec §16）

| # | 判据 | 验证命令 | 通过标准 |
|---|---|---|---|
| 4.1 | Registry 可机械生成并消费控制面 | `$PY skills/ai-skill-mcp-Y/scripts/registry_build.py --json` | `sources` 含 `shared/release-manifest.yaml`；`bundled` 与 `deploy.bundle.yaml` 一致 |
| 4.2 | Router 可解释、硬过滤先于打分 | `$PY skills/ai-skill-mcp-Y/scripts/router.py --registry .skillmind/registry.json --task "查日志定位 500" --json` | 每条推荐有 `reasons`；`blocked` 技能不出现在 `recommended`；`excluded` 带理由 |
| 4.3 | 评分可复现 | 同 §2.1 | PASS |
| 4.4 | Gateway 身份/隔离/重试边界 | `$PY skills/ai-skill-mcp-Y/scripts/selftest.py --json` | `gateway` 用例全绿；重试上限有界 |
| 4.5 | 三级加载有预算与落点 | 同 §1.5 | PASS |
| 4.6 | 四层记忆边界写清 | 人工核对 `references/spec-v2.md` §6 与实现 | 项目数据禁入 Skill 经验；`candidate → verified → stale/deprecated` 两态可查 |
| 4.7 | TestMind 四类 + Score Report 模板 | `ls skills/ai-skill-mcp-Y/templates/` | 存在 `skill-score-report.md` |
| 4.8 | 供应链审计评级 | `$PY skills/ai-skill-mcp-Y/scripts/selftest.py --json` | 评级仅取 `SAFE`/`REVIEW`/`BLOCK`；无「高 Star 即可信」逻辑 |
| 4.9 | Hard Gate + Evidence Gate + 回滚 | 见 §5 / §6 | 三者在文档与脚本中均可定位 |
| 4.10 | 裸 Python 3.9+ 无第三方依赖可跑 | `$PY -S -c "import sys;sys.path.insert(0,'skills/ai-skill-mcp-Y/scripts');import _common,_yaml_lite;print('ok')"` | 输出 `ok`；无 `ModuleNotFoundError` |
| 4.11 | 不破坏本仓既有基线 | `$PY scripts/validate_bundle.py --json`；`$PY scripts/verify_skill_drift.py --json` | 均退出码 0，无新增 DRIFT |
| 4.12 | 哈希语义与 `_release_lib` 一致 | `$PY -c "import sys;sys.path.insert(0,'scripts');sys.path.insert(0,'skills/ai-skill-mcp-Y/scripts');import _release_lib as R,_common as C;print(R.hash_tree('shared')['content_hash']);print(C.hash_tree('shared')['content_hash'])"` | 两行完全一致（无假 DRIFT） |
| 4.13 | 基准集可解析且覆盖达标 | `$PY -c "import sys;sys.path.insert(0,'skills/ai-skill-mcp-Y/scripts');import _common as C;d=C.load_yaml('skills/ai-skill-mcp-Y/benchmarks/tasks.yaml');ts=d['tasks'];print(len(ts),sorted({t['kind'] for t in ts}),sorted({t['level'] for t in ts}))"` | ≥15 条；8 类 kind 全覆盖；L0–L3 全覆盖 |
| 4.14 | 常驻摘要 ≤60 行 | `wc -l skills/ai-skill-mcp-Y/references/spec-summary.md` | ≤ 60 |

---

## 5. Hard Gate（任一命中 = FAIL）

| Gate | 判定方式 | 命中后果 |
|---|---|---|
| 丢 P0 证据 | 遥测 `p0_evidence_retained=false`，或报告缺报错原文/失败断言/关键行号/SQL 状态 | FAIL，立即回滚 |
| 成功率下降 | B 侧 `TaskSuccess` < A 侧 | FAIL，立即回滚 |
| 权限扩大 | 新增 `execute`/`admin` 暴露，或 destructive 工具未二次确认 | FAIL，立即回滚 |
| 该用找不到（Recall 崩） | 本应命中的技能进入 `excluded`，或 `recommended` 为空 | FAIL，立即回滚 |
| 只报压缩率 | 报告中成本数字与 `TaskSuccess`/`EvidenceRetention` 未同屏 | FAIL，报告作废 |
| 多层 Router | 全仓出现第二处路由决策实现 | FAIL（spec §9.4） |
| 自动删除低频技能 | 进化产出执行了删除动作 | FAIL（spec §3.4） |

```bash
# Hard Gate 机械可查部分
$PY skills/ai-skill-mcp-Y/scripts/selftest.py --json          # 期望退出码 0
$PY -c "
import sys;sys.path.insert(0,'skills/ai-skill-mcp-Y/scripts');import _common as C
import json
rows=[json.loads(l) for l in open('.skillmind/telemetry.jsonl',encoding='utf-8') if l.strip()] if __import__('pathlib').Path('.skillmind/telemetry.jsonl').exists() else []
bad=[r for r in rows if r.get('p0_evidence_retained') is False]
print('events=%d evidence_lost=%d'%(len(rows),len(bad)))
"
```

---

## 6. 回滚方式

**触发条件**：§5 任一 Hard Gate 命中，或 §1–§4 出现无法当场修复的 FAIL。

```bash
# 0. 记录现场
git rev-parse HEAD > /tmp/skillmind-bad-ref.txt
git status --short

# 1. 首选：revert 升级提交（保留历史，可追溯）
git log --oneline -5
git revert --no-edit <bad-commit>

# 2. 备选：把 skill 目录整体回到上一个已知良好 ref
git checkout <last-good-ref> -- skills/ai-skill-mcp-Y/

# 3. 清掉生成物（生成物不进版本库，回滚必须一并清）
rm -rf .skillmind/registry.json .skillmind/scores.json .skillmind/telemetry.jsonl .skillmind/reports/

# 4. 回滚后复验
$PY skills/ai-skill-mcp-Y/scripts/selftest.py --json      # 期望 0
$PY scripts/validate_bundle.py --json                     # 期望 0
$PY scripts/verify_skill_drift.py --json                  # 期望 0，无新增 DRIFT
```

**回滚边界**：

- 只回滚本 skill 目录与 `.skillmind/` 生成物；**不得**回滚 `shared/` 控制面（属其他 owner）。
- V1 资产（`references/spec-v1.md`、`SKILL.md` 的 `trig:` 行）在 V2 中保留，回滚无需额外恢复文件，见 `docs/MIGRATION.md`。
- 回滚后必须重跑 §1.3（Router 准确率）与 §2.1（评分可复现），确认回到已知良好状态。

---

## 7. 宣称规则

- 未跑完 §1–§4 全部条目，**不得**宣称任何 Phase 达成。
- 未跑完 §1.2 的完整 A/B，**不得**宣称 Token 节约数字。
- 未满足 spec-v1 §25（≥3 真实项目任务 A/B + ≥1 复杂 Debug + ≥1 跨模块），**不得**宣称「生产可用」。
- 当前档位以 `docs/ROADMAP.md` 的「当前档位」一节为准。
