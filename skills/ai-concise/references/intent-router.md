# Output Intent Router v4

用**最近一条用户消息**判模式（优先级从上到下）。Latch ON 时 Router **只选模式**，不再决定「压不压」。

| 信号（中/英） | Mode |
|---------------|------|
| 写文档、写报告、写 README、说明书、PRD、方案文档、长文、起草、gen doc、write docs | **DOC** |
| Plan 模式、计划、规划、步骤、怎么做、拆一下、roadmap、只读方案 | **PLAN** |
| 线上、故障、incident、回滚、告警、炸了、502 | INCIDENT |
| 架构、评审设计、ADR、方案评审、委员会、tradeoff | ARCH |
| 交接、给下一个 AI、接手、handoff、context 导出 | HANDOFF |
| 改代码、实现、PR、diff、修 bug（非 incident 语气）、重构 | CODE |
| 简单说一下、简短、tl;dr、不用展开、直接说 | CHAT |
| eli5、说人话、通俗、讲给 … 听、小白 | CHAT + **Explain 档**（见 `levels-and-eli5.md`） |
| （默认） | CODE（实现会话）/ CHAT（纯问答） |

## 两条兜底

1. **歧义时取更保守的模式**：DOC > PLAN > ARCH > CODE > CHAT（越左保留越多）。
2. **一条消息含多个信号**：取**首个**信号；若同时出现「写文档」+「eli5」，取 DOC，并在文档内用 Explain 档的行文。
