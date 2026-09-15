# Decision Memory（P1 · V5）— 决策记忆

目标：把"为什么选 / 为什么拒 / 历史失败"显式落盘，让下次会话不重提已否决方案、不重蹈覆辙。

## 三段式

| 段 | 内容 | 来源 |
|---|---|---|
| **frozen** | 当前有效的冻结决策 + 推荐理由 + **被否决的备选** | `decisions.json` 中 `status=FROZEN` |
| **superseded 链** | 谁 supersede 了谁 | `decisions.json` 中 `status=SUPERSEDED` + `replaced_by` |
| **failure_history** | 跨会话学到的失败模式 | `history/` 各快照中 SUPERSEDED 决策 + 原因 |

## 关键字段

`decision-memory.json`：

```json
{
  "frozen": [
    {
      "id": "DEC-007",
      "topic": "expiration_boundary",
      "decision": "REQUEST_RECEIVED_AT",
      "source": "USER",
      "basis": "Q-007 + FACT-003",
      "rejected_alternatives": [
        { "option": "B. 数据库事务提交时间", "reason": "边界判定分散在事务层与并发层，难统一" },
        { "option": "C. 到期时间一到立即拒绝", "reason": "需要额外时间同步组件，无证据支持必要性" }
      ],
      "created_at": "2026-09-04T10:00:00.000Z"
    }
  ],
  "failure_history": [
    { "at": "history/001-...json", "decision_id": "DEC-003", "summary": "选了 B 选项 → 用户下一轮改 A", "evidence_refs": ["Q-001"] }
  ],
  "superseded_count": 1
}
```

## 写入 `rejected_alternatives`

主 Agent 在 `freeze` 之后，可通过 `state.mjs` 的写入通道补 `rejected_alternatives`（V5 起 schema 允许该字段）。或直接在 JSON 里补 + 跑 `state.mjs validate`。

## 生成

```bash
node $SKILL/scripts/state.mjs decision-memory .requirementmind            # 预览
node $SKILL/scripts/state.mjs decision-memory .requirementmind --write    # 写入 decision-memory.json
```

## 跨会话学习

`failure_history` 跨会话读取：把 `.requirementmind/decision-memory.json` 复制到下一次会话（或通过 `project-brain` 拉取），下次 Phase 3 抛出"同类未答问题"前先比对 failure_history，避免重蹈覆辙（参考 `references/eval.md` 的策略阈值）。

## 与现有决策图的关系

- `decision-graph.json` = 结构化影响图（`impact_scope` 字段）。
- `decision-memory.json` = 决策叙事（`rejected_alternatives` / `failure_history`）。
- `ir/decision.json`（V5 IR） = 上述两者 + canonical decisions 的合并视图（供 Coding Agent 一次性消费）。

## 与 IR 的边界

- IR 的 `ir/decision.json` 是**单会话**视图（只反映当前 `.requirementmind/` 状态）。
- `decision-memory.json` 是**跨会话学习**视图（聚合 `history/` 快照）。
