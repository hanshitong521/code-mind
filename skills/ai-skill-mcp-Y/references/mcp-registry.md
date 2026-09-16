# mcp-registry · MCP 清单格式与成本口径

> 对应实现：`scripts/registry_build.py` 的 `scan_mcps` / `_mcp_entries` / `_tool_items`；
> 审计：`scripts/skillmind.py` 的 `_audit_mcp`（`skillmind.py audit --scope mcp`）。
> 相关：`references/gateway.md`（身份/隔离/重试）、`references/security.md`（供应链评级）。

## 0 为什么 MCP 也需要成本审计

**工具定义是每轮都进上下文的常驻成本** —— 与 always skill 的 `root_words` 是同一类东西。
一个 40 工具、每轮全暴露的 MCP，和一个 3 工具的 MCP，在旧审计里长得一模一样（都只记个数）。

**最省 token 的 MCP 优化，是不暴露。** 对应 `references/token-loading.md` 八级序第 1 级「不加载」：
先收窄暴露面（按 phase 白名单），再谈压缩 description。

## 1 清单落点（按序探测，命中即用）

| 顺序 | 路径 | 格式 |
|---|---|---|
| 1 | `shared/mcp-registry.yaml` | YAML |
| 2 | `shared/mcp-manifest.yaml` | YAML |
| 3 | `.skillmind/mcps.yaml` | YAML |
| 4 | `.skillmind/mcps.json` | JSON |

**都缺 → `registry.json.mcps = []`（禁臆造）**，审计报 KEEP 并提示补清单。

顶层接受 `servers` / `mcps` / `mcp_servers` 任一桶名；也接受「map 形式」
（`{server_name: {...}}`，会自动补 `name`）。

## 2 字段

### 2.1 server

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | str | ✅ | 也可写 `id` / `server` |
| `tools` | list | — | 工具列表；也接受 `tool_count`（只给个数，成本不可度量） |
| `standing` | bool | — | **true = 每轮都暴露**（常驻成本来源）。审计报 `LAZY-LOAD` |
| `transport` | str | — | `stdio` / `sse` / `http`；也可写 `type` |
| `owner` | str | — | 对齐 `shared/capability-registry.yaml` |

### 2.2 tool

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | str | 工具名（也可写 `id`） |
| `description` | str | **只答「何时用」**。禁写工作流/示例（与 skill description 同一条纪律） |
| `params` | map | 参数名 → 类型；参与成本估算 |
| `destructive` | bool | true → 需二次权限检查，默认隐藏 |
| `schema_tokens` | int | 可选：有实测值时直接给，跳过估算 |

## 3 成本口径

```
tool.tokens  = schema_tokens            # 显式优先
             | est_tokens(工具名 + description + " " + "k:v" 拼接的参数)
server.tool_tokens = Σ tool.tokens      # 本 server 常驻成本
registry 合计      = Σ server.tool_tokens
```

`est_tokens` 口径见 `references/token-loading.md` §3（`ceil(ascii/4)+ceil(cjk/1.5)`，零依赖）。
**估算值禁冒充遥测实测值**，报告里须标 `est`。

## 4 审计判定

| 条件 | action | 说明 |
|---|---|---|
| `standing: true` 且 `tool_tokens > 0` | `LAZY-LOAD` | 每轮都付；改按 phase 白名单暴露 |
| `tools > capability-registry.tool_budget.default_max_tools_per_phase` | `OPTIMIZE` | 默认上限 12；超限须在 task bundle 显式声明理由 |
| 含任一 `destructive` 工具 | `OPTIMIZE` (risk=high) | 默认隐藏 + 二次确认 |
| 单工具 `tokens > MCP_TOOL_TOKENS_WARN`（600） | `OPTIMIZE` | description 疑似写进工作流，移到 server 端文档 |
| 全部 `tool_tokens` 合计 > `MCP_TOKENS_WARN`（3000） | `OPTIMIZE` | 常驻成本超预算（≈12 工具 × 250 tok） |
| 以上都不命中 | `KEEP` | 合规 |

阈值常量在 `scripts/skillmind.py` 顶部（`MCP_TOKENS_WARN` / `MCP_TOOL_TOKENS_WARN`）。

## 5 自检清单

- [ ] 每个 server 声明 `standing`（未声明按 false 处理，但显式更安全）
- [ ] `destructive` 工具逐个标记，且确认有二次权限检查
- [ ] 工具 `description` 只答「何时用」，无工作流/示例
- [ ] 单 server 工具数 ≤ `tool_budget.default_max_tools_per_phase`
- [ ] 合计 `tool_tokens` ≤ `MCP_TOKENS_WARN`；超出时优先收窄暴露面而非改 description
- [ ] 清单落点四选一，且**不入 `.gitignore`**（否则注册表看不到）

## STOP

STOP:把工作流写进 tool description|standing 无白名单|destructive 无二次确认|用个数代替成本|估算值冒充实测|清单缺失时臆造 server
