# commands · state.mjs 子命令清单

> 从根 `SKILL.md` 外移（V5.1 瘦身）。全部子命令由 `$SKILL/scripts/state.mjs` 提供。
> 参数与调度器一致，可独立运行。改动本 skill 后必跑 `node $SKILL/scripts/selftest.mjs`。

## 分阶段

| 阶段 | 命令 |
|---|---|
| 0 复杂度路由 | `route    .requirementmind [--write]` — L0–L3 分层 |
| 2.5 风险路由 | `risk     .requirementmind [--write]` — 八维评分 → LIGHT/FOCUSED/COUNCIL + 专项；COUNCIL=五专家强制派发（V5） |
| 3 追问 | `frontier .requirementmind` — 本批待决项 + 计数；**退出码 0 = R9 达成** |
| 3 冻结 | `freeze   .requirementmind Q-007 B [--supersede] [--auto] [--impact "a,b"]` — 冻结答案 → DEC（`--auto`=AI 自治） |
| 3 出口 | `stop     .requirementmind` — 停止条件（R9+覆盖率）；**退出码 0 = 收敛** |
| 4 规格编译 | `ir           .requirementmind [--write]` — V5 P0：生成 Requirement IR 7 文件 |
| 7 Gate | `gate     .requirementmind` — Gate 硬门槛汇总 |
| 7 状态机 | `gate-state   .requirementmind [--to NODE] [--reason "…"]` — V5 P0：节点 + 迁移 |

## 校验 / 维护

| 命令 | 作用 |
|---|---|
| `counters .requirementmind` | 四项关键计数 |
| `validate .requirementmind` | JSON 结构校验 |
| `snapshot .requirementmind` | 快照到 `history/` |
| `migrate  .requirementmind [--write]` | 旧 questions 补推荐字段（预览/写入） |
| `budget   .requirementmind [--write] [...]` | Change Budget（L2/L3 必填） |
| `eval     .requirementmind` | 会话指标（自治率 / 验真率），供 Eval 闭环 |

## 证据 / 记忆（V5 P1）

| 命令 | 作用 |
|---|---|
| `ledger         .requirementmind list\|validate\|append` | 可交付主张证据账 |
| `impact-graph   .requirementmind [--write]` | Decision Impact Graph |
| `context        .requirementmind` | Decision Context Contract JSON（跨栈消费） |
| `evidence-pack  .requirementmind [--write]` | 统一四元组视图（结论 / 证据 / 可信度 / 验证方式） |
| `decision-memory .requirementmind [--write]` | 跨会话决策记忆（rejected_alternatives + failure_history） |

## 自测

```bash
node $SKILL/scripts/selftest.mjs      # 确定性自测（含 5 攻击测试场景）
```

修改本 Skill 须遵守 `references/skill-change-gate.md`（禁止无证据自改）。

## STOP

STOP:绕过 state.mjs 手改状态 JSON|未跑 validate 就进下一阶段|`stop` 退出码 0 后追加提问
