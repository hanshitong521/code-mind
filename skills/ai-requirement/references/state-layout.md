# state-layout · 状态目录结构

> 从根 `SKILL.md` 外移（V5.1 瘦身）。所有状态写在**目标项目根目录** `.requirementmind/`，
> **不依赖聊天记忆**。会话中断后从这里恢复，禁止凭聊天记忆续跑。
> Schema 定义：`$SKILL/schemas/state.schema.json`。校验：`node $SKILL/scripts/state.mjs validate .requirementmind`。

```
.requirementmind/
├── session.json           # 当前阶段游标 + 需求原文 + Gate 状态机节点（V5）
├── facts.json             # FACT-xxx 项目事实（带文件级证据）
├── questions.json         # Q-xxx   问题（priority: BLOCKING|IMPORTANT|OPTIONAL）
├── decisions.json         # DEC-xxx 冻结决策（FROZEN | SUPERSEDED
│                          #         + rejected_alternatives / failure_history V5）
├── assumptions.json       # ASM-xxx 模型推断（risk: HIGH|MEDIUM|LOW）
├── conflicts.json         # CON-xxx 冲突（severity: BLOCKING|IMPORTANT）
├── challenges.json        # CH-xxx  Reviewer 的 CLAIM
├── evidence.json          # 裁决：CONFIRMED | PLAUSIBLE | REFUTED（含 confidence / verification V5）
├── gate.json              # Gate 检查表 + 最终状态
├── evidence-ledger.json   # 可交付主张证据账（P1）
├── evidence-pack.json     # 统一四元组视图（V5，evidence-engine）
├── change-budget.json     # 开发变更上限（L2/L3 必填）
├── decision-graph.json    # 决策影响图（由脚本生成）
├── decision-memory.json   # 跨会话决策记忆（V5，含 rejected_alternatives / failure_history）
├── ir/                    # Requirement IR 7 文件（V5 P0）：
│                          #   requirement / business-rule / workflow / risk / acceptance yaml
│                          #   + decision / trace json
└── history/               # 每轮快照
```

## 状态文件与阶段的对应

| 文件 | 谁写 | 何时 |
|---|---|---|
| `session.json` | `state.mjs route` / `gate-state` | Phase 0 起，全程维护阶段游标 |
| `facts.json` | Phase 1 Context Scanner | 每条带 `path:line` 证据 |
| `questions.json` / `conflicts.json` / `assumptions.json` | Phase 2 Requirement Parser | 由 UNKNOWN 生成，每条标 `authority` + `value` |
| `decisions.json` | `state.mjs freeze` | 每收到一个回答立即落盘（**禁手工改 JSON**） |
| `challenges.json` | Phase 5 Reviewer | status=PENDING_VALIDATION |
| `evidence.json` | Phase 6 Validator | 逐条 challenge 裁决 |
| `gate.json` | `state.mjs gate` | Phase 7，16 项检查表 + 硬门槛计数 |
| `ir/` | `state.mjs ir --write` | Phase 4 规格编译完成后 |
| `decision-memory.json` | `state.mjs decision-memory --write` | 跨会话记忆（V5 P1） |
| `change-budget.json` | `state.mjs budget --write` | L2/L3 开发前必填 |

## 跨栈 Contract

`state.mjs context` 导出 `shared/schemas/decision-context.contract.json` 形状，
供 ConciseMind HANDOFF / AI-Code / TestMind 消费。
升级设计见 `shared/docs/RequirementMind_ConciseMind_Peak_Upgrade_Specification_v2.md`。

## STOP

STOP:凭聊天记忆续跑|手工改 JSON 代替 freeze|项目数据写进 Skill 经验层|跳过 validate 就进下一阶段
