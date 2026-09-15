# Requirement IR（P0 · V5）— 机器可读需求中间层

目标：把 `.requirementmind/*.json` 编译为 **机器可读的需求中间层**，让 Coding Agent / Project-Brain / ContextMind / TestMind 都能**零对话历史**消费同一种事实。

## 7 个文件（全部生成在 `.requirementmind/ir/`）

| 文件 | 用途 | 主要消费者 |
|---|---|---|
| `requirement.yaml` | 业务目标 + scope + out_of_scope | Coding Agent（开工前必读） |
| `business-rule.yaml` | 冻结业务规则（每条带 DEC id） | Coding Agent（硬约束） / TestMind（验收依据） |
| `workflow.yaml` | 状态机 / 流程 | Coding Agent / TestMind（状态机测试） |
| `risk.yaml` | 八维风险评分 + 路由专家 | Project-Brain（决定模块化粒度）/ Coding Agent（防御深度） |
| `acceptance.yaml` | 验收标准 + 必填测试 | TestMind（生成测试用例） |
| `decision.json` | 决策（含 `rejected_alternatives` / `failure_history`） | 全部（决策审计） |
| `trace.json` | 追溯链（FACT → DEC → 影响面） | 全部（解释链路） |

## 生成

```bash
node $SKILL/scripts/state.mjs ir .requirementmind            # 预览（stdout）
node $SKILL/scripts/state.mjs ir .requirementmind --write    # 写入 .requirementmind/ir/
```

## 原则

- **单向**：canonical JSON → IR（`state.mjs ir`）。禁止手改 IR 后反向写回 JSON（与 DEVELOPMENT_SPEC.md 的单向生成一致）。
- **R10 自足**：每个 IR 文件对完全不了解对话历史的 Agent 必须可独立读懂。
- **消费方契约**：Coding Agent 开工前必读 `requirement.yaml` + `business-rule.yaml` + `acceptance.yaml`；TestMind 优先消费 `acceptance.yaml` + `workflow.yaml`。
- **不是新存储**：不取代 `.requirementmind/*.json`，只把它们编译成下游更易消化的形态。

## 与现有产物关系

| 已有 | IR 等价 | 关系 |
|---|---|---|
| `docs/requirementmind/DEVELOPMENT_SPEC.md` | `ir/requirement.yaml + business-rule.yaml + acceptance.yaml` | 同一事实的 Markdown 视图 vs YAML 视图 |
| `decisions.json` | `ir/decision.json` | 同一决策的不同表达（IR 加 `rejected_alternatives` / `failure_history`） |
| `risk.json` | `ir/risk.yaml` | 同评分（IR 加专家路由到 specialist 节） |
| `gate.json` | `ir/acceptance.yaml` | 同检查表（IR 拆出 GATE-READY / GATE-BLOCKED 节点） |
| `decision-graph.json` | `ir/trace.json` | 同一影响图（IR 显式列 evidence_refs） |

## 何时生成

1. Phase 4 编译完 SPEC.md 后立即生成（让 Coding Agent / TestMind 可以并行开工）。
2. Phase 6 产生新决策回流后重生成（IR 自动反映 supersede 链）。
3. Phase 7 Gate READY 时不重生成（仅校验 IR 与 gate.json 一致）。
