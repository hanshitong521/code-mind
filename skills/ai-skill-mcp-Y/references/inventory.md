# Inventory（机械优先）

```bash
python <this-skill>/scripts/inventory.py --root <项目根>
```

输出: `path | name | description | lines | alwaysApply`

无脚本时手扫:

| 层 | 扫什么 | 记什么 |
|----|--------|--------|
| L0 常驻 | `.cursor/rules/*.mdc` alwaysApply:true | 每轮 token; 是否叠层重复 |
| Skill | `**/.cursor/skills/*/SKILL.md` 与用户/库 `**/skills/*/SKILL.md` | name+description+根行数; disable-model-invocation |
| AGENTS | 项目根 `AGENTS.md` / `CLAUDE.md` | 必读清单 vs 导航地图 |
| MCP | 启用的 server 名; tools **只列目录名** 禁整读 `mcps/**/tools/*.json` | standing vs on-demand; 单任务暴露个数 |

重叠图: description 交叉 ≥1 触发词 → conflict 候选。
同职责两份(项目 skill + 库 skill) → MERGE, 留一 SSOT。

P0 不进 inventory 正文: 密钥、生产连接串、整段日志。
