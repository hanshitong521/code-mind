# Complexity Router（P1-01 · Phase 0）

在 Phase 1 Scanner 之前或紧接 Phase 2 Parser 之后，为本次需求定 **task_level**，避免「加字段」与「设计 Agent 平台」走同一重型流程。

## 等级

| Level | 语义 | 典型信号 |
|-------|------|----------|
| **L0** | `simple_change` | 单文件/单字段、明确验收、无 schema 迁移、无新服务 |
| **L1** | `normal_feature` | 默认；多模块但边界清晰 |
| **L2** | `architecture` | 新子系统、跨服务、持久化模型重设、平台级 Agent |
| **L3** | `incident` | 线上故障、回滚、时效优先；时间线驱动 |

## 落盘

写入 `session.json`：

```json
{
  "task_level": "L1",
  "task_level_rationale": "…"
}
```

或由脚本推断后人工确认：

```bash
node $SKILL/scripts/state.mjs route .requirementmind [--write]
```

## 流程裁剪（硬规则）

### L0

- Phase 2.5 Risk：可写 **全 0** 的 `risk.json`（须通过 `state.mjs risk` 校验）。
- Phase 5–6：**可跳过** Adversarial Review / Validator（须在 `session.json` 记 `skipped_phases: ["REVIEW","VALIDATE"]` 与理由）。
- 仍须满足 R9 + Gate 检查表（不得因 L0 绕过 UNKNOWN）。

### L1

- 现有默认流程（Risk Router + LIGHT 为主）。

### L2 / L3

- **禁止**跳过 Phase 5–6。
- `risk` 分层至少 **FOCUSED**；L3 额外要求 `evidence-ledger.json` 首条为 INCIDENT 时间线（`kind=RISK` 或 `RESULT`）。
- 开发前必须存在 `change-budget.json`（`state.mjs budget --write`）。

## 与 Risk Router 关系

- `task_level` 决定 **是否允许轻量路径**。
- `risk.json` 决定 **Reviewer 投入**（LIGHT/FOCUSED/COUNCIL）。
- L2 且 risk 仍为 LIGHT 时：Agent 须上调至少一维 score≥2 或书面说明为何架构变更无额外风险（写入 `task_level_rationale`）。
