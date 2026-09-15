# MIGRATION — V1 → SkillMind Ultimate V2.0

> 迁移目标：V1 的「审计方法论」不丢，V2 的「运行层」补上。二者互补不互斥（`references/spec-v2.md` §8 冲突裁决）。
> 迁移不改 `skill_id`、不改触发词主键，属**增量升级**，非重写。

---

## 1. 定位差异（一句话）

| 版本 | 是什么 | 产物 |
|---|---|---|
| V1 | Skill / MCP / AGENTS 的**审计与治理方法论**（只读审计 + 报告 + 配方） | `audit-report.md`、inventory、4 类 trigger 结论 |
| V2 | **Skill 运行层**：注册 · 发现 · 路由 · 评分 · 生命周期 · MCP 网关 · 分级加载 · 自动验证 · 长期进化 | `registry.json`、`route-result.json`、`score-record.json`、`telemetry.jsonl`、Skill Score Report |

V2 只做「选」（HOW-选），不做「做」（HOW-做）；V1 的审计仍是 V2 发现问题的手段。

---

## 2. V1 能力保留映射

| V1 能力 | V1 落点 | V2 去向 | 保留方式 |
|---|---|---|---|
| Skill 审计（inventory → 分类 → 改 → 复跑 trigger） | `SKILL.md` G0–G6 + `references/inventory.md` + `references/apply.md` | V2 子命令 `audit`（`scripts/skillmind.py audit`），内部复用 `scripts/inventory.py` | 原样保留，G0–G6 流程不变 |
| MCP 审计（standing vs on-demand、单任务暴露个数） | `references/inventory.md` MCP 行 + 4 类 trigger | 同上，`audit` 的 MCP 域；暴露预算改由 `shared/capability-registry.yaml` 的 `tool_budget` 提供 | 审计标准不变，预算真源外移到控制面 |
| AGENTS / Rules 审计（必读清单 vs 导航地图） | `references/inventory.md` AGENTS 行 | 同上，`audit` 的 agents 域 | 判据不变 |
| 4 类 Trigger 测试 | `references/trigger-tests.md` + `tests/trigger-cases.md` | `audit` 的必跑步骤；纳入 TestMind 四类测试 | 金标表逐行保留 |
| 100 分评分体系 | `references/spec-v1.md` §18 | V2 §3.3 五维加权（成功率 40 / 准确率 30 / Token 效率 15 / 速度 10 / 稳定性 5） | **双轨**：V1 的 100 分用于「审计结论」，V2 的分用于「技能评分」，禁混用同一数字 |
| Hard Gate / Evidence Preservation | `SKILL.md` Hard Gate 行 | V2 §16 + `docs/ACCEPTANCE.md` §5 | 判据原样，改为可勾选验收表 |
| 上线门槛 | `references/spec-v1.md` §25 | V2 §7 + `docs/ACCEPTANCE.md` §7 | 保留，并补 Benchmark 前置 |
| 自动治理生命周期 CLASSIFY 七类 | `references/spec-v1.md` §19 | V2 §3.4 | 原样保留；新增红线「禁止自动删除」 |
| 供应链安全审计 | `references/spec-v1.md` §10 域 | V2 §10 SAFE/REVIEW/BLOCK | 原样保留 |

**`audit` 入口说明**：`references/spec-v2.md` §14.1 列出的 10 个子命令是**必须实现的最小集**；
`audit` 是在其之上的审计入口（V1 工作流的机器化封装），与 §14.1 不冲突。
若某宿主尚未提供 `audit`，等价路径 = 依次执行 `scripts/inventory.py` → `tests/trigger-cases.md` 四类 →
填 `templates/audit-report.md`，判据与 `audit` 完全一致。

---

## 3. 文件迁移表

### 3.1 保留（内容不变或仅小幅增补）

| V1 文件 | V2 去向 | 说明 |
|---|---|---|
| `references/spec-v1.md` | 原位保留 | 审计方法论真源；**禁默认整读**，仅点名时读 |
| `references/inventory.md` | 原位保留 | `audit` 的 inventory 步骤参考 |
| `references/trigger-tests.md` | 原位保留 | 4 类 trigger + 本 skill 金标 |
| `references/apply.md` | 原位保留 | 改动配方 |
| `templates/audit-report.md` | 原位保留 | 审计报告模板 |
| `tests/trigger-cases.md` | 原位保留 | trigger 用例 |
| `scripts/inventory.py` | 原位保留 | 被 `audit` 复用 |
| `Skill_MCP_Governance_Ultimate_Development_Spec_V1.md` | 原位保留 | 跳转桩，指向 `references/spec-v1.md` |

### 3.2 更新

| 文件 | V1 状态 | V2 变化 |
|---|---|---|
| `SKILL.md` | 根文档（G0–G6 + Hard Gate + STOP） | 保留为**根路由器**；`name` / `description` frontmatter 保留；`trig:` 行新增别名 `skillmind`；正文 ≤120 行；新增指向 `references/spec-v2.md`、`docs/`、`benchmarks/` 的 ref 指针 |
| `references/spec-summary.md` | V1 摘要（16 行） | 更新为 V2 摘要；V1 要点收进「审计方法论（V1 保留）」段；**全文 ≤60 行** |

### 3.3 新增

| V2 文件 | 作用 | 对应 spec |
|---|---|---|
| `README.md` | 人读入口：定位、目录树、命令速查、五层栈关系、快速开始 | §8 |
| `skill.yaml` | 统一 manifest（`id/version/triggers/risk/loading/security_permissions`） | §8、§17 |
| `VERSION` | 版本号 `2.0.0` | §0 |
| `references/spec-v2.md` | V2 唯一规格来源 | — |
| `references/gateway.md` / `token-loading.md` / `memory.md` / `testmind.md` / `lifecycle.md` / `security.md` | 六大模块细则展开（命中才读） | §4–§7、§10 |
| `scripts/skillmind.py` | 统一 CLI 调度 | §14.1 |
| `scripts/registry_build.py` / `router.py` / `score.py` / `telemetry.py` / `manifest_validate.py` / `selftest.py` | 可独立运行的子脚本 | §14.1 |
| `scripts/_common.py` / `_yaml_lite.py` | 共享底座（YAML 装载、哈希、路径、输出） | §14.1 |
| `schemas/registry.schema.json` / `skill-manifest.schema.json` / `telemetry-event.schema.json` | 契约 schema | §14.2、§14.5、§17 |
| `templates/skill-score-report.md` / `evolution-log.md` / `skill-skeleton/` | 评分报告、进化留痕、新 skill 骨架 | §7、§8 |
| `benchmarks/README.md` / `tasks.yaml` / `runner.md` | 基准任务、方法论、执行方式 | §7、§13 |
| `docs/ROADMAP.md` / `ACCEPTANCE.md` / `MIGRATION.md` | 路线、验收、迁移 | §12、§13、§16 |
| 根 `.skillmind/` | 生成物目录（`registry.json` / `scores.json` / `telemetry.jsonl`） | §14.1 |

### 3.4 不变的外部契约

| 外部依赖 | 关系 |
|---|---|
| `shared/release-manifest.yaml` | 只读消费（`bundled` 与 `hash` 来源） |
| `shared/capability-registry.yaml` | 只读消费（阶段映射 + `tool_budget`） |
| `shared/schema-versions.yaml` | 只读消费（版本兼容判定） |
| `deploy.bundle.yaml` | 只读消费（`bundled` 判定） |
| `scripts/_release_lib.py` | 哈希语义必须逐字节等价（禁假 DRIFT） |
| `scripts/validate_bundle.py` / `verify_skill_drift.py` | 迁移后必须仍为 0 |

> 注意：`ai-skill-mcp-Y` **不在** `deploy.bundle.yaml` 的 `skills` 列表内，因此注册表中该项
> `bundled` 应为 `false`、`source` 为 `filesystem`。迁移时不得为「好看」把它塞进 bundle。

---

## 4. 兼容性

| 项 | V1 | V2 | 兼容结论 |
|---|---|---|---|
| `skill_id` | `ai-skill-mcp-Y` | `ai-skill-mcp-Y` | **不变**，禁改（注册表主键） |
| 目录 | `skills/ai-skill-mcp-Y/` | 同 | **不变** |
| 触发词 | `优化skill` / `审计MCP` / `AGENTS瘦身` / `误触发` / `governance` | 全部保留，**新增别名 `skillmind`** | 向后兼容；旧句仍命中 |
| `trig:` 行 | `trig:优化skill\|审计MCP\|...` | 原串 + `skillmind` | 追加式，非替换 |
| 产品名 | 无 | SkillMind | 仅命名，不改 id |
| STOP 条件 | 写业务码 / micro-fix / `/ai-code` / 查日志 / 对账 / 整读 V1 | 全部保留 | 不变 |
| Hard Gate | 丢 P0 证据 / 成功率降 / 权限扩大 / 该用找不到 | 全部保留 + 新增「只报压缩率」「多层 Router」「自动删除低频技能」 | 只增不减 |
| V1 默认加载 | 根 `SKILL.md` + `spec-summary.md` | 同 | 不变 |
| `spec-v1.md` 定位 | 全文规格 | 审计方法论真源，禁默认整读 | 定位调整，内容不变 |
| 退出码 | 无约定 | `0` 通过 / `1` 校验失败或 DRIFT / `2` 用法或环境错误 | 新增，不与 V1 冲突 |
| 状态目录 | 无 | 仓根 `.skillmind/` | 新增，生成物不入库 |

**破坏性变更**：无。V2 是 V1 的超集，V1 的审计流程与判据全部保留。

---

## 5. 迁移步骤

```bash
cd <repo_root>                                   # code-mind
PY=python3
git rev-parse HEAD                               # 记录迁移前 ref，回滚用
```

1. **冻结**：迁移期间不改 `shared/` 控制面四文件与 `scripts/` 仓级脚本。
2. **落地文件**：按 §3.1–§3.3 建目录与文件（`docs/`、`benchmarks/`、`schemas/`、`scripts/` 新增项）。
3. **根文档瘦身**：`SKILL.md` 保留 G0–G6 与 Hard Gate，`trig:` 追加 `skillmind`，正文 ≤120 行。
4. **摘要替换**：`references/spec-summary.md` 换成 V2 摘要 + 「审计方法论（V1 保留）」段，行数 ≤60。
5. **生成产物**：`$PY skills/ai-skill-mcp-Y/scripts/skillmind.py registry build --json`。
6. **跑必跑清单**（见 §6）。
7. **提交**：单 commit 记录迁移前后 ref；`.skillmind/` 生成物不入库。

---

## 6. 迁移后必跑清单

| # | 命令 | 期望 |
|---|---|---|
| 1 | `$PY skills/ai-skill-mcp-Y/scripts/selftest.py --json` | 退出码 0，全绿 |
| 2 | `$PY skills/ai-skill-mcp-Y/scripts/skillmind.py registry build --json` | 退出码 0，产出 `.skillmind/registry.json` |
| 3 | `$PY skills/ai-skill-mcp-Y/scripts/skillmind.py registry query --json` | 退出码 0；`ai-skill-mcp-Y` 自身在册 |
| 4 | `$PY skills/ai-skill-mcp-Y/scripts/skillmind.py route --task "优化一下 skills 触发器" --json` | `recommended` 含 `ai-skill-mcp-Y`（V1 触发词仍命中） |
| 5 | `$PY skills/ai-skill-mcp-Y/scripts/skillmind.py route --task "改 TRedPacketTaskServiceImpl 空指针" --json` | **不含** `ai-skill-mcp-Y`（negative 用例仍正确） |
| 6 | `$PY skills/ai-skill-mcp-Y/scripts/skillmind.py route --task "审计 MCP tool 暴露" --json` | 含 `ai-skill-mcp-Y`（MCP 审计入口保留） |
| 7 | `$PY skills/ai-skill-mcp-Y/scripts/skillmind.py route --task "skillmind 帮我看看该用哪个技能" --json` | 含 `ai-skill-mcp-Y`（新别名生效） |
| 8 | `$PY skills/ai-skill-mcp-Y/scripts/skillmind.py score report --json` | 退出码 0；原始指标与分数同屏 |
| 9 | `$PY skills/ai-skill-mcp-Y/scripts/skillmind.py manifest validate --json` | 退出码 0 |
| 10 | `$PY skills/ai-skill-mcp-Y/scripts/skillmind.py verify --json` | 退出码 0，无 DRIFT |
| 11 | `$PY scripts/validate_bundle.py --json` | 退出码 0 |
| 12 | `$PY scripts/verify_skill_drift.py --json` | 退出码 0，无新增 DRIFT |
| 13 | `$PY -c "import sys;sys.path.insert(0,'scripts');sys.path.insert(0,'skills/ai-skill-mcp-Y/scripts');import _release_lib as R,_common as C;print(R.hash_tree('shared')['content_hash']==C.hash_tree('shared')['content_hash'])"` | `True`（哈希语义一致） |
| 14 | `$PY -c "import sys;sys.path.insert(0,'skills/ai-skill-mcp-Y/scripts');import _common as C;d=C.load_yaml('skills/ai-skill-mcp-Y/benchmarks/tasks.yaml');print(len(d['tasks']))"` | `18` |
| 15 | `wc -l skills/ai-skill-mcp-Y/references/spec-summary.md` | ≤ 60 |
| 16 | 人工核对 `SKILL.md` 行数 | ≤ 120 行 |

全部通过后方可宣称迁移完成；`docs/ACCEPTANCE.md` §1–§4 仍须单独跑完才可宣称 Phase 达成。

---

## 7. 回滚

**触发条件**：§6 任一项 FAIL，或 `docs/ACCEPTANCE.md` §5 Hard Gate 命中。

```bash
# 1. 首选：revert 迁移提交（保留历史）
git log --oneline -5
git revert --no-edit <migration-commit>

# 2. 备选：skill 目录整体回到迁移前 ref
git checkout <pre-migration-ref> -- skills/ai-skill-mcp-Y/

# 3. 清理生成物（不入库，回滚必须一并清）
rm -rf .skillmind/registry.json .skillmind/scores.json .skillmind/telemetry.jsonl .skillmind/reports/

# 4. 复验
$PY skills/ai-skill-mcp-Y/scripts/selftest.py --json
$PY scripts/validate_bundle.py --json
$PY scripts/verify_skill_drift.py --json
```

**回滚边界**：

- 只回滚 `skills/ai-skill-mcp-Y/` 与 `.skillmind/` 生成物；`shared/` 与仓级 `scripts/` 不属本 skill，禁动。
- V1 资产在 V2 中全部保留（§3.1），回滚不需要额外恢复文件；`git checkout` 后 V1 的 `SKILL.md` 与
  `spec-v1.md` 即为可用状态。
- 回滚后必须重跑 §6 的 11、12 两条，确认控制面未被污染。
