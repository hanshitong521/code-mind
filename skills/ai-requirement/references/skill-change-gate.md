# Skill Change Gate（P1-04 · Phase 3）

修改 **本仓库** `SKILL.md`、`references/`、`scripts/state.mjs` 或 **concise-mind** 等价物时，禁止静默自改。

## 必走流程

1. **修改原因** — 对应 Spec v2 条目或失败用例
2. **失败证据** — `selftest` 输出、Eval、或生产 incident
3. **影响分析** — 哪些 Gate（RM0–RM8）、下游 Contract 字段
4. **人工确认** — PR 或显式用户「批准改 skill」
5. **版本升级** — manifest / changelog 一行
6. **回滚方案** — git revert 或上一版 manifest 路径

未满足 1–4 时：Agent **只读** skill，可提议 diff 但不写入 skill 目录。
