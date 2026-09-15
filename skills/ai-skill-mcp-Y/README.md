# SkillMind Ultimate V2.0

**一句话定位**：Skill 运行层——在几十个 Skill、几百个 Tool 面前，为每个任务挑出**最小充分能力**并只加载**最小充分上下文**；它只做「选」（HOW-选），不做「做」。

- `skill_id`：`ai-skill-mcp-Y`（稳定，禁改）｜产品名：SkillMind｜新增触发词别名：`skillmind`
- 规格真源：[`references/spec-v2.md`](references/spec-v2.md)（V2 定平台形态）· [`references/spec-v1.md`](references/spec-v1.md)（V1 定审计方法论）
- 常驻摘要：[`references/spec-summary.md`](references/spec-summary.md)（≤60 行，日常够用）
- 状态目录：仓根 `.skillmind/`（生成物，不入库）

---

## 目录

```
skills/ai-skill-mcp-Y/
├─ README.md                  ← 本文件：人读入口
├─ SKILL.md                   ← 根路由器（Agent 入口，≤120 行）
├─ skill.yaml                 ← 统一 manifest（校验：scripts/manifest_validate.py）
├─ VERSION                    ← 2.0.0
├─ references/
│  ├─ spec-v2.md              V2 唯一规格来源（§0 定位 / §3 模块 / §13 验收 / §14 契约）
│  ├─ spec-v1.md              V1 全文（审计方法论真源，禁默认整读）
│  ├─ spec-summary.md         常驻摘要（≤60 行）
│  ├─ gateway.md              MCP 网关：身份 / 隔离 / 有界重试
│  ├─ token-loading.md        三级加载与 Token 预算
│  ├─ memory.md               四层记忆边界
│  ├─ testmind.md             四类测试与 Score Report
│  ├─ lifecycle.md            进化生命周期与 CLASSIFY 七类
│  ├─ security.md             权限 / 审计 / 供应链评级
│  ├─ inventory.md            audit 的 inventory 步骤
│  ├─ trigger-tests.md        4 类 trigger + 本 skill 金标
│  └─ apply.md                改动配方
├─ scripts/                   统一 CLI 与子脚本（裸 Python 3.9+，无第三方依赖）
├─ schemas/                   registry / skill-manifest / telemetry-event 契约
├─ templates/
│  ├─ audit-report.md         审计报告模板（V1 保留）
│  ├─ skill-score-report.md   评分报告模板
│  ├─ evolution-log.md        进化留痕模板
│  └─ skill-skeleton/         新 skill 骨架
├─ tests/                     trigger 用例与安全用例
├─ benchmarks/                README.md / tasks.yaml（18 条基准）/ runner.md
└─ docs/                      ROADMAP.md / ACCEPTANCE.md / MIGRATION.md
```

---

## 命令速查

全部命令以**仓根**为工作目录。退出码：`0` 通过 / `1` 校验失败或存在 DRIFT / `2` 用法或环境错误。

| 目的 | 命令 |
|---|---|
| 建注册表 | `python3 skills/ai-skill-mcp-Y/scripts/skillmind.py registry build --json` |
| 查注册表 | `python3 skills/ai-skill-mcp-Y/scripts/skillmind.py registry query --tag java --status verified --json` |
| 路由 | `python3 skills/ai-skill-mcp-Y/scripts/skillmind.py route --task "品牌审核驳回后状态没变" --complexity L2 --risk medium --top 3 --json` |
| 记评分 | `python3 skills/ai-skill-mcp-Y/scripts/skillmind.py score record --skill-id ai-code --metrics-json '<json>' --json` |
| 看评分 | `python3 skills/ai-skill-mcp-Y/scripts/skillmind.py score report --json` |
| 记遥测 | `python3 skills/ai-skill-mcp-Y/scripts/skillmind.py telemetry append --event-json '<json>' --json` |
| 遥测汇总 | `python3 skills/ai-skill-mcp-Y/scripts/skillmind.py telemetry summary --json` |
| 校验 manifest | `python3 skills/ai-skill-mcp-Y/scripts/skillmind.py manifest validate --path skills/ai-skill-mcp-Y/SKILL.md --json` |
| 漂移校验 | `python3 skills/ai-skill-mcp-Y/scripts/skillmind.py verify --json` |
| 自检 | `python3 skills/ai-skill-mcp-Y/scripts/skillmind.py selftest --json` |
| 审计（V1 工作流） | `python3 skills/ai-skill-mcp-Y/scripts/skillmind.py audit --root . --scope all` |
| 仓级校验 | `python3 scripts/validate_bundle.py --json` · `python3 scripts/verify_skill_drift.py --json` |

子脚本可独立运行（同名参数）：`registry_build.py` / `router.py` / `score.py` / `telemetry.py` / `manifest_validate.py` / `selftest.py`。

---

## 与五层栈的关系（禁双开）

```
RequirementMind  → WHAT     做什么（FROZEN 决策）
project-brain    → WHY      为什么 / ADR / 坑
TokenMind        → CTX      读多少 / 从哪读
SkillMind        → HOW-选   选哪个技能 / 用什么链 / 暴露多少工具   ← 本 skill
ai-code/ai-design→ HOW-做   怎么写
TestMind         → VERIFY   真的成了吗
Evidence Gate    → 证据     能不能证明
```

- **只做「选」**：一旦开始写业务码、改生产配置，即越界。
- **唯一权威路由**：运行时路由只有 SkillMind Router 一处；Brain / TokenMind / MCP 只提供输入信号。
- **只读消费控制面**：`shared/release-manifest.yaml`、`shared/capability-registry.yaml`、`shared/schema-versions.yaml`、`deploy.bundle.yaml` 禁反向改写。

---

## 快速开始

```bash
cd <repo_root>                                   # code-mind

# 1. 自检环境
python3 skills/ai-skill-mcp-Y/scripts/skillmind.py selftest --json

# 2. 建注册表（产出 .skillmind/registry.json）
python3 skills/ai-skill-mcp-Y/scripts/skillmind.py registry build --json

# 3. 路由一次，看推荐与理由
python3 skills/ai-skill-mcp-Y/scripts/skillmind.py route \
  --task "改一个 MyBatis SQL，查询条件多一个审核人" --complexity L1 --risk medium --json

# 4. 确认没破坏本仓基线
python3 scripts/validate_bundle.py --json
python3 scripts/verify_skill_drift.py --json
```

---

## 边界与红线

| 项 | 规则 |
|---|---|
| 做什么 | 注册 · 发现 · 路由 · 评分 · 生命周期 · MCP 网关 · 分级加载 · 自动验证 · 长期进化 |
| 不做什么 | 不做 Skill 文件管理器；不做第二个 Router；不取代 RequirementMind / Brain / TokenMind / TestMind；不写业务码 |
| Hard Gate | 丢 P0 证据 / 成功率降 / 权限扩大 / 该用找不到 → FAIL |
| 进化红线 | 可产出 `DISABLE-CANDIDATE` 建议与候选 patch；**禁自动删除 Skill、禁自动改安全权限、禁自动改生产 Tool**；高风险变更须人工审批 |
| 评分纪律 | 原始指标与分数必须同屏；禁止只报压缩率；禁止用分数掩盖事实 |

---

## 相关文档

| 文档 | 内容 |
|---|---|
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Phase 0–3 交付物、验收判据、当前档位 |
| [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) | 可勾选验收表 + 可执行验证命令 + Hard Gate + 回滚 |
| [`docs/MIGRATION.md`](docs/MIGRATION.md) | V1→V2 能力映射、文件迁移、兼容性、回滚、必跑清单 |
| [`benchmarks/README.md`](benchmarks/README.md) | Benchmark 方法论与 `Successful Task Cost` |
| [`benchmarks/runner.md`](benchmarks/runner.md) | 怎么跑、对比维度、报告位置、环境隔离 |
| [`benchmarks/tasks.yaml`](benchmarks/tasks.yaml) | 18 条真实基准任务与 baseline |
