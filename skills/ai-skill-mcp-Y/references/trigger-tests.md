# Trigger 4 类（每个被审 Skill 都要过）

1. Positive: 必须触发的真实用户句
2. Negative: 明确不该触发(邻域/日常写码/微修复)
3. Boundary: 模糊句, 写出「谁赢」
4. Conflict: 两个 description 都能沾, 指定优先 + 输家如何改窄

附加: Strong-model — 根文档是否过度约束(18步/全仓必读)。

指标: Precision=正确触发/实际触发; Recall=正确触发/应当触发。禁只追 Precision。

## 本 Skill 金标

| 类 | 用户句 | 期望 |
|----|--------|------|
| P | 优化一下 skills 触发器 | 加载 Y |
| P | MCP tool 暴露太多, 审计 | 加载 Y |
| P | AGENTS.md 该更新了, 大扫除 | 加载 Y |
| N | 改 TRedPacketTaskServiceImpl 空指针 | 不加载 |
| N | 查 192.168.1.202 日志 | 不加载 |
| N | /ai-code 按 Handoff 实现 | 不加载 |
| B | token 太贵怎么办 | 仅当明确 skill/MCP/AGENTS 时加载; 纯测 ledger 走 token-budget |
| C | 项目里还有 skill-governance-doctor | Y 为 SSOT; doctor 是别名, 不双开正文 |
