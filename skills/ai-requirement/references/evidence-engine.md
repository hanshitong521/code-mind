# Evidence Engine（P1 · V5）— 统一四元组

目标：让系统里**所有**重要事实（不只是 Reviewer challenge）都带 **结论 / 证据 / 可信度 / 验证方式** 四元组，下游 Agent 可以用同一套语义查询。

## 与已有文件的边界

| 已有 | 角色 | 局限 |
|---|---|---|
| `evidence.json` | Reviewer CHALLENGE → CONFIRMED/PLAUSIBLE/REFUTED | 只覆盖 reviewer 攻击 |
| `evidence-ledger.json` | 可交付主张（性能/完成度）→ FACT/DECISION/TEST/RESULT/RISK | 缺事实/决策的覆盖 |
| `facts.json` | 项目事实 | 没有 verification（怎么验证） |
| `decisions.json` | 冻结决策 | 没有 confidence（0/1） |

`evidence-pack` 是**统一视图**，不取代上面任何文件。

## 四元组

```yaml
- kind:        FACT | DECISION | CHALLENGE | LEDGER
  id:          FACT-001 / DEC-007 / CH-002 / EL-003
  conclusion:  一句话结论
  evidence:    [path:line | FACT id | DEC id | ...]
  confidence:  0.0 ~ 1.0
  verification: 一句可机械执行的检查（grep 命令 / 跑哪个测试 / 查哪个文件）
```

## 规则

- `confidence` 缺省：FACT 来自 `facts.json.confidence`；DECISION 用户冻结 = 0.9、AI 自治 = 0.6；CHALLENGE 来自 `evidence.json.confidence`（V5 起记录，缺省 0.5）；LEDGER 不评。
- `verification` 缺省：FACT 来自 `source.path` 自动生成 grep；DECISION 来自 `impact` 自动生成 `trace impact → ...`；CHALLENGE 来自 `validation` 字段。
- `evidence-pack.json` 是**只读视图**：禁止手改；改回 canonical JSON 后用 `state.mjs evidence-pack --write` 重生成。

## 生成

```bash
node $SKILL/scripts/state.mjs evidence-pack .requirementmind            # 预览（stdout）
node $SKILL/scripts/state.mjs evidence-pack .requirementmind --write    # 写入 evidence-pack.json
```

## 用途

- **Coding Agent**：开工前按 `verification` 字段机械核验四元组是否齐（自动化冒烟）。
- **TestMind**：把 `verification` 直接当成"自动验证"步骤写进测试。
- **Project-Brain**：用 `evidence` 字段做"决定置信度 = evidence 完整度 × DEC 来源"的训练信号。
- **Gate READY 检查**：`fact_items_without_evidence` > 0 → BLOCKED（避免"听说"决策）。

## 与 evidence-ledger 的关系

- `evidence-ledger.json` = **主动声明** 的可交付主张（开发方负责的"接口 P99<200ms"等）。
- `evidence-pack.json` = **聚合视图**（包含 ledger + facts + decisions + challenges 的所有声明）。

两者并列：ledger 是窄但严格的"开发主张账本"；pack 是宽但不写盘的"全量证据视图"。
