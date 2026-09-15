# Inventory（机械优先）

**首选**：走 SkillMind 注册表 —— 一次覆盖 skill / rules / mcp / overlap 四类，且哈希与本仓控制面一致。

```bash
python3 <this-skill>/scripts/skillmind.py registry build [--root R] [--json]
python3 <this-skill>/scripts/skillmind.py registry query --status verified --json
```

产物 `.skillmind/registry.json`（结构见 `spec-v2.md §14.2`）：

| 字段 | 内容 |
|---|---|
| `skills[]` | id / name / category / tags / version / status / score / owner / load_mode / risk / destructive / root_lines / root_words / refs / triggers / bundled / hash |
| `rules[]` | `.cursor/rules/**/*.mdc` 中 `alwaysApply: true`（**常驻 token 成本来源**） |
| `mcps[]` | 仓库无 MCP 清单时输出空数组（**不臆造**） |
| `overlap[]` | 标签交集 ≥2 或 description 关键词交叉 |

**轻量兜底**（只要一份清单、不需要控制面对齐时）：

```bash
python3 <this-skill>/scripts/inventory.py --root <项目根>
```

输出：`path | name | description | lines | alwaysApply`

## 手扫对照表

| 层 | 扫什么 | 记什么 |
|----|--------|--------|
| L0 常驻 | `.cursor/rules/*.mdc` `alwaysApply:true` | 每轮 token；是否叠层重复 |
| Skill | `**/skills/*/SKILL.md` | name + description + 根行数；load_mode |
| AGENTS | 项目根 `AGENTS.md` / `CLAUDE.md` | 必读清单 vs 导航地图 |
| MCP | 启用的 server 名；tools **只列目录名**，禁整读 `mcps/**/tools/*.json` | standing vs on-demand；单任务暴露个数 |

## 纪律

- 重叠图：description 交叉 ≥1 触发词 → conflict 候选（注册表的 `overlap[]` 已机械产出）。
- 同职责两份（项目 skill + 库 skill）→ `MERGE`，留一 SSOT。
- P0 不进 inventory 正文：密钥、生产连接串、整段日志。
- **哈希语义**：必须复用 `_common.hash_tree`（与 `scripts/_release_lib.py` 逐字节一致），
  自己实现归一化会产生**假 DRIFT**。
