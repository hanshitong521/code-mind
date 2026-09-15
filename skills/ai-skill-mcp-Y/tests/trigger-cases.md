# Y 自身 trigger 压测（改 description 后必过）

PASS 仅当：4P 都该加载；3N 都不加载；B/C 与 `references/trigger-tests.md` 金标表一致。

跑法（两种，都要）：

1. **单条人工判**：只看 `SKILL.md` frontmatter 的 `description`，不读正文，判断会不会选中本 skill。
2. **机械复跑**：
   ```bash
   python3 scripts/skillmind.py registry build
   python3 scripts/skillmind.py route --task "优化一下 skills 触发器" --json
   python3 scripts/skillmind.py selftest          # routing_golden_cases 必须全过
   ```

## 期望对照

| 类 | 用户句 | expect_top | expect_not |
|----|--------|-----------|-----------|
| P | 优化一下 skills 触发器 | ai-skill-mcp-Y | — |
| P | MCP tool 暴露太多，审计 | ai-skill-mcp-Y | — |
| P | AGENTS.md 该更新了，大扫除 | ai-skill-mcp-Y | — |
| P | skillmind 帮我建个注册表 | ai-skill-mcp-Y | — |
| P | 给 skill 评分，看评分报告 | ai-skill-mcp-Y | — |
| N | 改 TRedPacketTaskServiceImpl 空指针 | null 或 ai-code | ai-skill-mcp-Y |
| N | 查 192.168.1.202 日志 | null（无推荐） | ai-skill-mcp-Y |
| N | /ai-code 按 Handoff 实现 | ai-code | ai-skill-mcp-Y |
| B | token 太贵怎么办 | 视是否含 skill/MCP/AGENTS 语境 | — |
| B | 给 ai-code 打个分，看看成功率 | ai-code（对象技能名命中 tag/触发词） | — |
| C | 审计 skill 触发器，然后改 ai-code 的 SKILL.md | ai-skill-mcp-Y | ai-design, ai-requirement |

## 判定红线

- `查 192.168.1.202 日志` 若被本 skill 命中 → **FAIL**（说明 `Not for 查日志` 的否定从句
  没被 `positive_clause` 切掉，或 `triggers.exclude` 失效）。
- 治理任务里 `ai-requirement` 靠 `category=governance` 单点混进推荐 → **FAIL**
  （说明同量级带 `RELATIVE_BAND` 失效）。
- 边界句（如「给 ai-code 打个分」）**允许**由对象技能居首；红线是「本 skill 不得误触负例」，
  不是「本 skill 必须赢下所有含 skill 字样的句子」。
