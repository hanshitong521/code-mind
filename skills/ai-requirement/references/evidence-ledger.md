# Evidence Ledger（P1 · Phase 1）

统一证据账本，与 `evidence.json`（Validator 对 CHALLENGE 的裁决）并列：

| 文件 | 用途 |
|------|------|
| `evidence.json` | Reviewer CLAIM → CONFIRMED/PLAUSIBLE/REFUTED |
| `evidence-ledger.json` | 可交付主张（性能、完成度、合规）必须有 refs |

## 种类

`FACT` | `DECISION` | `TEST` | `RESULT` | `RISK`

## 纪律

禁止在无 `evidence_refs` 条目时输出：

- 「完成」「优化成功」「性能提升 X%」「已验证通过」（除 Gate READY 且对应 EL 已落盘）

## 命令

```bash
node $SKILL/scripts/state.mjs ledger .requirementmind list
node $SKILL/scripts/state.mjs ledger .requirementmind append RESULT "接口 P99<200ms" --refs "reports/latency.md,FACT-012"
node $SKILL/scripts/state.mjs ledger .requirementmind validate
```

Gate READY 前：凡 DEVELOPMENT_SPEC 含可量化验收，须在 ledger 有对应 `RESULT` 或 `TEST` 行（人工/Agent 核对）。
