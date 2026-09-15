# Change Budget（P1-03 · Phase 2）

开发前上限，防止 AI 大范围重构。

## 默认建议

| task_level | files | modules | database | new_service |
|------------|-------|---------|----------|-------------|
| L0 | 3 | 1 | false | false |
| L1 | 10 | 2 | false | false |
| L2 | 25 | 5 | true | false |
| L3 | 15 | 3 | false | false |

L3 偏热修，文件数可紧但须列明 `rationale`。

## 落盘

`.requirementmind/change-budget.json`

```bash
node $SKILL/scripts/state.mjs budget .requirementmind [--write]
node $SKILL/scripts/state.mjs budget .requirementmind --write --files 8 --modules 2 --database false
```

Coding Agent 超出预算须输出 `DEVELOPMENT_BLOCKER`（见 `dev-feedback.md`），不得静默扩 scope。
