# Trigger 4 类（每个被审 Skill 都要过）

1. **Positive**：必须触发的真实用户句
2. **Negative**：明确不该触发（邻域 / 日常写码 / 微修复）
3. **Boundary**：模糊句，写出「谁赢」
4. **Conflict**：两个 description 都能沾，指定优先 + 输家如何改窄

附加：**Strong-model** —— 根文档是否过度约束（18 步 / 全仓必读）。

指标：`Precision = 正确触发 / 实际触发`；`Recall = 正确触发 / 应当触发`。**禁只追 Precision**。

## 机械化支持

- 单条判定：`skillmind.py route --task "<用户句>" --json` → 看 `recommended[0]` 与 `reasons`
- 批量金标：`tests/routing-cases.json`（12 条，P/N/B/C 全覆盖）由 `selftest.py` 自动复跑
- 注册表视角：`skillmind.py registry query --tag <T>` 确认该资源是否在候选池内

## 本 Skill 金标

| 类 | 用户句 | 期望 |
|----|--------|------|
| P | 优化一下 skills 触发器 | 加载 Y |
| P | MCP tool 暴露太多, 审计 | 加载 Y |
| P | AGENTS.md 该更新了, 大扫除 | 加载 Y |
| P | skillmind 帮我建个注册表 | 加载 Y |
| P | 给 skill 评分, 看评分报告 | 加载 Y（命中 `评分` 关键词/触发词） |
| N | 改 TRedPacketTaskServiceImpl 空指针 | **不加载 Y**（可无推荐，或 ai-code；关键是不能是本 skill） |
| N | 查 192.168.1.202 日志 | **不加载 Y**（应为无推荐；`Not for 查日志` 必须挡住） |
| N | /ai-code 按 Handoff 实现 | 不加载 |
| B | token 太贵怎么办 | 仅当明确 skill/MCP/AGENTS 时加载；纯测 ledger 走 token-budget |
| B | 给 ai-code 打个分，看看成功率 | 对象技能名 `ai-code` 会命中其 tag 与 `/ai-code` 触发词 → 实测 ai-code 居首（0.61）。属**边界句**：改窄需把评分意图写成「评分报告 / skill 评分」 |
| C | 项目里还有 skill-governance-doctor | Y 为 SSOT；doctor 是别名，不双开正文 |
| C | 审计 skill 触发器, 然后改 ai-code 的 SKILL.md | Y 居首（治理意图更明确），但链上同时出现 coding 段 |

## 改完 description 后必过

`tests/trigger-cases.md` 的 PASS 判据 + `skillmind.py selftest` 的
`routing_golden_cases` 全过。任一不过 → 回滚 description，禁止带着 Recall 缺口上线。
