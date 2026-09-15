---
name: ai-skill-mcp-Y
version: 2.0.1
description: >-
  SkillMind — 技能运行层: 注册/路由/评分/网关/三级加载/验证/进化。Use when skillmind、优化skill、
  审计MCP、AGENTS瘦身、技能路由、skill评分、误触发治理、skill大扫除。Not for 业务编码、/ai-code、
  需求冻结、查日志、对账。
---
trig:skillmind|优化skill|审计MCP|AGENTS瘦身|技能路由|skill评分|误触发 prio:本页>项目rules
load:本页; ref命中单读; 禁批读; 禁默认整读 spec-v1/spec-v2
axiom:最小充分上下文; 正确>证据>安全>token; 不加载>不重复>再压缩; 只选不做
ssot:平台=references/spec-v2.md; 审计方法论=references/spec-v1.md; 摘要=references/spec-summary.md

# ai-skill-mcp-Y · SkillMind v2.0

干什么: 注册技能 → 路由选择 → 评分留痕 → 审计治理 → 验证闭环。
定位: **只做「选」(HOW-选), 不做「做」**。写业务码、改生产配置即越界。
默认最小: 先报告后改; 用户说「直接改」才动文件。

## 命令 (spec-v2 §14; 退出码 0通过/1失败或DRIFT/2用法)

| 目的 | cmd |
|---|---|
| 建注册表 | `python3 scripts/skillmind.py registry build [--json]` |
| 查注册表 | `... registry query [--tag T] [--status S] [--category C] [--min-score N]` |
| 路由 | `... route --task "..." [--project-type T] [--risk R] [--complexity L0..L3] [--top N]` |
| 记/看评分 | `... score record --skill-id ID --metrics-json '<json>'` · `... score report` |
| 遥测 | `... telemetry append --event-json '<json>'` · `... telemetry summary` |
| 校验 manifest | `... manifest validate --path <skill.yaml>` |
| 漂移 | `... verify` (原生三层, 与 scripts/verify_skill_drift.py 同语义) |
| 自测 | `... selftest` |
| 审计 | `... audit --scope skill\|mcp\|agents\|all [--out <报告>]` |
| 仓级校验 | `python3 scripts/validate_bundle.py` · `python3 scripts/verify_skill_drift.py` |

状态目录 `<repo_root>/.skillmind/` (生成物, 不入库)。子脚本参数同名, 可独立运行。

## 审计工作流 (V1 方法论, 已机械化为 `audit`)

G0 范围=skill|mcp|agents|all(默认all, 只扫实际存在的) · G1 registry build
G2 audit → 机械 findings · G3 分类 KEEP|OPTIMIZE|MERGE|SPLIT|LAZY-LOAD|DISABLE-CANDIDATE|BLOCK
G4 填 templates/audit-report.md; 未授权改则停 · G5 改: 一次一资源, 配方 references/apply.md
G6 复跑 audit + 4类 trigger; Hard Gate FAIL 则回滚该资源

Hard Gate(任一即 FAIL): 丢P0证据 | 成功率降 | 权限扩大 | 该用找不到(Recall崩) | 假DRIFT(哈希语义不一致)
禁: 自动删灾备/事故/迁移/安全类 skill | 只报压缩率 | 分数掩盖原始指标 | 多层都做 Router | 自动改安全权限
低频≠可删: 90 天不用仍可能是 P0。

## ref (命中才单读)

| 命中 | 读 |
|---|---|
| 平台全文 / 模块细则 | references/spec-v2.md · registry.md · router.md · scoring.md · gateway.md |
| 加载·记忆·验证·进化 | token-loading.md · memory.md · testmind.md · lifecycle.md |
| 安全·遥测·整合 | security.md · observability.md · integration.md |
| 审计方法论 | spec-v1.md(全文) · inventory.md · trigger-tests.md · apply.md |
| 产出模板 | templates/audit-report.md · skill-score-report.md · evolution-log.md · skill-skeleton/ |
| 路线·验收·迁移·基准 | docs/ROADMAP.md · ACCEPTANCE.md · MIGRATION.md · benchmarks/tasks.yaml |

STOP:写业务码|micro-fix|/ai-code|查日志|对账|整读 spec 当开工|自动删 skill|改安全权限|用分数掩盖原始指标
link:/ai-code /ai-design requirement-mind(WHAT) — 只给路由输入, 不代做
