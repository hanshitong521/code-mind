# Eval 闭环（收尾 + Phase 8 之后）

目标：让系统知道自己问多了还是问少了、审对了还是审歪了，下次会话按数据调整策略。

## 会话内指标（确定性，脚本算）

```bash
node $SKILL/scripts/state.mjs eval .requirementmind
```

输出：`should_ask_by_policy / answered_total / user_decisions / ai_decisions / autonomy_rate / review{CONFIRMED,PLAUSIBLE,REFUTED,refuted_rate} / snapshots`。

Gate READY 后把输出 JSON 存为 `.requirementmind/eval.json`（schema 见 schemas/state.schema.json 的 eval 节），并随 snapshot 入 `history/`。

## 开发后回填（Phase 8 结束时）

更新 `eval.json` 补充三个字段：
- `missed_requirements` — 开发期 DEVELOPMENT_BLOCKER 揭示的遗漏需求数
- `rework_count` — 因需求不清导致的返工次数
- `not_ask_me` — 用户说"这个不用问我"的次数
- `lessons` — 一句话策略调整结论（按下表）

## 策略阈值（下次会话生效）

| 指标 | 判读 | 调整动作 |
|---|---|---|
| autonomy_rate < 60% | authority 判定过严，问了太多该自己定的 | 下次把纯工程项标 TECHNICAL（R11） |
| refuted_rate > 40% | Reviewer 过激，伪问题多 | 派发时强调 confidence 校准（<0.6 不输出） |
| CONFIRMED ≈ 0 且 missed_requirements > 0 | 审查没抓到真问题、扫描漏维度 | 下次 Phase 1 扩大对应维度扫描，risk 对应维度提分 |
| rework_count > 0 | 规格与代码现实脱节 | 检查 Impact Analysis 章节（spec-compiler.md）是否敷衍 |
| not_ask_me > 0 | 具体问题 authority 标错 | 该问题类型下次默认 TECHNICAL |

## 攻击测试指标（V5）

按 `references/attack-tests.md` 列出的 5 类场景，selftest 必跑。每次跑记录到 `eval.json`：

```json
{
  "attack_tests": {
    "payment_refund":    { "ran": true, "found_hidden_issues": 2, "blocked_wrong_dev": true, "generated_acceptance": true },
    "ten_million_db":    { "ran": true, "found_hidden_issues": 1, "blocked_wrong_dev": true, "generated_acceptance": true },
    "ai_agent_arch":     { "ran": true, "found_hidden_issues": 3, "blocked_wrong_dev": true, "generated_acceptance": true },
    "permission_system": { "ran": true, "found_hidden_issues": 2, "blocked_wrong_dev": true, "generated_acceptance": true },
    "high_concurrency":  { "ran": true, "found_hidden_issues": 1, "blocked_wrong_dev": true, "generated_acceptance": true }
  }
}
```

任何一类 4 个子项（found_hidden_issues / blocked_wrong_dev / generated_acceptance / ran）不全 → 视为该场景覆盖失败，Gate 升级到 FOCUSED。

## 硬约束

- eval.json 只记录指标与调整结论，禁止把对话流水账写进去。
- 跨会话对比时读各 `history/` 快照里的 eval.json，不凭印象说"上次好像问多了"。
