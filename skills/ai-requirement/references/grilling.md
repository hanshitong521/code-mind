# Grilling Engine 规则（Phase 3）— 批量提问模式

目标：只问真正影响开发结果的问题，整批抛出，答后重推演，直到关键疑问清零。

**呈现原则（对用户可见）**：说人话、先讲清「为啥要问」，**每问必有推荐**；推荐是默认建议，用户选别的照常冻结，不得劝说改选。

与 **concise-mind Explain 档**对齐：`audience: engineer` — 先结论、术语第一次附一句白话；比喻可简化「怎么做」，不可错「能不能」。

## 循环

```
分析全需求 → 收集当前所有 OPEN 的 BLOCKING 问题（含 IMPORTANT）
→ 一批全部抛出（等待用户逐个回答）
→ 逐个冻结（见 freezer.md）
→ 全量重新解析（见 parser.md，R6）
→ 还有新问题？整批再抛；否则出口
```

- **一批 = 当前 frontier**：所有前置已就绪、现在就能问的问题。某问题的选项依赖另一个未答问题时，归入下一批，不混入本批。
- 用户回答后**必须**全量重推演：答案可能解开一批 UNKNOWN，也可能暴露更深层问题（追加新编号，不覆盖旧行）。
- 禁止从预设问卷机械往下念——每批都从当前状态重新计算。
- 用户没有明确回答的问题保持 OPEN，下一批继续带上，禁止擅自代答。

## 问题格式（固定）

每条 USER_ONLY 问题落盘 `questions.json` 后，向用户展示时**必须**包含四块：

1. **白话问句** — 把 `question` 翻成「你一听就懂」的一句（可保留 ID 如 Q-001 便于 freeze）
2. **为啥要问** — 一句话：不确认会怎样（对应 `reason`，禁止长篇背景）
3. **选项** — 2~5 个，字母 A/B/C… 与 `options` 一致
4. **⭐ 推荐** — `recommended_option` 字母 + `recommendation_reason`（必须可追溯到 FACT 或 `path:line`；没有证据则先取证或标 UNKNOWN，**禁止空推荐**）

### 文字列表模板（默认）

```
❓ Q7｜红包快过期时有人同时来领，算过期还是算还能领？

为啥要问：这会决定代码里「抢锁 / 判过期」谁先谁后，搞错会多发或少发。

A. 以请求到达服务器的时间为准
B. 以数据库事务提交的时间为准
C. 一到过期时间就立刻拒绝
D. 沿用现有业务规则（请注明出处）

⭐ 推荐：A — FACT-003 现有防重已在请求入口实时判，和到期判定放同一处最不容易打架。
```

### 下拉框模板（可选，适合 2~4 个互斥选项）

当本批 **≤4 问** 且每问 **2~5 个选项** 时，可用 Cursor `AskQuestion` 工具抛表单；**仍须**在问题正文或选项 label 里标出推荐：

- 推荐项 label 后缀 `(推荐)`，例如 `A. 以请求到达服务器的时间为准 (推荐)`
- 表单上方或下方**单独一行**：`⭐ 推荐：A — <recommendation_reason 白话版>`
- 多题时可 `AskQuestion` 连抛，或一题一表单；**禁止**因用了下拉就省略推荐行

**硬门**：`recommended_option` 或 `recommendation_reason` 缺失 → `validate` 失败，**不得**向用户展示该问（先补推荐再抛）。

## 禁止问的问题

- "还有其他补充吗？" / "你希望效果怎么样？" / "你有没有特别要求？"
- 项目里已经能查到答案的（违反 R3）。
- 不影响实现结果的、只为"显得严谨"的。
- 已经回答过的（除非出现显式冲突，R4/R5）。
- **不带 ⭐ 推荐** 就抛给用户（与 R11 / SKILL 提问纪律冲突）。

## 出口条件（R9，唯一出口）

```bash
node $SKILL/scripts/state.mjs counters .requirementmind
# Blocking Questions: 0
# Blocking Conflicts: 0
# Critical Assumptions: 0
```

三项同时为 0 → 进入 Phase 4。IMPORTANT 问题用户未答时带默认值进规格并记录在 Open Questions；OPTIONAL 一律不问。

## 冲突与用户改变决定

- CONFLICT 类问题的裁决作为新 DEC 冻结，冲突置 RESOLVED 并回填 resolution_decision_id。
- 用户改变决定：旧决策 SUPERSEDED + replaced_by，全量重解析下游。
