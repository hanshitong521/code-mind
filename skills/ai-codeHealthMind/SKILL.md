---
name: ai-codeHealthMind
version: 1.0.0
description: >-
  CodeHealthMind — AI 写完代码后的强制代码健康 Gate。审 diff/commit/range/repo，
  找出死代码·重复·错误抽象·过度设计·复杂度·错误处理·并发·资源·DB·性能·可测试性退化，
  分级（CRITICAL/HIGH/MEDIUM/LOW）→ 证据校验 → 评分 → PASS/WARN/BLOCK/UNKNOWN。
  Triggers: /codehealth, /ai-codeHealthMind, CodeHealthMind, 代码健康, 垃圾代码,
  死代码, 过度设计, 合并准入, 代码质量门.
disable-model-invocation: true
---
encoding:../../shared/core.md
trig:/codehealth|CodeHealthMind|代码健康|垃圾代码|合并准入 prio:rules>this
load:本页; ref/docs 命中单读; 禁批读
axiom:证据优先>删除优先>最小修改; AI≠证据; 不同上下文复审; 高风险跨模型复核; 修复后必重跑 Gate; 工具失败不假绿
ssot:docs/architecture.md schema:docs/finding-schema.md risk:docs/risk-model.md

Goal: 最少 Token、最可靠证据，阻止 AI 把长期维护成本带进生产代码。
Not: 不做需求澄清(→ai-requirement); 不做完整测试策略(→TestMind); 不替代 SAST/编译器; 不大规模重写业务。

# 入口
`python codehealth.py <command> [flags]` — 零依赖，无需 PYTHONPATH；Python ≥3.10。
本机托管解释器损坏时用 `D:\APJ\Anaconda\python.exe`。

# 最小输出契约
退出码：`0` PASS/WARN · `1` BLOCK · `2` 工具或配置错误 · `3` UNKNOWN
判据：compile fail / test fail → BLOCK；CRITICAL（未 accepted_risk）→ BLOCK；HIGH（未 accepted_risk）→ BLOCK；
新增 MEDIUM > `gates.max_new_medium` → BLOCK；≤ 阈值 → WARN；只有 LOW → PASS；
工具降级、无证据缺口 → WARN；工具降级、且影响 HIGH/CRITICAL 取证 → **UNKNOWN**。

# 硬规则（不可破）
- **证据优先**：HIGH/CRITICAL 须带 deterministic 证据；仅语义推断降 MEDIUM。
- **AI ≠ 证据**：LLM 只能说「疑似」，不能证明死代码/性能/并发。
- **删除优先**：先删 → 标准库 → 项目已有能力 → 最后才加抽象。
- **错误抽象 > 重复**：重复**不得自动抽象**；先答 7 问（references/rules.md §3）。
- **上下文隔离**：Reviewer 绝不接收 Writer 的自我解释。默认 A 模式。
- **不随机表决**：两个 Reviewer 冲突 → Evidence Validator 裁决。
- **动态入口安全**：反射/IOC/SPI/MQ/XML/RPC/动态 import 任一命中 → 禁止自动删除。
- **失败降级**：工具缺失 → `TOOL_DEGRADED`；HIGH/CRITICAL 取证依赖它 → `UNKNOWN`（**禁止 PASS**）。
- **语言无覆盖 ≠ 通过**：变更全属无 provider 覆盖语言（Python/Go/Rust/…）→ `UNKNOWN`(3)，非 PASS。
- **修复后必须重跑**：`codehealth verify`。

# ref（命中才单读，禁批读）
| 信号 | 读 |
|---|---|
| 命令 · 目标 · 输出 · 失败排查 | references/cli.md |
| 12 步工作流（§25） · 上下游 PRE/POST-GATE | references/workflow.md |
| `.codehealth.yml` 旋钮 · accepted_risks · 错误抽象 7 问 | references/rules.md |
| 目录结构 · 模块职责 | references/layout.md |
| 架构 · Finding · 风险 · 规则编写 | docs/architecture.md · docs/finding-schema.md · docs/risk-model.md · docs/rule-authoring.md |
| ADR · V2.0 路线图 | docs/adr/ · docs/adr/ADR-004-v2-code-intelligence-roadmap.md |

STOP:需求澄清|完整测试策略|替代 SAST/编译器|大规模重写业务|工具缺失假绿|AI 推断当证据|重复自动抽象|动态入口命中仍自动删除|修复后不重跑 verify|未命中 ref 批读
