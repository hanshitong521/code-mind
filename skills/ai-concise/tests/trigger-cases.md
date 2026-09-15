# concise-mind trigger 压测

| 类 | 用户句 | 期望 |
|----|--------|------|
| P | /concise-mind | 加载 |
| P | 别废话，说人话 | 加载 |
| P | 简洁一点总结上面 | 加载（latch ON 时后续也可） |
| N | /ai-code 按 Handoff 实现 | 不加载 |
| N | 优化 skill 触发器 | 不加载（→ ai-skill-mcp-Y） |
| N | Requirement Gate 怎么过 | 不加载（→ requirement-mind） |
| B | token 太贵 | latch 已 ON 则压文风；纯 ledger → token-budget |
| C | concise-mind vs ai-concise | 同目录 SSOT；禁双读正文 |
