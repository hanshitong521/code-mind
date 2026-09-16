---
name: requirement-mind
description: AI requirement clarification, adversarial review and spec compilation. Turns a vague one-line requirement into a frozen, evidence-backed DEVELOPMENT_SPEC.md gated by a Requirement Gate, before any coding agent starts. Use when the user says 澄清需求 / 需求追问 / 需求审查 / Requirement Gate / 开始需求分析 / requirementmind, or asks to turn a rough requirement into a dev spec for Codex/Cursor/Claude Code.
---
trig:澄清需求|需求追问|需求审查|Requirement Gate|开始需求分析|requirementmind prio:本页>项目rules
load:本页; ref命中单读; 禁批读; 禁通读 questions.json/conflicts.json
axiom:WHAT 先于 HOW; 取证先于提问; 冻结先于开发; 未过 Gate 禁开发
ssot:阶段细则=references/<phase>.md; 状态结构=state-layout.md; 命令=commands.md; Gate=gate.md

# RequirementMind — 需求澄清、反驳审查与规格编译

干什么: 把一句模糊需求编译成取证、追问、反驳、验证、冻结的开发规格。
产物三层: 人读 `docs/requirementmind/DEVELOPMENT_SPEC.md` · 机读 IR `.requirementmind/ir/*`（V5）· 跨会话记忆 `.requirementmind/decision-memory.json`
定位: **只做 WHAT（做什么），不做 HOW（怎么做）**。写业务码、改生产配置即越界。
Skill home: 本文件所在目录 = `$SKILL`；加载后展开为绝对路径（勿假设安装位置）。
默认最小: 先报告后改；用户说「直接改」才动文件。

## 硬规则（最高优先级，任何阶段不得违反）

- **R1** 需求未过 Requirement Gate，不允许正式开发。
- **R2** 模型推理不是业务事实；项目里查不到的业务规则一律进 UNKNOWN，禁擅自补全。
- **R3** 能取证的问题禁问用户。序：代码 → DB Schema → 接口定义 → 测试 → 历史文档（README/ADR/AGENTS.md/CLAUDE.md）→ Git 历史 → 配置 → 最后才问用户。
- **R4** 用户确认的决策必须冻结（FROZEN），记来源与时间。
- **R5** 冻结决策不可静默覆盖；新旧冲突必须显式 supersede。
- **R6** 每收到一个回答必须重析整个需求，禁机械执行预设问卷。
- **R7** Reviewer 的发现默认不可信，必须二次验证。
- **R8** 无实际证据不得把 challenge 判为 CONFIRMED。
- **R9** 结束追问唯一条件：Blocking Questions=0 且 Blocking Conflicts=0 且 Critical Assumptions=0。
- **R10** 最终规格须让不了解对话历史的 Agent 直接完成开发。
- **R11** authority=TECHNICAL 或 value=LOW 的问题禁问用户：AI 采纳可辩护推荐项自行裁决（`freeze --auto`，source=AI_DEFAULT 附证据 basis）。
- **R12** `stop` 退出码 0 即收敛：禁追加提问、禁「为严谨」加审查轮次；Reviewer/Validator 回流 ≤2 轮。

## 阶段路由（命中才读对应 reference，禁批读）

| 阶段 | 干什么 | 读 |
|---|---|---|
| 0 复杂度路由 | 定 task_level L0–L3，简单改动免全套 | `references/complexity-router.md` |
| 1 上下文扫描 | 扫目标项目（Java 系优先）→ `facts.json` + `PROJECT_FACTS.md`，每条带 `path:line` | `references/scanner.md` |
| 2 需求解析 | 拆 KNOWN / UNKNOWN / CONFLICT / ASSUMPTION 四类分别落盘 | `references/parser.md` |
| 2.5 风险路由 | 八维评分 → LIGHT(0-7) / FOCUSED(8-14) / COUNCIL(15+) | `references/risk-router.md` |
| 3 追问循环 | frontier 取本批 → 整批抛出 → 回答 → freeze → 全量重解析 | `references/grilling.md` · `freezer.md` |
| 4 规格编译 | 从 canonical JSON **单向**生成 `DEVELOPMENT_SPEC.md`（禁手改反向生效） | `references/spec-compiler.md` |
| 4+ IR 生成 | 编译后立即生成 Requirement IR 7 文件，供并行开工 | `references/ir.md` |
| 5 对抗审查 | 全新上下文 subagent 按 tier 派发，产出 CHALLENGE | `references/reviewer.md` · `specialists.md` |
| 6 证据裁决 | 逐条 challenge 重新取证：CONFIRMED / PLAUSIBLE / REFUTED | `references/validator.md` |
| 7 Requirement Gate | 16 项检查表 + 硬门槛计数 → READY / BLOCKED（含 V5 状态机） | `references/gate.md` |
| 8 开发期回流 | `DEVELOPMENT_BLOCKER` → 转 CONFLICT/QUESTION → 重编译 → 重跑 Gate | `references/dev-feedback.md` |
| 收尾 提示词导出 | READY 后导出 4 种 Coding Agent prompt | `templates/agent-prompt.md` |
| 状态 · 命令 · 自测 | 落盘结构 / 20+ 子命令 / `selftest.mjs` | `state-layout.md` · `commands.md` |
| 改本 skill · 攻击测试 | 6 步变更门 / 5 攻击场景 / 会话指标 | `skill-change-gate.md` · `attack-tests.md` · `eval.md` |

**阶段细则不在本页**：L0 可跳过 Phase 5–6（须记 `skipped_phases`）、L2/L3 禁跳过且开发前须 `budget --write`、80% 需求应停在 LIGHT、COUNCIL 五专家全部出场 —— 见对应 reference。

## 铁律摘要（全文见 `references/grilling.md`）

- 每轮整批抛 frontier（只含 **USER_ONLY** 的 BLOCKING+IMPORTANT + OPEN 冲突）；TECHNICAL/LOW 不问（R11）。
- **每问必有推荐** `⭐ 推荐：X` + 可追溯 FACT/`path:line`；缺推荐 → `validate` 失败，禁展示。
- 禁问项目里能查到的（R3）；禁「还有补充吗」空问题；禁代答未答项；说人话 + 一句「为啥要问」。
- 用户改主意用 `freeze --supersede` 显式改判，禁静默覆盖（R5）。
- 省 token：拼批次只用 `frontier`，**禁通读 questions.json/conflicts.json**；回答用 `freeze` 落盘，禁手工改 JSON。

## 下游栈（Gate READY 之后 · 禁本 skill 兼做实现）

职责切分见技能库 `shared/core.md` §pipeline-contract（五层 WHAT/WHY/CTX/HOW/DO）。

- **WHAT 已冻结**：禁用 `/ai-design` 或 `@grilling` 重问同一 FROZEN；HOW（模块/接缝/验证档）才走 `/ai-design`。
- **同步**：`decision_state.json` + `node scripts/sync-requirementmind-brain.mjs`（FROZEN → project-brain）；brain 不得覆盖 FROZEN。
- **CTX**：设计交付经 `handoff_to_task_bundle.py` 写入 `.contextmind/task.active.json`；Java 结构用 `context_orient`（非 brain）。
- **DO**：`/ai-code`。规格与代码冲突 → `DEVELOPMENT_BLOCKER`，禁编码 Agent 私裁。
- **Grill 互斥**：本流程 Phase 3 是 WHAT grilling 唯一入口；未 READY 时禁并行挂 `grilling` skill。

## STOP

STOP:未过 Gate 就开发|模型推理当业务事实|能取证却问用户|静默覆盖 FROZEN|机械执行预设问卷|无证据判 CONFIRMED|为严谨加审查轮次|通读 questions.json 拼批次|手工改 JSON 代替 freeze|编码 Agent 私裁冲突|另挂 grilling 并行|未过 change-gate 前 4 条就改本 skill
